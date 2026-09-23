r"""
NÍVEL 6 — Contexto: o recurso mais escasso de um agente

No nível 2 você descobriu que precisa reenviar o histórico inteiro a cada chamada.
Num chat isso é chato. Num AGENTE é grave: cada volta do loop acrescenta o pedido
de ferramenta E o resultado dela. Um agente que dá 15 voltas lendo documentos pode
mandar 200 mil tokens na última chamada.

Isso cria três problemas distintos, com três soluções distintas. Confundi-los é o
erro mais comum de quem está construindo o primeiro agente sério:

  problema                          solução             onde
  "reenviar o mesmo custa caro"  -> prompt caching      Parte B
  "o histórico não cabe mais"    -> compactação/edição  Parte D
  "quero lembrar amanhã"         -> memória persistente Parte E

⚠  As partes B, C e D usam recursos da API da Anthropic. Em PROVEDOR=openrouter
   elas avisam e são puladas — o formato OpenAI não expõe as métricas de cache,
   e sem poder MEDIR não há lição nenhuma a tirar. As partes A e E funcionam
   nos dois.

Rode com:
    .\.venv\Scripts\python.exe 06_contexto.py
"""

import json
from pathlib import Path

from config import (
    client,
    MODEL,
    cabecalho,
    suporta,
    avisar_indisponivel,
)

# ===========================================================================
# O material fixo: um "manual de operação" grande
# ===========================================================================
# Para o cache funcionar, o trecho cacheado precisa passar de um tamanho mínimo:
# 512 tokens no Opus 5. Abaixo disso a API simplesmente NÃO cacheia — e não avisa,
# não dá erro, só devolve cache_creation_input_tokens = 0.
#
# Em produção esse bloco seria seu manual real, sua base de conhecimento, suas
# instruções longas, seus exemplos few-shot.

MANUAL = """
MANUAL DE OPERAÇÃO LOGÍSTICA — TRANSPORTADORA (uso interno)

1. STATUS DE PEDIDO
   1.1 'aguardando_coleta': mercadoria faturada, ainda no cliente remetente.
   1.2 'em_transito': mercadoria coletada e em movimento entre filiais.
   1.3 'em_rota_entrega': mercadoria na última filial, saiu para entrega hoje.
   1.4 'entregue': canhoto assinado e digitalizado no sistema.
   1.5 'atrasado': previsão de entrega vencida sem baixa de canhoto.
   1.6 'ocorrencia': houve evento que impede a entrega (endereço, recusa, avaria).

2. PRAZOS
   2.1 O prazo contratual conta em dias úteis a partir da coleta, não do faturamento.
   2.2 Capitais do Sudeste: 2 dias úteis. Sul: 3. Centro-Oeste: 4. Nordeste: 5.
   2.3 Norte: 7 dias úteis, exceto Manaus e Porto Velho, que são 9 por via fluvial.
   2.4 Interior soma 2 dias úteis ao prazo da capital do mesmo estado.
   2.5 Feriado municipal na praça de destino suspende a contagem no dia.

3. OCORRÊNCIAS
   3.1 Toda ocorrência precisa de código, descrição e responsável identificado.
   3.2 Ocorrência de avaria exige foto anexada antes do fechamento.
   3.3 Recusa do destinatário gera devolução automática em 48h se não houver
       reagendamento registrado pelo comercial.
   3.4 Endereço não localizado: até 3 tentativas, depois devolve ao remetente.
   3.5 Ocorrência aberta há mais de 5 dias úteis escala para o gerente regional.

4. ATRASO E COMUNICAÇÃO
   4.1 Atraso previsto acima de 1 dia útil: comunicar o cliente proativamente.
   4.2 Atraso acima de 3 dias úteis: comunicar o comercial responsável pela conta.
   4.3 Clientes com contrato SLA (Atacadão Norte, Distribuidora Lima) têm multa
       contratual por dia de atraso e prioridade em realocação de carga.
   4.4 Nunca prometer nova data de entrega sem confirmação da filial de destino.

5. VALORES E SEGURO
   5.1 Carga acima de R$ 50.000 exige averbação de seguro antes da coleta.
   5.2 Carga acima de R$ 100.000 exige escolta em trechos classificados como risco.
   5.3 Divergência entre valor da nota e valor averbado bloqueia a emissão do CT-e.

6. ATENDIMENTO
   6.1 Responder sempre com base em dado do sistema; nunca estimar status.
   6.2 Quando o dado não existir, dizer que não existe e abrir chamado interno.
   6.3 Não divulgar valor de frete negociado de um cliente para outro.
   6.4 Datas ao cliente sempre no formato DD/MM/AAAA.
""".strip()


