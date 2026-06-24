"""
gerador_testes.py
------------------
Gera cenarios de teste aleatorios (ACL + processos concorrentes), no mesmo
formato usado em casos_de_teste.json. Util para testar o sistema com
combinacoes que nao pensamos manualmente, e para gerar casos de Deadlock
forcado sob demanda.
"""

import json
import random


class GeradorCasosTeste:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.usuarios = ["admin", "supervisor", "estagiario", "sistema", "convidado"]
        self.arquivos_base = ["relatorio.pdf", "dados.csv", "config.ini", "log.txt", "banco.db"]
        self.modos = ["R", "W"]

    def gerar_acl_aleatoria(self, num_arquivos=3):
        acl = {}
        arquivos = random.sample(self.arquivos_base, min(num_arquivos, len(self.arquivos_base)))
        for arquivo in arquivos:
            acl[arquivo] = {}
            usuarios_escolhidos = random.sample(self.usuarios, random.randint(1, 3))
            for usuario in usuarios_escolhidos:
                acl[arquivo][usuario] = random.sample(self.modos, random.randint(1, 2))
        return acl

    def gerar_processo_aleatorio(self, nome, acl, num_passos=4):
        arquivos_disponiveis = list(acl.keys())
        if not arquivos_disponiveis:
            return None

        usuario = random.choice(self.usuarios)
        passos = []

        # Primeiro passo: sempre um 'bloquear', para garantir uso do mecanismo de lock.
        arq_inicial = random.choice(arquivos_disponiveis)
        passos.append({"acao": "bloquear", "arquivo": arq_inicial, "modo": random.choice(self.modos)})

        # Passos intermediarios: mistura de processar / bloquear outro arquivo.
        for _ in range(max(0, num_passos - 2)):
            if random.random() < 0.5:
                passos.append({"acao": "processar", "tempo": round(random.uniform(0.1, 0.4), 2)})
            else:
                arq = random.choice(arquivos_disponiveis)
                passos.append({"acao": "bloquear", "arquivo": arq, "modo": random.choice(self.modos)})

        # Ultimo passo: libera um dos arquivos bloqueados (o resto e limpo no final pelo SO).
        arquivos_bloqueados = [p["arquivo"] for p in passos if p["acao"] == "bloquear"]
        if arquivos_bloqueados:
            passos.append({"acao": "liberar", "arquivo": random.choice(arquivos_bloqueados)})

        return {"nome": nome, "usuario": usuario, "passos": passos}

    def gerar_cenario_aleatorio(self, num_processos=3, num_arquivos=3):
        acl = self.gerar_acl_aleatoria(num_arquivos)
        processos = [
            self.gerar_processo_aleatorio(f"Proc_{i}", acl)
            for i in range(num_processos)
        ]
        return {
            "descricao": "Cenario concorrente aleatorio",
            "acl": acl,
            "processos": [p for p in processos if p is not None],
        }

    def gerar_cenario_deadlock(self):
        """Forca um deadlock classico: A trava arq1 depois arq2; B trava arq2 depois arq1."""
        arq1, arq2 = random.sample(self.arquivos_base, 2)
        return {
            "descricao": "Cenario forcado de deadlock (A->B, B->A)",
            "acl": {
                arq1: {"sistema": ["R", "W"]},
                arq2: {"sistema": ["R", "W"]},
            },
            "processos": [
                {
                    "nome": "Thread_A", "usuario": "sistema",
                    "passos": [
                        {"acao": "bloquear", "arquivo": arq1, "modo": "W"},
                        {"acao": "processar", "tempo": 0.3},
                        {"acao": "bloquear", "arquivo": arq2, "modo": "W"},
                        {"acao": "liberar", "arquivo": arq1},
                        {"acao": "liberar", "arquivo": arq2},
                    ],
                },
                {
                    "nome": "Thread_B", "usuario": "sistema",
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

    def gerar_bateria(self, quantidade=6):
        """Gera um dict de cenarios: a cada 3, um deadlock forcado; os outros, aleatorios."""
        cenarios = {}
        for i in range(quantidade):
            if i % 3 == 1:
                cenarios[f"cenario_{i+1}_deadlock_forcado"] = self.gerar_cenario_deadlock()
            else:
                cenarios[f"cenario_{i+1}_aleatorio"] = self.gerar_cenario_aleatorio(
                    num_processos=random.randint(2, 4)
                )
        return cenarios


def gerar_e_salvar(quantidade=6, arquivo_saida="casos_de_teste_aleatorios.json"):
    """Gera uma bateria de testes aleatorios e salva em um JSON separado,
    para nao sobrescrever os casos fixos em casos_de_teste.json."""
    gerador = GeradorCasosTeste()
    cenarios = gerador.gerar_bateria(quantidade)
    with open(arquivo_saida, "w", encoding="utf-8") as f:
        json.dump(cenarios, f, indent=2, ensure_ascii=False)
    print(f"{quantidade} cenarios aleatorios salvos em '{arquivo_saida}'.")
    return cenarios


if __name__ == "__main__":
    gerar_e_salvar()