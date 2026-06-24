import logging


class PermissaoNegadaError(Exception):
    """Levantada quando uma operacao e recusada pela ACL."""

    def __init__(self, usuario, arquivo, modo, motivo):
        self.usuario = usuario
        self.arquivo = arquivo
        self.modo = modo
        self.motivo = motivo
        super().__init__(f"{usuario} -> '{modo}' em '{arquivo}' negado ({motivo})")


class HierarquiaDePapeis:
    """
    Define a cadeia de autoridade entre papeis, do mais privilegiado
    para o menos privilegiado. Cada papel herda as permissoes de todos
    os papeis que vem depois dele na lista.
    """

    def __init__(self, ordem):
        # ordem: lista do papel MAIS privilegiado para o MENOS privilegiado.
        # Ex.: ["admin", "supervisor", "estagiario", "convidado"]
        self.ordem = list(ordem)
        self._nivel = {papel: i for i, papel in enumerate(self.ordem)}

    def nivel(self, papel):
        """Quanto MENOR o numero, MAIOR o privilegio. Papel desconhecido = sem privilegio (infinito)."""
        return self._nivel.get(papel, len(self.ordem))

    def papeis_herdados(self, papel):
        """Retorna o proprio papel + todos os papeis abaixo dele na hierarquia
        (cujas permissoes ele herda automaticamente)."""
        if papel not in self._nivel:
            return [papel]
        meu_nivel = self._nivel[papel]
        return [p for p, n in self._nivel.items() if n >= meu_nivel]

    def mais_privilegiado(self, papel_a, papel_b):
        """Retorna o papel de maior privilegio entre os dois (usado pelo deadlock)."""
        return papel_a if self.nivel(papel_a) <= self.nivel(papel_b) else papel_b


class SistemaACL:
    """
    Gerenciador de Permissoes baseado em Listas de Controle de Acesso.

    Estrutura de regras esperada (regras_iniciais):
    {
        "arquivo.txt": {
            "papeis": {
                "admin":      {"allow": ["R", "W"]},
                "supervisor": {"allow": ["R", "W"], "deny": ["W"]},  # exemplo de deny vencendo heranca
                "estagiario": {"allow": ["R"]}
            },
            "usuarios": {
                "joao": {"deny": ["W"]}   # excecao pontual a um usuario especifico
            }
        }
    }

    "papeis" e opcional por arquivo; "usuarios" tambem. Se um arquivo nao
    tiver nenhuma regra, o acesso e negado por padrao (fail-closed).
    """

    def __init__(self, regras_iniciais, hierarquia, usuario_papel):
        self.regras = regras_iniciais
        self.hierarquia = hierarquia
        # usuario_papel: dict {usuario: papel}, ex: {"joao": "estagiario"}
        self.usuario_papel = usuario_papel
        self.log_auditoria = []  # cada entrada: (usuario, arquivo, modo, permitido, motivo)

    def papel_de(self, usuario):
        return self.usuario_papel.get(usuario)

    def _checar_usuario(self, regras_arquivo, usuario, modo):
        """Retorna 'allow', 'deny' ou None (sem regra direta para este usuario)."""
        regra = regras_arquivo.get("usuarios", {}).get(usuario)
        if not regra:
            return None
        if modo in regra.get("deny", []):
            return "deny"
        if modo in regra.get("allow", []):
            return "allow"
        return None

    def _checar_papel(self, regras_arquivo, papel, modo):
        """
        Verifica a regra do papel, considerando heranca: percorre o proprio
        papel e todos os papeis abaixo dele na hierarquia. Um 'deny' em
        QUALQUER papel herdado vence; senao, um 'allow' em qualquer um basta.
        """
        if papel is None:
            return None
        papeis_a_checar = self.hierarquia.papeis_herdados(papel)
        regras_papeis = regras_arquivo.get("papeis", {})

        encontrou_allow = False
        for p in papeis_a_checar:
            regra = regras_papeis.get(p)
            if not regra:
                continue
            if modo in regra.get("deny", []):
                return "deny"  # deny tem precedencia imediata
            if modo in regra.get("allow", []):
                encontrou_allow = True
        return "allow" if encontrou_allow else None

    def validar(self, usuario, arquivo, modo, registrar_auditoria=True):
        """
        Decide se 'usuario' pode acessar 'arquivo' no 'modo' (R ou W).
        Aplica a ordem de precedencia: deny do usuario > deny do papel >
        allow do usuario > allow do papel > nega por padrao.
        """
        regras_arquivo = self.regras.get(arquivo)
        permitido, motivo = False, "sem regra para este arquivo (fail-closed)"

        if regras_arquivo:
            papel = self.papel_de(usuario)

            decisao_usuario = self._checar_usuario(regras_arquivo, usuario, modo)
            if decisao_usuario == "deny":
                permitido, motivo = False, "deny explicito no usuario"
            elif decisao_usuario == "allow":
                permitido, motivo = True, "allow explicito no usuario"
            else:
                decisao_papel = self._checar_papel(regras_arquivo, papel, modo)
                if decisao_papel == "deny":
                    permitido, motivo = False, f"deny no papel '{papel}' (ou herdado)"
                elif decisao_papel == "allow":
                    permitido, motivo = True, f"allow no papel '{papel}' (direto ou herdado)"
                else:
                    permitido, motivo = False, "nenhuma regra aplicavel (fail-closed)"

        if registrar_auditoria:
            self.log_auditoria.append((usuario, arquivo, modo, permitido, motivo))

        nivel_log = logging.INFO if permitido else logging.WARNING
        logging.log(nivel_log, f"ACL {'PERMITIU' if permitido else 'NEGOU'}: "
                                f"'{usuario}' -> '{modo}' em '{arquivo}' ({motivo})")
        return permitido

    def nivel_privilegio(self, usuario):
        """
        Privilegio numerico do usuario, usado apenas como criterio auxiliar
        de desempate (ex.: pelo MonitorDeadlock, ver kernel_so.py). Quanto
        MAIOR o numero, MAIOR o privilegio. Baseado no nivel hierarquico do
        papel do usuario -- a hierarquia de papeis e global, nao depende do
        arquivo em questao.
        """
        papel = self.papel_de(usuario)
        if papel is None:
            return 0
        total_papeis = len(self.hierarquia.ordem) or 1
        return total_papeis - self.hierarquia.nivel(papel)

    def estatisticas_auditoria(self):
        """Resumo do log de auditoria: quantos acessos permitidos/negados, por motivo."""
        total = len(self.log_auditoria)
        permitidos = sum(1 for _, _, _, ok, _ in self.log_auditoria if ok)
        negados = total - permitidos
        motivos_negacao = {}
        for _, _, _, ok, motivo in self.log_auditoria:
            if not ok:
                motivos_negacao[motivo] = motivos_negacao.get(motivo, 0) + 1
        return {
            "total_consultas": total,
            "permitidos": permitidos,
            "negados": negados,
            "motivos_negacao": motivos_negacao,
        }