import json
import random


PAPEIS_PADRAO = ["admin", "supervisor", "estagiario", "convidado"]
ARQUIVOS_BASE = ["relatorio.pdf", "dados.csv", "config.ini", "log.txt", "banco.db"]
MODOS = ["R", "W"]

class GeradorCasosTeste:
    def __init__(self, seed=None, papeis=None):
        if seed is not None:
            random.seed(seed)
        self.papeis = papeis or PAPEIS_PADRAO

    def gerar_regra_acl_aleatoria(self, arquivo):

        regras_papeis = {}
        for papel in self.papeis:
            if random.random() < 0.6:  
                allow = random.sample(MODOS, random.randint(1, 2))
                regra = {"allow": allow}
                if random.random() < 0.2:  
                    regra["deny"] = random.sample(MODOS, 1)
                regras_papeis[papel] = regra
        return {"papeis": regras_papeis}

    def gerar_acl_aleatoria(self, num_arquivos=3):
        arquivos = random.sample(ARQUIVOS_BASE, min(num_arquivos, len(ARQUIVOS_BASE)))
        return {arquivo: self.gerar_regra_acl_aleatoria(arquivo) for arquivo in arquivos}

    def gerar_processo_aleatorio(self, nome, usuario, acl, num_passos=3):
        arquivos_disponiveis = list(acl.keys())
        if not arquivos_disponiveis:
            return None

        passos = []
        arq_inicial = random.choice(arquivos_disponiveis)
        passos.append({"acao": "bloquear", "arquivo": arq_inicial, "modo": random.choice(MODOS)})

        acao_extra = random.choice(["ler", "escrever"])
        passos.append({
            "acao": acao_extra, "arquivo": arq_inicial,
            **({"conteudo": f"dado de {usuario}"} if acao_extra == "escrever" else {})
        })

        passos.append({"acao": "liberar", "arquivo": arq_inicial})
        return {"nome": nome, "usuario": usuario, "passos": passos}

    def gerar_cenario_aleatorio(self, num_processos=3, num_arquivos=3):

        acl = self.gerar_acl_aleatoria(num_arquivos)
        usuarios_papel = {f"user_{i}": random.choice(self.papeis) for i in range(num_processos)}

        processos = []
        for i, (usuario, _) in enumerate(usuarios_papel.items()):
            p = self.gerar_processo_aleatorio(f"Proc_{i}", usuario, acl)
            if p:
                processos.append(p)

        return {
            "descricao": "Cenario de ACL gerado aleatoriamente (sem deadlock).",
            "ativar_monitor_deadlock": False,
            "_usuario_papel_extra": usuarios_papel,  
            "acl": acl,
            "processos": processos,
        }

    def gerar_cenario_deadlock(self):

        arq1, arq2 = random.sample(ARQUIVOS_BASE, 2)
        papel_alto, papel_baixo = self.papeis[0], self.papeis[-2] 

        acl = {
            arq1: {"papeis": {papel_alto: {"allow": ["R", "W"]}, papel_baixo: {"allow": ["R", "W"]}}},
            arq2: {"papeis": {papel_alto: {"allow": ["R", "W"]}, papel_baixo: {"allow": ["R", "W"]}}},
        }
        return {
            "descricao": f"Deadlock forcado entre papel '{papel_alto}' e '{papel_baixo}' (teste de estresse).",
            "ativar_monitor_deadlock": True,
            "_usuario_papel_extra": {"user_alto": papel_alto, "user_baixo": papel_baixo},
            "acl": acl,
            "processos": [
                {
                    "nome": "Thread_Alto", "usuario": "user_alto",
                    "passos": [
                        {"acao": "bloquear", "arquivo": arq1, "modo": "W"},
                        {"acao": "processar", "tempo": 0.3},
                        {"acao": "bloquear", "arquivo": arq2, "modo": "W"},
                        {"acao": "liberar", "arquivo": arq1},
                        {"acao": "liberar", "arquivo": arq2},
                    ],
                },
                {
                    "nome": "Thread_Baixo", "usuario": "user_baixo",
                    "passos": [
                        {"acao": "bloquear", "arquivo": arq2, "modo": "W"},
                        {"acao": "processar", "tempo": 0.3},
                        {"acao": "bloquear", "arquivo": arq1, "modo": "W"},
                        {"acao": "liberar", "arquivo": arq2},
                        {"acao": "liberar", "arquivo": arq1},
                    ],
                },
            ],
        }

    def gerar_bateria(self, quantidade=5, incluir_deadlock=True):
        cenarios = {}
        for i in range(quantidade - 1 if incluir_deadlock else quantidade):
            cenarios[f"cenario_{i+1}_acl_aleatorio"] = self.gerar_cenario_aleatorio(
                num_processos=random.randint(2, 4)
            )
        if incluir_deadlock:
            cenarios[f"cenario_{quantidade}_deadlock_estresse"] = self.gerar_cenario_deadlock()
        return cenarios


def gerar_e_salvar(quantidade=5, arquivo_saida="casos_de_teste_aleatorios.json"):
 
    gerador = GeradorCasosTeste()
    cenarios = gerador.gerar_bateria(quantidade)

    usuario_papel_consolidado = {}
    for config in cenarios.values():
        usuario_papel_consolidado.update(config.pop("_usuario_papel_extra"))

    saida = {
        "_config_acl": {
            "hierarquia_papeis": PAPEIS_PADRAO,
            "usuario_papel": usuario_papel_consolidado,
        },
        **cenarios,
    }

    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(saida, f, indent=2, ensure_ascii=False)
    print(f"{quantidade} cenarios salvos em '{arquivo_saida}'.")
    return saida


if __name__ == "__main__":
    gerar_e_salvar()