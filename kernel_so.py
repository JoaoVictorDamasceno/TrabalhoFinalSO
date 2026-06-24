import threading
import logging
import time

from sistema_arquivos import PermissaoNegadaError

logging.basicConfig(
    level=logging.INFO,
    format='[%(relativeCreated)06d ms] [%(levelname)s] %(message)s'
)


class GerenciadorDeRecursos:
    """
    Controla quem esta de posse de qual arquivo (locks) e quem esta
    esperando por qual arquivo. E a fonte de verdade que o MonitorDeadlock
    consulta para montar o grafo de espera.
    """

    def __init__(self, fs):
        self.fs = fs                      # SistemaArquivos (dados + ACL)
        self.locks = {}                   # arquivo -> threading.Lock()
        self.alocados = {}                # processo -> set(arquivos que possui)
        self.esperando = {}               # processo -> arquivo que deseja (ou None)
        self.usuario_do_processo = {}      # processo -> usuario (para consultar privilegio)
        self.lock_so = threading.Lock()    # protege as estruturas acima

        self.metricas = {
            "total_acessos": 0,
            "negados_acl": 0,
            "concluidos": 0,
            "abortados_deadlock": 0,
            "deadlocks_resolvidos": 0,
            "tempo_espera_total": 0.0,
        }

    def registrar_processo(self, processo, usuario):
        with self.lock_so:
            self.alocados.setdefault(processo, set())
            self.esperando.setdefault(processo, None)
            self.usuario_do_processo[processo] = usuario

    def _processo_ativo(self, processo):
        """Um processo so esta 'ativo' se ainda consta nas estruturas do gerenciador.
        Se o MonitorDeadlock o removeu, ele foi abortado."""
        return processo in self.alocados

    def solicitar_bloqueio(self, processo, usuario, arquivo, modo):
        """
        Tenta obter o lock exclusivo de 'arquivo' para 'processo', respeitando a ACL.
        Retorna True se obteve o lock, False se foi abortado por deadlock.
        Levanta PermissaoNegadaError se a ACL nao permitir o acesso.
        """
        with self.lock_so:
            self.metricas["total_acessos"] += 1

        if not self.fs.tem_permissao(usuario, arquivo, modo):
            with self.lock_so:
                self.metricas["negados_acl"] += 1
            raise PermissaoNegadaError(f"{usuario} sem permissao '{modo}' em {arquivo}")

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
                    # O MonitorDeadlock abortou este processo nesse intervalo.
                    # Se conseguimos o lock mesmo assim (corrida entre o
                    # acquire() e o abort), devolvemos o lock antes de sair,
                    # senao ele fica preso para sempre (ninguem mais o libera).
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
    Thread separada que periodicamente constroi o grafo de espera
    (quem espera por um arquivo que outro processo possui) e procura
    ciclos nesse grafo, que indicam Deadlock.

    Politica de escolha de vitima: dentre os processos no ciclo,
    aborta aquele com MENOR privilegio de ACL sobre o arquivo que ele
    proprio possui e que esta bloqueando outro processo. A ideia e
    que processos com menos privilegio tendem a ser tarefas menos
    criticas, entao sacrifica-las primeiro e uma politica defensavel
    (analoga a uma prioridade de processo no SO).
    """

    INTERVALO_VERIFICACAO = 1.0

    def __init__(self, gerenciador, intervalo=None):
        super().__init__(daemon=True)
        self.gerenciador = gerenciador
        self.intervalo = intervalo or self.INTERVALO_VERIFICACAO
        self.ativo = True

    def run(self):
        while self.ativo:
            time.sleep(self.intervalo)
            self.analisar_e_resolver()

    def _construir_grafo_de_espera(self):
        # grafo[proc_A] = proc_B  significa "proc_A espera um arquivo que proc_B possui".
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
        # Busca um ciclo no grafo de espera (DFS). Retorna a lista de nos do ciclo, ou None.
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
        """
        Dentre os processos do ciclo, escolhe o de menor privilegio de ACL
        sobre o arquivo que ele possui e que esta causando o bloqueio.
        Em caso de empate, escolhe o primeiro do ciclo (desempate estavel).
        """
        g = self.gerenciador
        melhor_vitima, menor_privilegio = None, None

        for proc in ciclo:
            usuario = g.usuario_do_processo.get(proc)
            arquivos_do_proc = g.alocados.get(proc, set())
            if not usuario or not arquivos_do_proc:
                continue
            # privilegio do processo = maior privilegio entre os arquivos que ele possui
            privilegio = max(
                g.fs.nivel_privilegio(usuario, arq) for arq in arquivos_do_proc
            )
            if menor_privilegio is None or privilegio < menor_privilegio:
                menor_privilegio, melhor_vitima = privilegio, proc

        return melhor_vitima or ciclo[-1]  # fallback de seguranca

    def analisar_e_resolver(self):
        g = self.gerenciador
        with g.lock_so:
            grafo = self._construir_grafo_de_espera()
            ciclo = self._encontrar_ciclo(grafo)
            if not ciclo:
                return

            vitima = self._escolher_vitima(ciclo)
            usuario_vitima = g.usuario_do_processo.get(vitima, "?")

            logging.error(f"DEADLOCK DETECTADO: {' -> '.join(ciclo)} -> {ciclo[0]}")
            logging.warning(
                f"VITIMA ESCOLHIDA: '{vitima}' (usuario={usuario_vitima}, "
                f"menor privilegio de ACL no ciclo)."
            )

            for arq in list(g.alocados.get(vitima, [])):
                g.locks[arq].release()

            g.alocados.pop(vitima, None)
            g.esperando.pop(vitima, None)
            g.metricas["deadlocks_resolvidos"] += 1
            g.metricas["abortados_deadlock"] += 1