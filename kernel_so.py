Python
import threading
import time
import logging


logging.basicConfig(level=logging.INFO, format='[%(relativeCreated)05d ms] [%(levelname)s]%(message)s')

class SistemaACL:
    def __init__(self, regras_iniciais):
        self.regras = regras_iniciais

    def validar(self, usuario, arquivo, modo):
        permissoes = self.regras.get(arquivo, {}).get(usuario, [])
        return modo in permissoes
