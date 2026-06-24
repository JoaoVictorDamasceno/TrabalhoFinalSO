from acl import PermissaoNegadaError


class SistemaArquivos:
    def __init__(self, sistema_acl, arquivos_iniciais=None):
        self.acl = sistema_acl
        self._conteudo = dict(arquivos_iniciais or {})

    def ler(self, usuario, arquivo):
        if not self.acl.validar(usuario, arquivo, "R"):
            raise PermissaoNegadaError(usuario, arquivo, "R", "negado pela ACL")
        return self._conteudo.get(arquivo, "")

    def escrever(self, usuario, arquivo, dado):
        if not self.acl.validar(usuario, arquivo, "W"):
            raise PermissaoNegadaError(usuario, arquivo, "W", "negado pela ACL")
        self._conteudo[arquivo] = dado
        return True

    def arquivos(self):
        return list(self._conteudo.keys())