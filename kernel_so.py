import threading
import logging
import time

from acl import PermissaoNegadaError

logging.basicConfig(
    level=logging.INFO,
    format='[%(relativeCreated)06d ms] [%(levelname)s] %(message)s'
)


class GerenciadorDeRecursos:
    """
    Controla locks de arquivo para simular concorrencia entre processos.
    Toda solicitacao de lock primeiro consulta a ACL (acl.validar); o lock
    em si e so o mecanismo de exclusao mutua, nao quem decide permissao.
    """

    def __init__(self, sistema_acl, sistema_arquivos):
        self.acl = sistema_acl
        self.fs = sistema_arquivos
        self.locks = {}
        self.alocados = {}
        self.esperando = {}
        self.lock_so = threading.Lock()

        self.metricas = {
            "total_acessos": 0,
            "negados_acl": 0,
            "concluidos": 0,
            "abortados_deadlock": 0,
            "deadlocks_resolvidos": 0,
            "tempo_espera_total": 0.0,
        }

    def registrar_processo(self, processo):
        with self.lock_so:
            self.alocados.setdefault(processo, set())
            self.esperando.setdefault(processo, None)

    def _processo_ativo(self, processo):
        return processo in self.alocados

    def solicitar_bloqueio(self, processo, usuario, arquivo, modo):
        """
        Tenta obter o lock de 'arquivo', respeitando a ACL (acl.py).
        Retorna True se obteve, False se abortado por deadlock.
        Levanta PermissaoNegadaError (de acl.py) se a ACL negar.
        """
        with self.lock_so:
            self.metricas["total_acessos"] += 1

        if not self.acl.validar(usuario, arquivo, modo):
            with self.lock_so:
                self.metricas["negados_acl"] += 1
            raise PermissaoNegadaError(usuario, arquivo, modo, "negado pela ACL")

        with self.lock_so:
            if arquivo not in self.locks:
                self.locks[arquivo] = threading.Lock()
            self.esperando[processo] = arquivo

        inicio_espera = time.time()
        adquirido = False
        while not adquirido:
            adquirido = self.locks[arquivo].acquire(timeout=0.2)
            with self.lock_so:
                if not self._processo_ativo(processo):
                    if adquirido:
                        self.locks[arquivo].release()
                    return False  # Abortado pelo MonitorDeadlock enquanto esperava

        espera = time.time() - inicio_espera
        with self.lock_so:
            self.metricas["tempo_espera_total"] += espera
            self.esperando[processo] = None
            self.alocados[processo].add(arquivo)

        logging.info(f"LOCK ADQUIRIDO: '{processo}' -> '{arquivo}' (esperou {espera:.3f}s)")
        return True

    def liberar_arquivo(self, processo, arquivo):
        with self.lock_so:
            if arquivo in self.alocados.get(processo, set()):
                self.locks[arquivo].release()
                self.alocados[processo].remove(arquivo)

    def liberar_todos(self, processo):
        with self.lock_so:
            for arq in list(self.alocados.get(processo, set())):
                self.locks[arq].release()
            self.alocados.pop(processo, None)
            self.esperando.pop(processo, None)


class MonitorDeadlock(threading.Thread):
    """
    Thread OPCIONAL que detecta ciclos de espera (deadlock) e os resolve
    abortando uma "vitima". A escolha de vitima usa o nivel de privilegio
    da ACL (SistemaACL.nivel_privilegio) como criterio de desempate: entre
    os processos em conflito, sacrifica o de MENOR privilegio.

    Esse e o UNICO ponto em que o motor de concorrencia consulta a ACL
    para alem da simples permissao/negacao -- e e so um criterio auxiliar,
    nao o foco do trabalho.
    """

    INTERVALO_VERIFICACAO = 1.0

    def __init__(self, gerenciador, usuario_do_processo, intervalo=None):
        super().__init__(daemon=True)
        self.gerenciador = gerenciador
        self.usuario_do_processo = usuario_do_processo  # dict: processo -> usuario
        self.intervalo = intervalo or self.INTERVALO_VERIFICACAO
        self.ativo = True

    def run(self):
        while self.ativo:
            time.sleep(self.intervalo)
            self.analisar_e_resolver()

    def _construir_grafo_de_espera(self):
        g = self.gerenciador
        dono_do_arquivo = {}
        for proc, arquivos in g.alocados.items():
            for arq in arquivos:
                dono_do_arquivo[arq] = proc

        grafo = {}
        for proc, arq_desejado in g.esperando.items():
            if arq_desejado and arq_desejado in dono_do_arquivo:
                dono = dono_do_arquivo[arq_desejado]
                if dono != proc:
                    grafo[proc] = dono
        return grafo

    def _encontrar_ciclo(self, grafo):
        visitados, pilha, caminho = set(), set(), []

        def dfs(nodo):
            visitados.add(nodo)
            pilha.add(nodo)
            caminho.append(nodo)
            vizinho = grafo.get(nodo)
            if vizinho:
                if vizinho not in visitados:
                    resultado = dfs(vizinho)
                    if resultado:
                        return resultado
                elif vizinho in pilha:
                    idx = caminho.index(vizinho)
                    return caminho[idx:]
            pilha.remove(nodo)
            caminho.pop()
            return None

        for no in list(grafo.keys()):
            if no not in visitados:
                ciclo = dfs(no)
                if ciclo:
                    return ciclo
        return None

    def _escolher_vitima(self, ciclo):
        """Escolhe o processo de MENOR privilegio de ACL (criterio de desempate)."""
        g = self.gerenciador
        melhor_vitima, menor_privilegio = None, None

        for proc in ciclo:
            usuario = self.usuario_do_processo.get(proc)
            if not usuario:
                continue
            # Reusa a mesma logica de privilegio que a ACL ja expoe (acl.py),
            # em vez de duplicar o calculo aqui.
            privilegio = g.acl.nivel_privilegio(usuario)
            if menor_privilegio is None or privilegio < menor_privilegio:
                menor_privilegio, melhor_vitima = privilegio, proc

        return melhor_vitima or ciclo[-1]

    def analisar_e_resolver(self):
        g = self.gerenciador
        with g.lock_so:
            grafo = self._construir_grafo_de_espera()
            ciclo = self._encontrar_ciclo(grafo)
            if not ciclo:
                return

            vitima = self._escolher_vitima(ciclo)
            usuario_vitima = self.usuario_do_processo.get(vitima, "?")

            logging.error(f"DEADLOCK DETECTADO: {' -> '.join(ciclo)} -> {ciclo[0]}")
            logging.warning(
                f"VITIMA ESCOLHIDA: '{vitima}' (usuario={usuario_vitima}, "
                f"menor privilegio hierarquico no ciclo)."
            )

            for arq in list(g.alocados.get(vitima, [])):
                g.locks[arq].release()

            g.alocados.pop(vitima, None)
            g.esperando.pop(vitima, None)
            g.metricas["deadlocks_resolvidos"] += 1
            g.metricas["abortados_deadlock"] += 1