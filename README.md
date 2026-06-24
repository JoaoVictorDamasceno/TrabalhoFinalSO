# Simulação de um Gerenciador de Permissões (ACL)

Trabalho final da disciplina de Sistemas Operacionais — 2026.1

**Tema:** Simulação de um Gerenciador de Permissões: Implementação Simplificada de
Listas de Controle de Acesso.

**Tópicos integrados:** Sistemas de Arquivos (ACL, controle de acesso) + Impasses
(Deadlock, usado como teste de estresse opcional sobre a ACL — não como mecanismo
central do trabalho).

## Estrutura do projeto

```
acl.py               # NUCLEO: hierarquia de papeis, heranca, deny explicito, auditoria
sistema_arquivos.py   # Armazenamento de conteudo dos arquivos (consulta a ACL antes de ler/escrever)
kernel_so.py          # Locks de concorrencia + MonitorDeadlock (OPCIONAL, por cenario)
gerador_testes.py     # Gera cenarios de ACL aleatorios (e, como caso especial, um deadlock forcado)
casos_de_teste.json   # 6 cenarios fixos: 4 de ACL pura, 1 de concorrencia leve, 1 de deadlock
main.py               # Ponto de entrada: roda os cenarios e imprime metricas de ACL + concorrencia
```

## Por que o projeto está organizado assim

A ACL (`acl.py`) **não depende** de threads, locks ou do mecanismo de deadlock —
ela é testável e demonstrável isoladamente. Os módulos de concorrência
(`kernel_so.py`) apenas **consultam** as decisões da ACL; o deadlock que pode
surgir é uma consequência observada de conceder permissões concorrentes, não o
foco da simulação. Por isso a maioria dos cenários em `casos_de_teste.json` tem
`"ativar_monitor_deadlock": false` — são cenários de ACL pura.

### Conceitos de ACL implementados

- **Hierarquia de papéis com herança** (`HierarquiaDePapeis`): um papel herda
  automaticamente as permissões de todos os papéis abaixo dele na cadeia de
  autoridade (ex.: `admin > supervisor > estagiario > convidado`).
- **Deny explícito vencendo herança**: uma regra de negação sempre tem precedência
  sobre uma permissão herdada, mesmo que o papel seja mais privilegiado.
- **Exceções pontuais por usuário**: um usuário específico pode ganhar (ou perder)
  uma permissão independente do papel dele.
- **Fail-closed**: arquivos sem nenhuma regra cadastrada negam acesso por padrão.
- **Log de auditoria**: toda consulta de permissão é registrada, com o motivo da
  decisão (permitido ou negado e por quê).

## Como rodar

```bash
# Cenarios fixos (casos_de_teste.json)
python3 main.py

# Cenarios aleatorios
python3 gerador_testes.py                       # gera casos_de_teste_aleatorios.json
python3 main.py casos_de_teste_aleatorios.json  # roda os cenarios gerados
```

## Métricas reportadas

Para cada cenário e no resumo consolidado final:

- **Da ACL:** total de consultas, permitidos, negados, motivos de negação,
  taxa de negação.
- **Da concorrência (quando o cenário ativa o monitor):** processos concluídos,
  deadlocks resolvidos, processos abortados, tempo total de espera por locks.

## Sobre o cenário de deadlock

Existe **um único** cenário fixo de deadlock (`cenario_6_deadlock_como_teste_de_estresse`),
rotulado explicitamente como teste de estresse. Ele demonstra que, quando um
impasse ocorre, o `MonitorDeadlock` usa a própria hierarquia de privilégios da
ACL como critério para escolher qual processo abortar — sacrificando sempre o
de menor privilégio. Essa é a única integração entre os dois módulos, e é
deliberadamente pequena: o trabalho é sobre ACL, e o deadlock só prova que a
ACL continua coerente mesmo sob concorrência.
