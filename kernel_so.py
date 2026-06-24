import threading
import logging
import time

logging.basicConfig(level=logging.INFO, format='[%(relativeCreated)05d ms] [%(levelname)s]%(message)s')

class SistemaACL:
    def __init__(self, regras_iniciais):
        self.regras = regras_iniciais

    def validar(self, usuario, arquivo, modo):
        permissoes = self.regras.get(arquivo, {}).get(usuario, [])
        return modo in permissoes
    
class GerenciadorDeRecursos:
    def __init__(self, acl):
        self.acl = acl
        self.locks = {}
        self.alocados = {}
        self.esperando = {}
        self.lock_so = threading.Lock()
        self.metricas = {"acessos_negados": 0, "deadlocks_resolvidos": 0, "tempo_espera_total": 0}

    def registrar_processo(self, nome_processo):
        with self.lock_so:
            if nome_processo not in self.alocados:
                self.alocados[nome_processo] = set()
                self.esperando[nome_processo] = None
                
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
            dono_do_arquivo = {}
            
            for proc, arquivos in self.gerenciador.alocados.items():
                for arq in arquivos: dono_do_arquivo[arq] = proc

            for proc, arq_desejado in self.gerenciador.esperando.items():
                if arq_desejado and arq_desejado in dono_do_arquivo:
                    grafo[proc] = dono_do_arquivo[arq_desejado]
