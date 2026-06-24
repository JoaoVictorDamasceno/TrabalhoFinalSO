import json
import threading
import time
import logging

from acl import SistemaACL, HierarquiaDePapeis, PermissaoNegadaError
from sistema_arquivos import SistemaArquivos
from kernel_so import GerenciadorDeRecursos, MonitorDeadlock


def montar_acl(config_cenario, config_global):
    """Cria a SistemaACL para um cenario, usando a hierarquia de papeis
    e o mapeamento usuario->papel definidos em '_config_acl' do JSON."""
    hierarquia = HierarquiaDePapeis(config_global["hierarquia_papeis"])
    usuario_papel = config_global["usuario_papel"]
    return SistemaACL(config_cenario["acl"], hierarquia, usuario_papel)


def executar_processo_simulado(dados_proc, gerenciador, usuario_do_processo):
    nome = dados_proc["nome"]
    usuario = dados_proc["usuario"]
    passos = dados_proc["passos"]

    usuario_do_processo[nome] = usuario
    gerenciador.registrar_processo(nome)

    for passo in passos:
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


def rodar_cenario(nome_cenario, config, config_global):
    ativa_deadlock = config.get("ativar_monitor_deadlock", False)
    print(f"\n{'='*70}\nCENARIO: {nome_cenario}")
    print(f"  {config.get('descricao', '')}")
    print(f"  [Monitor de Deadlock: {'ATIVO' if ativa_deadlock else 'desativado -- cenario de ACL pura'}]")
    print('=' * 70)

    acl = montar_acl(config, config_global)
    fs = SistemaArquivos(acl)
    gerenciador = GerenciadorDeRecursos(acl, fs)

    usuario_do_processo = {}
    monitor = None
    if ativa_deadlock:
        monitor = MonitorDeadlock(gerenciador, usuario_do_processo)
        monitor.start()

    threads = [
        threading.Thread(target=executar_processo_simulado, args=(p, gerenciador, usuario_do_processo))
        for p in config["processos"]
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if monitor:
        monitor.ativo = False
        monitor.join()

    m = gerenciador.metricas
    aud = acl.estatisticas_auditoria()

    print(f"\n--- RELATORIO: {nome_cenario} ---")
    print(f"  [ACL] Consultas de permissao : {aud['total_consultas']}")
    print(f"  [ACL] Permitidos             : {aud['permitidos']}")
    print(f"  [ACL] Negados                : {aud['negados']}")
    if aud["motivos_negacao"]:
        print(f"  [ACL] Motivos de negacao     : {aud['motivos_negacao']}")
    print(f"  [Concorrencia] Processos concluidos : {m['concluidos']}")
    print(f"  [Concorrencia] Deadlocks resolvidos  : {m['deadlocks_resolvidos']}")
    print(f"  [Concorrencia] Processos abortados   : {m['abortados_deadlock']}")
    print(f"  [Concorrencia] Tempo total de espera : {m['tempo_espera_total']:.3f}s\n")

    return {"metricas": m, "auditoria": aud}


def rodar_bateria(cenarios, config_global):
    resultados = {}
    for nome, config in cenarios.items():
        resultados[nome] = rodar_cenario(nome, config, config_global)
        time.sleep(0.3)

    total_consultas = sum(r["auditoria"]["total_consultas"] for r in resultados.values())
    total_permitidos = sum(r["auditoria"]["permitidos"] for r in resultados.values())
    total_negados = sum(r["auditoria"]["negados"] for r in resultados.values())
    total_deadlocks = sum(r["metricas"]["deadlocks_resolvidos"] for r in resultados.values())
    total_concluidos = sum(r["metricas"]["concluidos"] for r in resultados.values())

    print(f"\n{'#'*70}\nRESUMO CONSOLIDADO ({len(resultados)} cenarios)\n{'#'*70}")
    print(f"  Total de consultas a ACL : {total_consultas}")
    print(f"  Permitidos pela ACL      : {total_permitidos}")
    print(f"  Negados pela ACL         : {total_negados}")
    taxa = (total_negados / total_consultas * 100) if total_consultas else 0
    print(f"  Taxa de negacao da ACL   : {taxa:.1f}%")
    print(f"  Processos concluidos     : {total_concluidos}")
    print(f"  Deadlocks resolvidos     : {total_deadlocks} (esperado: baixo, e so teste de estresse)")
    print()


def menu_principal():
    import sys
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "casos_de_teste.json"

    print("\n=== SIMULADOR DE GERENCIADOR DE PERMISSOES (ACL) ===")
    print(f"Carregando cenarios de: {arquivo}")
    with open(arquivo, "r", encoding="utf-8") as f:
        dados = json.load(f)

    config_global = dados.pop("_config_acl")
    rodar_bateria(dados, config_global)


if __name__ == "__main__":
    menu_principal()