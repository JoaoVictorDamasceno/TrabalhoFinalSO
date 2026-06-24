import logging


class PermissaoNegadaError(Exception):

    def __init__(self, usuario, arquivo, modo, motivo):
        self.usuario = usuario
        self.arquivo = arquivo
        self.modo = modo
        self.motivo = motivo
        super().__init__(f"{usuario} -> '{modo}' em '{arquivo}' negado ({motivo})")


class HierarquiaDePapeis:

    def __init__(self, ordem):
      
        self.ordem = list(ordem)
        self._nivel = {papel: i for i, papel in enumerate(self.ordem)}

    def nivel(self, papel):
        
        return self._nivel.get(papel, len(self.ordem))

    def papeis_herdados(self, papel):
      
        if papel not in self._nivel:
            return [papel]
        meu_nivel = self._nivel[papel]
        return [p for p, n in self._nivel.items() if n >= meu_nivel]

    def mais_privilegiado(self, papel_a, papel_b):
      
        return papel_a if self.nivel(papel_a) <= self.nivel(papel_b) else papel_b


class SistemaACL:

    def __init__(self, regras_iniciais, hierarquia, usuario_papel):
        self.regras = regras_iniciais
        self.hierarquia = hierarquia
      
        self.usuario_papel = usuario_papel
        self.log_auditoria = []  

    def papel_de(self, usuario):
        return self.usuario_papel.get(usuario)

    def _checar_usuario(self, regras_arquivo, usuario, modo):

        regra = regras_arquivo.get("usuarios", {}).get(usuario)
        if not regra:
            return None
        if modo in regra.get("deny", []):
            return "deny"
        if modo in regra.get("allow", []):
            return "allow"
        return None

    def _checar_papel(self, regras_arquivo, papel, modo):
      
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
   
        papel = self.papel_de(usuario)
        if papel is None:
            return 0
        total_papeis = len(self.hierarquia.ordem) or 1
        return total_papeis - self.hierarquia.nivel(papel)

    def estatisticas_auditoria(self):
      
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