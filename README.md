# Trilha: construindo agentes do zero

Projeto de estudo prático. Cada arquivo numerado é uma aula que **roda de verdade** e
constrói um conceito em cima do anterior. Leia o código — os comentários são a aula.

Roda em **dois provedores**: API da Anthropic (só Claude) ou **OpenRouter**
(GPT, Gemini, Llama, Claude e mais algumas centenas de modelos).

---

## O mapa completo

| Nível | Tema | O que você entende ao final | Arquivo |
|---|---|---|---|
| **0** | Ambiente | Provedor, chave, modelo — sem gastar token | `00_setup.py` |
| **1** | A chamada crua | Um LLM sozinho **não é** um agente | `01_primeira_chamada.py` |
| **2** | Estado | A API não lembra de nada. Memória é você quem carrega | `02_conversa.py` |
| **3** | Ferramentas | ⭐ O **loop do agente** — o conceito central de tudo | `03_primeira_tool.py` |
| **4** | Agente real | Várias ferramentas, erros, portão humano | `04_agente_loop.py` |
| **5** | Menos código | O SDK roda o loop por você (`tool_runner`) | `05_tool_runner.py` |
| **6** | Contexto | Cache (até 90% mais barato), compactação, memória | `06_contexto.py` |
| **7** | Avaliação | ⭐ Como **medir** se o agente está bom, e comparar versões | `07_avaliacao.py` |
| **8** | Produção | Limites, custo, logs, streaming e **injeção de prompt** | `08_producao.py` |

Arquivos de apoio: `config.py` (escolhe o provedor) e `provedor.py` (traduz entre os
dois protocolos — leitura opcional, mas vale depois do nível 4).

Os dois níveis marcados com ⭐ são os que mais mudam seu resultado: o **3** porque é o
conceito central, e o **7** porque é o que impede você de ajustar prompt no escuro.

---

## Antes de começar: escolha um provedor

Você precisa de **uma** chave. **Eu não posso criar conta por você** — é sua.

### Opção A — API da Anthropic (só modelos Claude)

1. <https://console.anthropic.com> → crie a conta e adicione créditos (US$ 5 sobra)
2. **API Keys** → **Create Key** → copie o `sk-ant-...`

**Todos** os recursos da trilha funcionam aqui.

### Opção B — OpenRouter (qualquer modelo)

1. <https://openrouter.ai/keys> → crie a chave `sk-or-...`
2. Adicione créditos

Vale quando você quer comparar modelos de fornecedores diferentes, ou centralizar
a cobrança em um lugar só.

### Configurando

```powershell
Copy-Item .env.example .env
```

Abra o `.env`, preencha a chave do provedor escolhido e (opcionalmente) o `MODELO`.
Ele está no `.gitignore` — nunca vai para o Git.

> **Regra que vale para sempre:** chave de API nunca é escrita dentro do código,
> nunca vai para o Git, nunca é colada em chat. Sempre variável de ambiente ou `.env`.

Para alternar entre os dois sem editar o `.env`:

```bash
PROVEDOR=openrouter MODELO=openai/gpt-4o-mini .\.venv\Scripts\python.exe 04_agente_loop.py
```

---

## O que muda entre os provedores

Os dois falam **protocolos diferentes**, e `provedor.py` traduz um no outro:

| | Anthropic | OpenRouter |
|---|---|---|
| Endpoint | `/v1/messages` | `/v1/chat/completions` |
| SDK | `anthropic` | `openai` |
| `system` | parâmetro separado | primeira mensagem da lista |
| Conteúdo | lista de blocos | string + `tool_calls` |
| Resultado de ferramenta | um bloco dentro da mensagem do usuário | **uma mensagem separada** por resultado |

Os **conceitos** são idênticos — loop, ferramentas, histórico. Por isso as aulas
continuam escritas em um formato só.

Recursos que **só existem na API da Anthropic**. Nas aulas afetadas o script
avisa e segue em frente, sem quebrar:

| Recurso | Nível | O que você perde no OpenRouter |
|---|---|---|
| `count_tokens` | 2 | Medir o prompt *antes* de enviar |
| Métricas de cache | 6 | Ver a economia do cache acontecendo |
| Compactação / edição de contexto | 6 | Teria que resumir o histórico no seu código |
| `tool_runner` | 5 | Cai no loop manual (que é portátil, e funciona) |

Rode `00_setup.py` para ver a lista exata do seu provedor.

---

## Como rodar

O projeto usa um ambiente virtual (`.venv`) para não bagunçar o Python do sistema.

```powershell
.\.venv\Scripts\python.exe 00_setup.py
```

E assim por diante: `01_primeira_chamada.py`, `02_conversa.py`, etc.

---

## Vocabulário que você vai ver o tempo todo

| Termo | O que é, sem enrolação |
|---|---|
| **LLM** | O modelo. Recebe texto, devolve texto. Não faz mais nada sozinho. |
| **Token** | Pedaço de palavra. É a unidade de cobrança. ~1 token ≈ 4 letras. |
| **Prompt** | Tudo que você manda para o modelo naquela chamada. |
| **System prompt** | Instrução de fundo: quem o modelo é, o que pode e não pode fazer. |
| **Contexto** | Tudo que o modelo "está vendo" agora. Tem limite. |
| **Tool / ferramenta** | Uma função sua que o modelo pode **pedir** para executar. |
| **Tool use** | O modelo respondendo "execute a função X com os argumentos Y". |
| **Loop do agente** | Chamar o modelo → executar a ferramenta → devolver o resultado → repetir. |
| **Agente** | LLM + ferramentas + loop. É literalmente isso. |

---

## A ideia central, em uma frase

> Um **agente** é um LLM rodando em um loop, com ferramentas, decidindo sozinho
> quantos passos dar até terminar a tarefa.

Tudo que existe de "avançado" em agentes (memória, subagentes, avaliação, multiagente)
é otimização em cima desse loop. Se você entender o nível 3, entendeu o essencial.

---

## Quando **não** usar um agente

Importante e quase nunca dito. Antes de construir um agente, cheque:

- **Complexidade** — a tarefa tem muitos passos e não dá para descrever todos de antemão? Se dá, use uma chamada só ou um fluxo fixo.
- **Valor** — o resultado justifica custar mais caro e demorar mais? Agente faz N chamadas, não uma.
- **Viabilidade** — o modelo é bom nisso hoje?
- **Custo do erro** — dá para detectar e desfazer quando ele erra? (testes, revisão humana, rollback)

Se a resposta for "não" para qualquer uma, fique no simples. Isso é decisão de
engenharia, não preguiça: a maioria dos problemas reais não precisa de agente.

---

## Sobre custo

O padrão é `claude-opus-5` (Anthropic) ou `anthropic/claude-sonnet-4.5` (OpenRouter).
Para gastar menos enquanto estuda, defina `MODELO` no `.env` — `claude-haiku-4-5`,
`openai/gpt-4o-mini` ou `google/gemini-2.0-flash-001` são ordens de grandeza mais
baratos e bastam para entender os conceitos.

Se o preço do seu modelo não estiver em `PRECOS_POR_MILHAO` (`config.py`), as aulas
mostram os tokens e dizem que o preço não está cadastrado — em vez de exibir
`US$ 0,0000`, que seria um zero mentiroso.
