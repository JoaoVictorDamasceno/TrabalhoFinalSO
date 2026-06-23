import threading
import logging

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