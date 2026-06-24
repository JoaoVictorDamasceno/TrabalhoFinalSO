import logging


class PermissaoNegadaError(Exception):
    # Levantada quando um usuario tenta uma operacao sem permissao na ACL.
    pass


class SistemaArquivos:
    """
    Representa um conjunto de arquivos com conteudo e permissões (ACL).

    Cada arquivo tem:
      - um conteudo (string, simulando os dados gravados em disco)
      - uma regra de ACL: {usuario: [modos_permitidos]}, ex: {"admin": ["R", "W"]}

    Modos suportados: "R" (leitura) e "W" (escrita).
    """

    def __init__(self, acl_inicial):
        # acl_inicial: dict no formato {arquivo: {usuario: [modos]}}
        self._acl = acl_inicial
        # Todo arquivo citado na ACL "existe" desde o início, com conteúdo vazio.
        self._conteudo = {arquivo: "" for arquivo in acl_inicial}

    def permissoes_de(self, usuario, arquivo):
        """Retorna a lista de modos permitidos (ex: ['R','W']) para um usuario/arquivo."""
        return self._acl.get(arquivo, {}).get(usuario, [])

    def tem_permissao(self, usuario, arquivo, modo):
        """Verifica se 'usuario' pode acessar 'arquivo' no 'modo' (R ou W)."""
        return modo in self.permissoes_de(usuario, arquivo)

    def nivel_privilegio(self, usuario, arquivo):
        """
        Métrica simples de privilégio, usada pelo MonitorDeadlock para decidir
        qual processo sacrificar em caso de impasse (ver kernel_so.py).

        Quanto mais modos um usuario tem sobre o arquivo, maior o privilegio.
        Ex: ["R","W"] = 2 (privilegio alto) ; ["R"] = 1 (privilegio baixo) ; [] = 0
        """
        return len(self.permissoes_de(usuario, arquivo))

    def ler(self, usuario, arquivo):
        """Le o conteudo do arquivo, verificando a ACL antes."""
        if not self.tem_permissao(usuario, arquivo, "R"):
            logging.warning(f"ACL NEGOU leitura: '{usuario}' -> '{arquivo}'")
            raise PermissaoNegadaError(f"{usuario} nao tem permissao de leitura em {arquivo}")
        return self._conteudo.get(arquivo, "")

    def escrever(self, usuario, arquivo, dado):
        """Escreve (sobrescreve) o conteudo do arquivo, verificando a ACL antes."""
        if not self.tem_permissao(usuario, arquivo, "W"):
            logging.warning(f"ACL NEGOU escrita: '{usuario}' -> '{arquivo}'")
            raise PermissaoNegadaError(f"{usuario} nao tem permissao de escrita em {arquivo}")
        self._conteudo[arquivo] = dado
        return True

    def arquivos(self):
        """Lista todos os arquivos conhecidos pelo sistema."""
        return list(self._acl.keys())