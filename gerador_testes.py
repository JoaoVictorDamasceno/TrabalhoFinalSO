import json
import random
from datetime import datetime

class GeradorCasosTeste:
    def __init__(self, seed=None):
        if seed: random.seed(seed)
        self.usuarios = ["admin", "supervisor", "estagiario", "sistema", "convidado"]
        self.arquivos_base = ["relatorio.pdf", "dados.csv", "config.ini", "log.txt", "banco.db"]
        self.permissoes = ["R", "W"]
        
    def gerar_acl_aleatoria(self, num_arquivos=3):
        acl = {}
        arquivos = random.sample(self.arquivos_base, min(num_arquivos, len(self.arquivos_base)))
        
        for arquivo in arquivos:
            acl[arquivo] = {}
            usuarios_escolhidos = random.sample(self.usuarios, random.randint(1, 3))
            for usuario in usuarios_escolhidos:
                acl[arquivo][usuario] = random.sample(self.permissoes, random.randint(1, 2))
                
        return acl
    
    def gerar_processo_aleatorio(self, nome, acl, num_passos=4):
        arquivos_disponiveis = list(acl.keys())
        if not arquivos_disponiveis: return None
            
        usuario = random.choice(self.usuarios)
        passos = []
        
        # Passo 1: Bloquear um arquivo inicial (para garantir que usa os locks)
        arq_inicial = random.choice(arquivos_disponiveis)
        passos.append({"acao": "bloquear", "arquivo": arq_inicial, "modo": random.choice(["R", "W"])})
        
        # Passos intermediários (Ações mistas)
        for _ in range(num_passos - 2):
            acao = random.choice(["processar", "ler", "escrever", "bloquear"])
            arq_aleatorio = random.choice(arquivos_disponiveis)
            
            if acao == "processar":
                passos.append({"acao": "processar", "tempo": round(random.uniform(0.1, 0.5), 2)})
            elif acao in ["ler", "escrever"]:
                passos.append({"acao": acao, "arquivo": arq_aleatorio, "conteudo": f"Dado gerado {datetime.now().time()}" if acao == "escrever" else ""})
            elif acao == "bloquear":
                passos.append({"acao": "bloquear", "arquivo": arq_aleatorio, "modo": random.choice(["R", "W"])})
        
        # Último passo: sempre tentar liberar algo explicitamente (o SO limpa o resto no final)
        arquivos_bloqueados = [p["arquivo"] for p in passos if p["acao"] == "bloquear"]
        if arquivos_bloqueados:
            passos.append({"acao": "liberar", "arquivo": random.choice(arquivos_bloqueados)})
            
        return {"nome": nome, "usuario": usuario, "passos": passos}
    
    def gerar_cenario_aleatorio(self, num_processos=3, num_arquivos=3):
        acl = self.gerar_acl_aleatoria(num_arquivos)
        processos = [self.gerar_processo_aleatorio(f"Proc_{i}", acl) for i in range(num_processos)]
        
        return {
            "descricao": "Cenário Concorrente Aleatório",
            "acl": acl,
            "processos": [p for p in processos if p is not None]
        }
    
    def gerar_cenario_deadlock(self):
        arquivos = random.sample(self.arquivos_base, 2)
        return {
            "descricao": "Cenário Forçado de Deadlock (A->B, B->A)",
            "acl": {arquivos[0]: {"sistema": ["R", "W"]}, arquivos[1]: {"sistema": ["R", "W"]}},
            "processos": [
                {
                    "nome": "Thread_A", "usuario": "sistema",
                    "passos": [
                        {"acao": "bloquear", "arquivo": arquivos[0], "modo": "W"},
                        {"acao": "processar", "tempo": 0.2},
                        {"acao": "bloquear", "arquivo": arquivos[1], "modo": "W"}
                    ]
                },
                {
                    "nome": "Thread_B", "usuario": "sistema",
                    "passos": [
                        {"acao": "bloquear", "arquivo": arquivos[1], "modo": "W"},
                        {"acao": "processar", "tempo": 0.2},
                        {"acao": "bloquear", "arquivo": arquivos[0], "modo": "W"}
                    ]
                }
            ]
        }

def gerar_bateria_de_testes(quantidade=5, arquivo_saida="casos_de_teste.json"):
    gerador = GeradorCasosTeste()
    cenarios = {}
    
    print(f"Gerando {quantidade} cenários de teste...")
    for i in range(quantidade):
        # A cada 3 testes, injeta um Deadlock forçado para garantir que a métrica será testada
        if i % 3 == 1:
            cenarios[f"Cenario_{i+1}_Forcar_Deadlock"] = gerador.gerar_cenario_deadlock()
        else:
            cenarios[f"Cenario_{i+1}_Aleatorio"] = gerador.gerar_cenario_aleatorio(num_processos=random.randint(2, 5))
            
    with open(arquivo_saida, 'w') as f:
        json.dump(cenarios, f, indent=2)
        
    print(f"Sucesso! Os testes foram salvos em '{arquivo_saida}'.")
    print("Agora basta rodar: python main.py")

if __name__ == "__main__":
    gerar_bateria_de_testes(quantidade=6)