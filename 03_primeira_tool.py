r"""
NÍVEL 3 — ⭐ O LOOP DO AGENTE

Este é O arquivo. Se você entender o que acontece aqui, entendeu agentes.
Tudo que vem depois é refinamento.

A ideia: o modelo não executa nada. Ele PEDE. Você executa e devolve o resultado.

    você  ──── "que horas são?" + lista de ferramentas ────>  modelo
    você  <─── "pare, execute agora_utc() pra mim"        ───  modelo
    [você executa a função Python de verdade]
    você  ──── "resultado: 2026-09-22T14:40:00Z"          ──>  modelo
    você  <─── "São 14h40 UTC."                            ──  modelo

Esse vai-e-volta é o loop. O modelo decide quantas voltas dar.

Rode com:
    .\.venv\Scripts\python.exe 03_primeira_tool.py
"""

import json
from datetime import datetime, timezone

from config import client, MODEL, cabecalho

# ===========================================================================
# PASSO 1 — A função Python normal
# ===========================================================================
# Não tem nada de especial. É código comum, que o modelo não consegue rodar
# e por isso vai pedir para você rodar.


def agora_utc() -> str:
    """Devolve a data e hora atuais em UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===========================================================================
# PASSO 2 — Descrever a função PARA o modelo
# ===========================================================================
# O modelo nunca vê seu código. Ele vê só esta descrição. Por isso ela é,
# na prática, um prompt — e a qualidade dela determina se o agente funciona.
#
#   name         -> como o modelo vai chamar
#   description  -> QUANDO usar. A parte mais importante. Seja explícito.
#   input_schema -> os argumentos, em JSON Schema
#
# Erro clássico de iniciante: descrição vaga ("pega a hora"). O modelo então
# usa a ferramenta na hora errada, ou não usa quando devia.

FERRAMENTAS = [
    {
        "name": "agora_utc",
        "description": (
            "Retorna a data e a hora atuais no fuso UTC, em formato ISO 8601. "
            "Use sempre que a pergunta depender do momento presente — "
            "'que horas são', 'que dia é hoje', 'quantos dias faltam para X'. "
            "Você não tem outra forma de saber a data atual."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},  # esta ferramenta não recebe argumentos
            "required": [],
        },
    }
]

# Mapa nome -> função de verdade. É assim que você liga o pedido do modelo
# ao seu código.
IMPLEMENTACOES = {"agora_utc": agora_utc}


# ===========================================================================
# PASSO 3 — O loop
# ===========================================================================


def rodar_agente(pergunta: str, max_voltas: int = 10) -> str:
    """O loop do agente, com cada passo impresso para você ver acontecendo."""

    mensagens = [{"role": "user", "content": pergunta}]

    for volta in range(1, max_voltas + 1):
        print(f"\n  ┌─ volta {volta} ─────────────────────────────────")

        # ---- (a) Pergunta ao modelo, informando quais ferramentas existem ----
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=FERRAMENTAS,  # <- sem isto, o modelo não sabe que pode pedir
            messages=mensagens,
        )

        print(f"  │ stop_reason: {resposta.stop_reason}")

        # ---- (b) O modelo terminou? ----
        # "end_turn" = ele respondeu e não quer mais nada. Saímos do loop.
        if resposta.stop_reason == "end_turn":
            print("  └─ modelo concluiu\n")
            return next((b.text for b in resposta.content if b.type == "text"), "")

        # ---- (c) O modelo pediu ferramenta(s) ----
        # stop_reason == "tool_use". Pode vir MAIS DE UM pedido de uma vez
        # (chamadas paralelas) — por isso tratamos como lista.
        pedidos = [b for b in resposta.content if b.type == "tool_use"]

        # Guarda a fala do modelo no histórico. Note que salvamos
        # `resposta.content` INTEIRO, não só o texto: os blocos de tool_use
        # (e de raciocínio) precisam voltar intactos na próxima chamada.
        mensagens.append({"role": "assistant", "content": resposta.content})

        # ---- (d) Executa de verdade ----
        resultados = []
        for pedido in pedidos:
            print(f"  │ pediu: {pedido.name}({json.dumps(pedido.input)})")

            try:
                funcao = IMPLEMENTACOES[pedido.name]
                saida = funcao(**pedido.input)
                erro = False
            except Exception as e:
                # NUNCA deixe a exceção subir e derrubar o agente.
                # Devolva o erro como resultado: o modelo é capaz de ler,
                # entender e tentar outro caminho.
                saida = f"Erro ao executar {pedido.name}: {e}"
                erro = True

            print(f"  │ devolveu: {saida}")

            resultados.append(
                {
                    "type": "tool_result",
                    "tool_use_id": pedido.id,  # <- TEM que casar com o id do pedido
                    "content": str(saida),
                    "is_error": erro,
                }
            )

        # ---- (e) Devolve os resultados ao modelo ----
        # Resultados de ferramenta vão com role "user". Parece estranho, mas é
        # a convenção da API: "user" é tudo que NÃO veio do modelo.
        #
        # Importante: todos os resultados vão em UMA única mensagem. Quebrar em
        # várias faz o modelo parar de pedir chamadas em paralelo.
        mensagens.append({"role": "user", "content": resultados})

        print("  └─ resultado devolvido, voltando ao modelo")

    return "[limite de voltas atingido]"


# ===========================================================================
# PASSO 4 — Rodar
# ===========================================================================

if __name__ == "__main__":
    cabecalho()
    print("=" * 70)
    print("A) Pergunta que EXIGE a ferramenta")
    print("=" * 70)
    print("\n[você]", "Que dia e que horas são agora?")
    print("\n[bot ]", rodar_agente("Que dia e que horas são agora?"))

    print("=" * 70)
    print("B) Pergunta que exige ferramenta + raciocínio em cima do resultado")
    print("=" * 70)
    p = "Quantos dias faltam para o Natal deste ano?"
    print("\n[você]", p)
    print("\n[bot ]", rodar_agente(p))

    print("=" * 70)
    print("C) Pergunta que NÃO precisa de ferramenta")
    print("=" * 70)
    # Repare: uma volta só, stop_reason vai direto para end_turn.
    # O modelo decide sozinho quando não usar. Isso é bom — ferramenta usada
    # à toa custa dinheiro e latência.
    p = "Quantos lados tem um hexágono?"
    print("\n[você]", p)
    print("\n[bot ]", rodar_agente(p))

    print(
        """
──────────────────────────────────────────────────────────────────────
   O que você acabou de construir é um agente completo. Sério.

   Reveja as 5 letras do loop — (a) a (e). Claude Code, assistentes de
   suporte, agentes de pesquisa: todos rodam exatamente isso. O que muda
   é a QUANTIDADE e a QUALIDADE das ferramentas, e como o contexto é
   gerenciado quando o loop fica longo.

   Detalhes que valem ouro e você já viu:
     - `max_voltas` existe para o agente não girar infinito e torrar
       seu saldo. Sempre coloque um limite.
     - erro de ferramenta volta como resultado, não como exceção
     - a descrição da ferramenta é um prompt, trate como tal

   Próximo: 04_agente_loop.py — várias ferramentas e um caso real.
──────────────────────────────────────────────────────────────────────
"""
    )