def separador(titulo: str) -> None:
    print("\n" + "=" * 72)
    print(titulo)
    print("=" * 72)


def relatorio(resposta, rotulo: str) -> None:
    """Imprime o que realmente importa no `usage` quando se estuda cache."""
    u = resposta.usage
    # Três contadores distintos, e é fácil confundir:
    #   input_tokens                 -> pagou preço cheio
    #   cache_creation_input_tokens  -> ESCREVEU no cache (custa 1,25x)
    #   cache_read_input_tokens      -> LEU do cache (custa 0,10x) <- a economia
    print(
        f"  {rotulo:<22} "
        f"novo={u.input_tokens:>6}  "
        f"escreveu_cache={getattr(u, 'cache_creation_input_tokens', 0) or 0:>6}  "
        f"leu_cache={getattr(u, 'cache_read_input_tokens', 0) or 0:>6}"
    )


cabecalho()


# ===========================================================================
# PARTE A — Sem cache: você paga o manual inteiro toda vez
# ===========================================================================

separador("A) Sem cache — o manual é cobrado integralmente em cada chamada")

for i in (1, 2):
    r = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=MANUAL,
        messages=[{"role": "user", "content": "Qual o prazo para Manaus?"}],
    )
    relatorio(r, f"chamada {i}")

print("\n  Duas chamadas idênticas, dois pagamentos idênticos. Nada foi reaproveitado.")


# ===========================================================================
# PARTE B — Com cache
# ===========================================================================
# `cache_control` no nível da requisição marca automaticamente o último bloco
# cacheável. É a forma mais simples e resolve a maioria dos casos.


def parte_b_com_cache() -> None:
    separador("B) Com cache — a primeira escreve, as seguintes leem")

    for i in (1, 2, 3):
        r = client.messages.create(
            model=MODEL,
            max_tokens=300,
            cache_control={"type": "ephemeral"},  # <- a única linha nova
            system=MANUAL,
            messages=[{"role": "user", "content": f"Qual o prazo para Manaus? (v{i})"}],
        )
        relatorio(r, f"chamada {i}")

    print(
        """
  Leia os números acima:
    chamada 1 -> escreveu_cache alto (pagou 1,25x por escrever)
    chamadas 2 e 3 -> leu_cache alto, novo baixíssimo (pagou 0,10x)

  Em um agente com manual grande e muitas voltas, isso derruba a conta em
  até ~90% do trecho fixo. É a otimização de maior retorno que existe, e
  custa uma linha.

  ⚠ Se `escreveu_cache` e `leu_cache` vierem ZERADOS, o trecho é curto demais
    (mínimo de 512 tokens no Opus 5). A API não avisa — falha em silêncio.
"""
    )


# ===========================================================================
# PARTE C — O invalidador silencioso
# ===========================================================================
# O cache é por PREFIXO EXATO. Um único byte diferente no começo do prompt
# invalida tudo dali pra frente. O jeito clássico de destruir o próprio cache
# sem perceber é colocar algo que muda toda hora no início.


