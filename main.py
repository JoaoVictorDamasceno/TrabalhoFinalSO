import json
import threading
import time
import logging

from sistema_arquivos import SistemaArquivos, PermissaoNegadaError
from kernel_so import GerenciadorDeRecursos, MonitorDeadlock
from gerador_testes import GeradorCasosTeste


def executar_processo_simulado(dados_proc, gerenciador):
    # Executa, em uma thread, a sequencia de passos de um processo.
    nome = dados_proc["nome"]
    usuario = dados_proc["usuario"]
    passos = dados_proc["passos"]

    gerenciador.registrar_processo(nome, usuario)

    for passo in passos:
        # Se o processo foi removido das estruturas do gerenciador, ele foi
        # abortado pelo MonitorDeadlock enquanto executava um passo anterior.
        with gerenciador.lock_so:
            if not gerenciador._processo_ativo(nome):
                logging.info(f"'{nome}' encerrado: foi vitima de deadlock.")
                return

        acao = passo["acao"]
        try:
            if acao == "bloquear":
                obteve = gerenciador.solicitar_bloqueio(nome, usuario, passo["arquivo"], passo["modo"])
                if not obteve:
                    logging.info(f"'{nome}' abortado enquanto esperava por '{passo['arquivo']}'.")
                    gerenciador.liberar_todos(nome)
                    return

            elif acao == "processar":
                time.sleep(passo["tempo"])

            elif acao == "ler":
                conteudo = gerenciador.fs.ler(usuario, passo["arquivo"])
                logging.info(f"'{nome}' leu '{passo['arquivo']}': '{conteudo[:40]}'")

            elif acao == "escrever":
                gerenciador.fs.escrever(usuario, passo["arquivo"], passo.get("conteudo", ""))
                logging.info(f"'{nome}' escreveu em '{passo['arquivo']}'.")

            elif acao == "liberar":
                gerenciador.liberar_arquivo(nome, passo["arquivo"])

        except PermissaoNegadaError as e:
            logging.warning(f"'{nome}' foi BLOQUEADO pela ACL: {e}")
            gerenciador.liberar_todos(nome)
            return

    gerenciador.liberar_todos(nome)
    with gerenciador.lock_so:
        gerenciador.metricas["concluidos"] += 1


def rodar_cenario(nome_cenario, config):
    print(f"\n{'='*60}\nCENARIO: {nome_cenario}\n  {config.get('descricao', '')}\n{'='*60}")

    fs = SistemaArquivos(config["acl"])
    gerenciador = GerenciadorDeRecursos(fs)
    monitor = MonitorDeadlock(gerenciador)
    monitor.start()

    threads = [
        threading.Thread(target=executar_processo_simulado, args=(p, gerenciador))
        for p in config["processos"]
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    monitor.ativo = False
    monitor.join()

    m = gerenciador.metricas
    print(f"\n--- RELATORIO: {nome_cenario} ---")
    print(f"  Acessos solicitados : {m['total_acessos']}")
    print(f"  Negados pela ACL    : {m['negados_acl']}")
    print(f"  Deadlocks resolvidos: {m['deadlocks_resolvidos']}")
    print(f"  Processos concluidos: {m['concluidos']}")
    print(f"  Processos abortados : {m['abortados_deadlock']}")
    print(f"  Tempo total de espera em lock: {m['tempo_espera_total']:.3f}s\n")

    return m


def rodar_bateria(cenarios):
    # Roda varios cenarios em sequencia e imprime um resumo consolidado ao final.
    resultados = {}
    for nome, config in cenarios.items():
        resultados[nome] = rodar_cenario(nome, config)
        time.sleep(0.3)  # pequena pausa para nao misturar logs de cenarios diferentes

    total = {
        "total_acessos": sum(m["total_acessos"] for m in resultados.values()),
        "negados_acl": sum(m["negados_acl"] for m in resultados.values()),
        "deadlocks_resolvidos": sum(m["deadlocks_resolvidos"] for m in resultados.values()),
        "concluidos": sum(m["concluidos"] for m in resultados.values()),
        "abortados_deadlock": sum(m["abortados_deadlock"] for m in resultados.values()),
        "tempo_espera_total": sum(m["tempo_espera_total"] for m in resultados.values()),
    }
    print(f"\n{'#'*60}\nRESUMO CONSOLIDADO ({len(resultados)} cenarios)\n{'#'*60}")
    for chave, valor in total.items():
        print(f"  {chave}: {valor:.3f}" if isinstance(valor, float) else f"  {chave}: {valor}")
    print()


def menu_principal():
    print("\n=== SIMULADOR DE SO: ACL + SISTEMA DE ARQUIVOS + DEADLOCK ===")
    print("1. Rodar cenarios fixos (casos_de_teste.json)")
    print("2. Gerar e rodar cenarios aleatorios")
    escolha = input("Escolha uma opcao (1 ou 2): ").strip()

    if escolha == "1":
        with open("casos_de_teste.json", "r", encoding="utf-8") as f:
            cenarios = json.load(f)
    elif escolha == "2":
        qtd = input("Quantos cenarios aleatorios gerar? [padrao=4]: ").strip()
        qtd = int(qtd) if qtd.isdigit() else 4
        cenarios = GeradorCasosTeste().gerar_bateria(qtd)
    else:
        print("Opcao invalida. Encerrando.")
        return

    rodar_bateria(cenarios)


if __name__ == "__main__":
    menu_principal()