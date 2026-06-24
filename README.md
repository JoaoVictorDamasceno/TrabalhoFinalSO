# Simulador de Gerenciador de Permissões com ACL

Trabalho Final — Sistemas Operacionais — 2026.1

## Tema

Simulação de um Gerenciador de Permissões com Listas de Controle de Acesso (ACL), integrada à detecção e resolução de Deadlocks.

**Tópicos integrados:** Sistemas de Arquivos + Impasses (Deadlocks)

---

## Estrutura do Projeto

```
.
├── main.py               # Ponto de entrada da simulação
├── sistema_arquivos.py   # Sistema de arquivos com ACL embutida
├── kernel_so.py          # Gerenciador de locks e monitor de deadlock
├── gerador_testes.py     # Gerador de cenários aleatórios
├── casos_de_teste.json   # Cenários fixos de teste
└── README.md
```

---

## Como Executar

**Pré-requisito:** Python 3.8+, sem dependências externas.

```bash
python main.py
```

Ao iniciar, um menu pergunta a fonte dos cenários:

```
1. Rodar cenários fixos (casos_de_teste.json)
2. Gerar e rodar cenários aleatórios
```

---

## Cenários de Teste Fixos

| Cenário                                       | Descrição                                                       |
| --------------------------------------------- | --------------------------------------------------------------- |
| `cenario_1_sucesso`                           | Execução limpa, ACL respeitada, sem deadlock                    |
| `cenario_2_acl_nega_acesso`                   | Estagiário tenta escrita negada pela ACL                        |
| `cenario_3_deadlock_resolvido_por_privilegio` | Deadlock clássico; vítima escolhida por menor privilégio na ACL |
| `cenario_4_tres_processos_um_arquivo`         | Três processos disputam o mesmo arquivo em fila                 |

---

## Métricas Reportadas por Cenário

- Acessos solicitados
- Acessos negados pela ACL
- Deadlocks detectados e resolvidos
- Processos concluídos e abortados
- Tempo total de espera em lock

---

## Decisões de Projeto

**ACL dentro do Sistema de Arquivos:** as permissões são verificadas antes de qualquer leitura ou escrita, modelando o comportamento real de um SO.

**Resolução de deadlock por privilégio de ACL:** quando um ciclo de espera é detectado, o processo com menor nível de privilégio na ACL é escolhido como vítima. Isso conecta diretamente os dois tópicos integrados: o controle de acesso não serve apenas para permitir ou negar operações, ele também informa a política de resolução de impasses.