def parte_c_invalidador() -> None:
    from datetime import datetime

    separador("C) O erro que zera seu cache sem você notar")

    for i in (1, 2):
        # ⚠ ERRADO DE PROPÓSITO: a hora muda a cada chamada, então o prefixo muda,
        #    então o cache nunca casa. Outros culpados comuns: UUID por requisição,
        #    json.dumps() de um dict sem sort_keys, lista de ferramentas em ordem
        #    variável, o nome do usuário logado.
        system_envenenado = f"[gerado em {datetime.now().isoformat()}]\n{MANUAL}"

        r = client.messages.create(
            model=MODEL,
            max_tokens=300,
            cache_control={"type": "ephemeral"},
            system=system_envenenado,
            messages=[{"role": "user", "content": "Qual o prazo para Manaus?"}],
        )
        relatorio(r, f"chamada {i}")

    print(
        """
  `leu_cache` fica em 0 para sempre. Você paga a escrita toda vez e nunca lê:
  fica MAIS caro do que não ter cache.

  Regra: conteúdo estável primeiro, conteúdo volátil depois.
  A ordem de montagem do prompt é sempre: tools -> system -> messages.
  Diagnóstico: se cache_read_input_tokens não sobe entre chamadas repetidas,
  procure o que está mudando no prefixo.
"""
    )


if suporta("cache_control") and suporta("metricas_cache"):
    parte_b_com_cache()
    parte_c_invalidador()
else:
    avisar_indisponivel(
        "prompt caching",
        "O formato OpenAI não devolve cache_creation/cache_read no `usage`, "
        "então não há como MEDIR a economia — e uma lição sobre cache que você "
        "não pode medir não ensina nada.",
    )
    print(
        """  O conceito continua valendo em qualquer provedor:

    - trecho fixo e grande (manual, few-shot) no INÍCIO do prompt
    - trecho volátil (pergunta, timestamp, id) no FIM
    - nunca coloque datetime.now() ou UUID antes do conteúdo estável

  Vários modelos no OpenRouter cacheiam automaticamente (OpenAI, Gemini) e
  reportam em `usage.prompt_tokens_details.cached_tokens` quando o fazem.
  Outros exigem cache_control inline no endpoint nativo deles. Ou seja:
  neste caminho o cache deixa de ser uma linha e vira pesquisa por modelo."""
    )


# ===========================================================================
# PARTE D — Quando o histórico não cabe mais
# ===========================================================================
# Cache resolve CUSTO, não resolve TAMANHO. A janela do Opus 5 é de 1M tokens,
# generosa, mas um agente que lê arquivos grandes chega lá.
#
# Duas ferramentas do servidor, que fazem coisas DIFERENTES:
#
#   edição de contexto (context editing)
#       APAGA resultados antigos de ferramenta. Não resume — descarta.
#       Ideal para agente que faz muitas buscas: o resultado da busca nº 1
#       raramente importa na volta nº 12.
#
#   compactação (compaction)
#       RESUME o histórico antigo em um bloco de resumo, no servidor.
#       Ideal para conversa longa onde o passado ainda importa.
#
# Ambas são beta e só ATIVAM quando o contexto fica grande. Rodar numa conversa
# curta não muda nada visível — por isso aqui o código está pronto e comentado,
# para você usar quando precisar, em vez de simular um efeito que não ocorreria.

separador("D) Contexto grande demais — edição e compactação (referência)")

if not suporta("compactacao"):
    print("\n  ⚠ Exclusivo da API da Anthropic. No OpenRouter você teria que\n"
          "    implementar o resumo do histórico você mesmo, no seu código.\n")

