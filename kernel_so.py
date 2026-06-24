import threading
import time
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='[%(relativeCreated)05d ms] [%(levelname)s] %(message)s')

class SistemaArquivos:
    def __init__(self):
        self.arquivos = {}
        
    def ler(self, nome):
        return self.arquivos.get(nome, None)
    
    def escrever(self, nome, conteudo):
        self.arquivos[nome] = conteudo
        return True

class SistemaACL:
    def __init__(self, regras_iniciais):
        self.regras = regras_iniciais
        self.grupos = {"gerencia": ["admin", "supervisor"], "operacional": ["sistema", "estagiario"]}
        
    def validar(self, usuario, arquivo, modo):
        if arquivo not in self.regras: return False
        
        # Permissão direta
        if modo in self.regras[arquivo].get(usuario, []): return True
        
        # Permissão via grupo
        for grupo, membros in self.grupos.items():
            if usuario in membros:
                for membro in membros:
                    if modo in self.regras[arquivo].get(membro, []): return True
        return False

class GerenciadorDeRecursos:
    def __init__(self, acl, sistema_arquivos):
        self.acl = acl
        self.fs = sistema_arquivos
        self.locks = {}
        self.alocados = defaultdict(set)
        self.esperando = {}
        self.lock_so = threading.Lock()
        
        self.metricas = {
            "total_acessos": 0, "permitidos": 0, "negados": 0,
            "deadlocks": 0, "abortados": 0, "espera_total": 0.0,
            "concluidos": 0, "falhos": 0
        }

    def solicitar_bloqueio(self, processo, usuario, arquivo, modo):
        with self.lock_so:
            self.metricas["total_acessos"] += 1
            if processo not in self.esperando: self.esperando[processo] = None
            
        if not self.acl.validar(usuario, arquivo, modo):
            logging.warning(f"ACL NEGOU: '{processo}' ({usuario}) -> '{arquivo}'")
            with self.lock_so:
                self.metricas["negados"] += 1
                self.metricas["falhos"] += 1
            return False
            
        with self.lock_so: self.metricas["permitidos"] += 1

        with self.lock_so:
            if arquivo not in self.locks: self.locks[arquivo] = threading.Lock()
            self.esperando[processo] = arquivo

        inicio_espera = time.time()
        adquirido = False
        while not adquirido:
            adquirido = self.locks[arquivo].acquire(timeout=0.2)
            with self.lock_so:
                if processo not in self.alocados and processo not in self.esperando:
                    return False # Abortado pelo Monitor

        espera = time.time() - inicio_espera
        with self.lock_so:
            self.metricas["espera_total"] += espera
            self.esperando[processo] = None
            self.alocados[processo].add(arquivo)
            
        logging.info(f"LOCK ADQUIRIDO: '{processo}' -> '{arquivo}' ({espera:.3f}s)")
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
    def __init__(self, gerenciador):
        super().__init__(daemon=True)
        self.gerenciador = gerenciador
        self.ativo = True

    def run(self):
        while self.ativo:
            time.sleep(1.0)
            self.analisar_e_resolver()

    def analisar_e_resolver(self):
        with self.gerenciador.lock_so:
            grafo = {}
            dono = {arq: proc for proc, arqs in self.gerenciador.alocados.items() for arq in arqs}
            for proc, arq_desejado in self.gerenciador.esperando.items():
                if arq_desejado in dono: grafo[proc] = dono[arq_desejado]

            visitados, pilha, ciclo = set(), set(), []

            def dfs(nodo, caminho):
                visitados.add(nodo); pilha.add(nodo); caminho.append(nodo)
                vizinho = grafo.get(nodo)
                if vizinho:
                    if vizinho not in visitados and dfs(vizinho, caminho): return True
                    elif vizinho in pilha:
                        ciclo.extend(caminho[caminho.index(vizinho):])
                        return True
                pilha.remove(nodo); caminho.pop()
                return False

            for no in list(grafo.keys()):
                if no not in visitados and dfs(no, []):
                    self.gerenciador.metricas["deadlocks"] += 1
                    logging.error(f"DEADLOCK DETECTADO! Ciclo: {' -> '.join(ciclo)} -> {ciclo[0]}")
                    
                    vitima = ciclo[-1]
                    logging.warning(f"SO RESOLVENDO: Abortando '{vitima}'")
                    
                    for arq in list(self.gerenciador.alocados[vitima]):
                        self.gerenciador.locks[arq].release()
                    
                    del self.gerenciador.alocados[vitima]
                    del self.gerenciador.esperando[vitima]
                    self.gerenciador.metricas["abortados"] += 1
                    break