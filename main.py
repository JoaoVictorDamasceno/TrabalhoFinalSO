import json
import threading
import time
import logging
from kernel_so import SistemaACL, GerenciadorDeRecursos, MonitorDeadlock

def executar_processo_simulado(dados_proc, gerenciador):
    nome, usuario, passos = dados_proc["nome"], dados_proc["usuario"], dados_proc["passos"]
    
    for passo in passos:
        with gerenciador.lock_so:
            if nome not in gerenciador.alocados and passo != passos[0]:
                return # Abortado

        acao = passo["acao"]
        if acao == "bloquear":
            if not gerenciador.solicitar_bloqueio(nome, usuario, passo["arquivo"], passo["modo"]):
                gerenciador.liberar_todos(nome)
                return
        elif acao == "processar":
            time.sleep(passo["tempo"])
        elif acao == "liberar":
            gerenciador.liberar_arquivo(nome, passo["arquivo"])

    gerenciador.liberar_todos(nome)

def rodar_cenario(nome_cenario, config_cenario):
    print(f"\n--- CENARIO: {nome_cenario} ---")
    acl = SistemaACL(config_cenario["acl"])
    gerenciador = GerenciadorDeRecursos(acl)
    monitor = MonitorDeadlock(gerenciador)
    monitor.start()

    threads = []
    for p_data in config_cenario["processos"]:
        t = threading.Thread(target=executar_processo_simulado, args=(p_data, gerenciador))
        threads.append(t)
        t.start()

    for t in threads: t.join()

    monitor.ativo = False
    monitor.join()

    print(f"\n--- RELATORIO ---")
    print(f" Deadlocks: {gerenciador.metricas['deadlocks_resolvidos']}")
    print(f" Acessos Negados: {gerenciador.metricas['acessos_negados']}")
    print(f" Espera Total: {gerenciador.metricas['tempo_espera_total']:.2f}s\n")

if __name__ == "__main__":
    with open('casos_de_teste.json', 'r') as f:
        testes = json.load(f)
        
    for nome, config in testes.items():
        rodar_cenario(nome, config)