print(
    '''
  # ---- Edição de contexto: descarta resultados antigos de ferramenta ----
  resposta = client.beta.messages.create(
      betas=["context-management-2025-06-27"],
      model=MODEL,
      max_tokens=4000,
      tools=FERRAMENTAS,
      messages=mensagens,
      context_management={
          "edits": [{"type": "clear_tool_uses_20250919"}]
      },
  )

  # ---- Compactação: resume o histórico antigo ----
  resposta = client.beta.messages.create(
      betas=["compact-2026-01-12"],
      model=MODEL,
      max_tokens=4000,
      messages=mensagens,
      context_management={
          "edits": [{"type": "compact_20260112"}]
      },
  )

  # ⚠ ARMADILHA da compactação:
  #   guarde `resposta.content` INTEIRO no histórico, nunca só o texto.
  mensagens.append({"role": "assistant", "content": resposta.content})   # certo
  mensagens.append({"role": "assistant", "content": texto_extraido})     # ERRADO
  #
  #   O bloco de compactação vem dentro de `content`. Se você extrair só o
  #   texto, joga o resumo fora e o servidor perde a referência — silenciosamente.
'''
)


# ===========================================================================
# PARTE E — Memória entre execuções
# ===========================================================================
# Cache e compactação vivem DENTRO de uma execução. Quando o processo termina,
# tudo se perde. Para o agente lembrar amanhã, alguém precisa gravar em disco.
#
# Existe uma ferramenta de memória pronta na API da Anthropic
# ({"type": "memory_20250818", "name": "memory"}), mas o conceito é mais
# importante que a ferramenta — e o conceito cabe em 20 linhas, em qualquer
# provedor.

separador("E) Memória que sobrevive ao fim do processo")

ARQUIVO_MEMORIA = Path(__file__).parent / "memoria_agente.json"


def carregar_memoria() -> list[str]:
    if ARQUIVO_MEMORIA.exists():
        return json.loads(ARQUIVO_MEMORIA.read_text(encoding="utf-8"))
    return []


def salvar_fato(fato: str) -> None:
    fatos = carregar_memoria()
    if fato not in fatos:
        fatos.append(fato)
        ARQUIVO_MEMORIA.write_text(
            json.dumps(fatos, ensure_ascii=False, indent=2), encoding="utf-8"
        )


fatos = carregar_memoria()
print(f"\n  Fatos lembrados de execuções anteriores: {len(fatos)}")
for f in fatos:
    print(f"    - {f}")

# A memória entra no system prompt — DEPOIS do manual, que é a parte estável.
# Assim o manual continua cacheável mesmo quando a memória muda.
system_com_memoria = MANUAL
if fatos:
    system_com_memoria += "\n\nFATOS LEMBRADOS DE CONVERSAS ANTERIORES:\n" + "\n".join(
        f"- {f}" for f in fatos
    )

pergunta = "Qual o prazo para Manaus e por que ele é diferente?"
r = client.messages.create(
    model=MODEL,
    max_tokens=400,
    system=system_com_memoria,
    messages=[{"role": "user", "content": pergunta}],
)
print(f"\n  [você] {pergunta}")
print(f"  [bot ] {next(b.text for b in r.content if b.type == 'text')}")

salvar_fato("Rafael pergunta com frequência sobre prazos da região Norte.")
print(f"\n  Fato gravado em {ARQUIVO_MEMORIA.name}.")
print("  Rode este arquivo de novo: a lista de fatos lembrados cresce.")

print(
    """
──────────────────────────────────────────────────────────────────────
   O que decidir, na prática, ao construir:

   trecho fixo e grande (manual, few-shot)   -> cacheie, sempre
   agente com muitas buscas                  -> edição de contexto
   conversa longa onde o passado importa     -> compactação
   precisa lembrar entre sessões             -> memória em disco/banco
   histórico crescendo sem controle          -> você tem um bug, não um
                                                problema de contexto

   Ordem de ataque: cacheie primeiro (é grátis em qualidade), só depois
   mexa em descartar ou resumir — essas duas perdem informação.

   Próximo: 07_avaliacao.py — como saber se o agente está bom.
──────────────────────────────────────────────────────────────────────
"""
)
