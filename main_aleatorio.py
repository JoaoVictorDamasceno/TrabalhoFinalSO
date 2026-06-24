import json
import threading
import time
import logging
import os
from kernel_SO import SistemaACL, GerenciadorDeRecursos, MonitorDeadlock, SistemaArquivos
from gerador_testes import GeradorCasosTeste

def executar_processo_simulado(dados_proc, gerenciador):
    nome, usuario, passos = dados_proc["nome"], dados_proc["usuario"], dados_proc["passos"]
    
    for passo in passos:
        with gerenciador.lock_so:
            if nome not in gerenciador.esperando and nome not in gerenciador.alocados and passo != passos[0]:
                return # Processo foi vítima de deadlock e abortado

        acao = passo["acao"]
        if acao == "bloquear":
            if not gerenciador.solicitar_bloqueio(nome, usuario, passo["arquivo"], passo["modo"]):
                gerenciador.liberar_todos(nome)
                return
        elif acao == "processar":
            time.sleep(passo.get("tempo", 0.5))
        elif acao == "ler":
            gerenciador.fs.ler(passo["arquivo"])
        elif acao == "escrever":
            gerenciador.fs.escrever(passo["arquivo"], passo.get("conteudo", "dados"))
        elif acao == "liberar":
            gerenciador.liberar_arquivo(nome, passo["arquivo"])

    gerenciador.liberar_todos(nome)
    with gerenciador.lock_so: gerenciador.metricas["concluidos"] += 1

def rodar_simulacao(cenarios):
    resultados_globais = []

    for nome_cenario, config in cenarios.items():
        print(f"\n{'='*50}\n[ INICIANDO CENÁRIO ]: {nome_cenario}\n{'='*50}")
        
        fs = SistemaArquivos()
        acl = SistemaACL(config["acl"])
        gerenciador = GerenciadorDeRecursos(acl, fs)
        monitor = MonitorDeadlock(gerenciador)
        monitor.start()

        threads = []
        for p_data in config["processos"]:
            t = threading.Thread(target=executar_processo_simulado, args=(p_data, gerenciador))
            threads.append(t)
            t.start()

        for t in threads: t.join()
        monitor.ativo = False; monitor.join()
        
        resultados_globais.append(gerenciador.metricas)
        time.sleep(0.5)

    if not resultados_globais: return

    t_acessos = sum(m["total_acessos"] for m in resultados_globais)
    t_negados = sum(m["negados"] for m in resultados_globais)
    t_deadlocks = sum(m["deadlocks"] for m in resultados_globais)
    t_espera = sum(m["espera_total"] for m in resultados_globais)
    t_concluidos = sum(m["concluidos"] for m in resultados_globais)
    t_falhos = sum(m["falhos"] + m["abortados"] for m in resultados_globais)

    taxa_negacao = (t_negados / max(1, t_acessos)) * 100
    espera_media = t_espera / max(1, t_acessos)

    print("\n" + "#"*50)
    print(" RELATÓRIO CONSOLIDADO FINAL ")
    print("#"*50)
    print(f" -> Total de Acessos Solicitados: {t_acessos}")
    print(f" -> Acessos Negados (ACL): {t_negados} (Taxa: {taxa_negacao:.1f}%)")
    print(f" -> Deadlocks Detectados/Resolvidos: {t_deadlocks}")
    print(f" -> Processos Concluídos com Sucesso: {t_concluidos}")
    print(f" -> Processos Falhos/Abortados: {t_falhos}")
    print(f" -> Tempo Total de Espera em Lock: {t_espera:.4f}s")
    print(f" -> Tempo Médio de Espera por Acesso: {espera_media:.4f}s")
    print("#"*50 + "\n")

def menu_principal():
    print("\n=== SIMULADOR DE SO (ACL & DEADLOCKS) ===")
    print("1. Executar testes fixos (casos_de_teste.json)")
    print("2. Gerar e executar cenários aleatórios (Na hora)")
    
    escolha = input("Escolha uma opção (1 ou 2): ").strip()
    
    cenarios_para_rodar = {}
    
    if escolha == '1':
        if not os.path.exists('casos_de_teste.json'):
            print("Erro: O arquivo 'casos_de_teste.json' não foi encontrado na pasta.")
            return
        with open('casos_de_teste.json', 'r') as f:
            cenarios_para_rodar = json.load(f)
            
    elif escolha == '2':
        print("Gerando cenários dinâmicos...")
        gerador = GeradorCasosTeste()
        # Gera 2 cenários aleatórios e 1 cenário forçado de deadlock em memória
        cenarios_para_rodar["Cenario_Dinamico_Aleatorio_1"] = gerador.gerar_cenario_aleatorio()
        cenarios_para_rodar["Cenario_Dinamico_Aleatorio_2"] = gerador.gerar_cenario_aleatorio()
        cenarios_para_rodar["Cenario_Dinamico_Deadlock"] = gerador.gerar_cenario_deadlock()
    
    else:
        print("Opção inválida. Encerrando.")
        return
        
    rodar_simulacao(cenarios_para_rodar)

if __name__ == "__main__":
    menu_principal()