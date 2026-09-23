r"""
NÍVEL 5 — Deixando o SDK rodar o loop

Você escreveu o loop na mão duas vezes. Agora que entende o que ele faz,
pode delegá-lo: o SDK da Anthropic tem um `tool_runner` que faz exatamente
aquilo.

Por que só agora? Porque quem começa pelo `tool_runner` acha que é mágica,
e trava no primeiro comportamento estranho. Você já sabe o que tem dentro.

⚠  DUAS RESSALVAS, e as duas importam:

    1. O tool_runner está em BETA no SDK Python — a interface pode mudar.
    2. Ele é um recurso do SDK DA ANTHROPIC, não da API. Em PROVEDOR=openrouter
       ele não existe — e é por isso que este arquivo cai no loop manual lá.

O loop manual do nível 4 não depende de beta nem de provedor. É por isso que
ele continua sendo uma escolha legítima em produção.

Rode com:
    .\.venv\Scripts\python.exe 05_tool_runner.py
"""

import json
from datetime import date, datetime, timezone

from config import client, MODEL, cabecalho, suporta, avisar_indisponivel

PEDIDOS = {
    "PED-1001": {"cliente": "Atacadão Norte", "status": "em_transito",
                 "previsao": "2026-09-24", "cidade": "Manaus/AM", "valor": 48200.00},
    "PED-1002": {"cliente": "Mercado Sul", "status": "entregue",
                 "previsao": "2026-09-19", "cidade": "Pelotas/RS", "valor": 12750.50},
    "PED-1003": {"cliente": "Atacadão Norte", "status": "atrasado",
                 "previsao": "2026-09-18", "cidade": "Porto Velho/RO", "valor": 93100.00},
    "PED-1004": {"cliente": "Distribuidora Lima", "status": "em_transito",
                 "previsao": "2026-09-30", "cidade": "Recife/PE", "valor": 7300.00},
}


# ===========================================================================
# AS FERRAMENTAS — funções Python comuns, com docstring caprichada
# ===========================================================================
# Compare com o nível 4: lá você escreveu a função E um dicionário de
# `input_schema` gigante ao lado, e tinha que manter os dois em sincronia.
#
# Com o `@beta_tool` o schema é gerado a partir da ASSINATURA (os type hints)
# e da DOCSTRING. Ou seja:
#
#     a docstring virou o prompt da ferramenta
#
# Escreva-a com o mesmo cuidado que você escreveria a `description` antes:
# é ela que o modelo lê para decidir quando usar a ferramenta.


def buscar_pedido(pedido_id: str) -> str:
    """Busca os dados completos de um pedido: cliente, status, previsão de
    entrega, cidade e valor. Use quando o usuário citar um pedido específico.
    Nunca invente dados — se o pedido não existir, diga que não existe.

    Args:
        pedido_id: Identificador do pedido, ex.: PED-1001.
    """
    p = PEDIDOS.get(pedido_id.upper())
    if not p:
        return f"Pedido {pedido_id} não existe. IDs válidos: {', '.join(PEDIDOS)}"
    return json.dumps({"pedido_id": pedido_id.upper(), **p}, ensure_ascii=False)


def listar_pedidos(status: str | None = None) -> str:
    """Lista pedidos, opcionalmente filtrando por status. Use para perguntas
    amplas como "quais estão atrasados". Omita o status para trazer todos.

    Args:
        status: Filtro opcional. Um de: em_transito, entregue, atrasado.
    """
    itens = {k: v for k, v in PEDIDOS.items() if status is None or v["status"] == status}
    return json.dumps(itens, ensure_ascii=False) if itens else f"Nenhum pedido '{status}'."


def dias_ate(data_iso: str) -> str:
    """Calcula quantos dias faltam até uma data (negativo = já passou).
    Use sempre que precisar comparar uma data com hoje — você não sabe a
    data atual por conta própria.

    Args:
        data_iso: Data no formato AAAA-MM-DD.
    """
    try:
        alvo = date.fromisoformat(data_iso)
    except ValueError:
        return f"Data inválida: '{data_iso}'. Use AAAA-MM-DD."
    hoje = datetime.now(timezone.utc).date()
    return f"{(alvo - hoje).days} dias (hoje é {hoje.isoformat()})"


SYSTEM = """Você é um assistente da operação logística.
Responda apenas com base no retorno das ferramentas — nunca invente dados.
Seja direto. Valores em reais, datas em DD/MM/AAAA."""

FUNCOES = [buscar_pedido, listar_pedidos, dias_ate]
IMPLEMENTACOES = {f.__name__: f for f in FUNCOES}


# ===========================================================================
# CAMINHO A — com tool_runner (PROVEDOR=anthropic)
# ===========================================================================

if suporta("tool_runner"):
    from anthropic import beta_tool

    # `beta_tool` é um decorador. Aplicamos aqui em vez de em cima da função
    # para que as MESMAS funções sirvam aos dois caminhos.
    FERRAMENTAS_DECORADAS = [beta_tool(f) for f in FUNCOES]

    def rodar_agente(pergunta: str) -> str:
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM,
            tools=FERRAMENTAS_DECORADAS,
            messages=[{"role": "user", "content": pergunta}],
        )

        # Iterar o runner = rodar o loop. A cada volta ele já chamou o modelo,
        # executou as ferramentas pedidas e devolveu os resultados — tudo que
        # você escreveu à mão no nível 4. Para quando o modelo termina.
        ultima = None
        for mensagem in runner:
            ultima = mensagem
            for bloco in mensagem.content:
                if bloco.type == "tool_use":
                    print(f"  │ {bloco.name}({json.dumps(bloco.input, ensure_ascii=False)})")

        return next((b.text for b in ultima.content if b.type == "text"), "")

    MODO = "tool_runner (SDK roda o loop)"


# ===========================================================================
# CAMINHO B — loop manual (PROVEDOR=openrouter)
# ===========================================================================
# Aqui o schema precisa ser escrito à mão de novo, porque não há decorador
# para gerá-lo. É exatamente o trabalho que o tool_runner economiza — e dá
# para ver o tamanho dele.

else:
    avisar_indisponivel(
        "tool_runner",
        "É um helper do SDK da Anthropic, não da API — nenhum gateway o oferece. "
        "Esta aula cai no loop manual do nível 4, que funciona em qualquer provedor.",
    )

    FERRAMENTAS = [
        {
            "name": "buscar_pedido",
            "description": (
                "Busca os dados completos de um pedido: cliente, status, previsão, "
                "cidade e valor. Use quando o usuário citar um pedido específico. "
                "Nunca invente dados."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"pedido_id": {"type": "string", "description": "Ex.: PED-1001"}},
                "required": ["pedido_id"],
            },
        },
        {
            "name": "listar_pedidos",
            "description": (
                "Lista pedidos, opcionalmente filtrando por status. Use para "
                "perguntas amplas. Omita o status para trazer todos."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["em_transito", "entregue", "atrasado"],
                    }
                },
                "required": [],
            },
        },
        {
            "name": "dias_ate",
            "description": (
                "Calcula quantos dias faltam até uma data (negativo = já passou). "
                "Use sempre que precisar comparar uma data com hoje."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"data_iso": {"type": "string", "description": "AAAA-MM-DD"}},
                "required": ["data_iso"],
            },
        },
    ]

    def rodar_agente(pergunta: str, max_voltas: int = 8) -> str:
        mensagens = [{"role": "user", "content": pergunta}]

        for _ in range(max_voltas):
            resposta = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM,
                tools=FERRAMENTAS,
                messages=mensagens,
            )

            if resposta.stop_reason != "tool_use":
                return next((b.text for b in resposta.content if b.type == "text"), "")

            pedidos = [b for b in resposta.content if b.type == "tool_use"]
            mensagens.append({"role": "assistant", "content": resposta.content})

            resultados = []
            for pedido in pedidos:
                print(f"  │ {pedido.name}({json.dumps(pedido.input, ensure_ascii=False)})")
                try:
                    saida, houve_erro = str(IMPLEMENTACOES[pedido.name](**pedido.input)), False
                except Exception as e:
                    saida, houve_erro = f"Falha em {pedido.name}: {e}", True
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": pedido.id,
                    "content": saida,
                    "is_error": houve_erro,
                })

            mensagens.append({"role": "user", "content": resultados})

        return "[limite de voltas atingido]"

    MODO = "loop manual (provedor sem tool_runner)"


# ===========================================================================
# RODAR
# ===========================================================================

if __name__ == "__main__":
    cabecalho()
    print(f"[modo: {MODO}]")

    for p in [
        "Qual o status do PED-1003?",
        "Quais pedidos estão atrasados e há quantos dias passaram da previsão?",
        "Qual o valor total em trânsito?",
    ]:
        print("\n" + "=" * 70)
        print(f"[você] {p}")
        print("-" * 70)
        print(f"[bot ] {rodar_agente(p)}")

    print(
        """
──────────────────────────────────────────────────────────────────────
   Quando usar cada um:

   tool_runner   -> a maioria dos casos, SE você está na API da Anthropic.
                    Menos código, menos bug bobo. Continua dando para
                    interceptar cada volta (foi o que fizemos no `for`)
                    para log, aprovação e métricas.

   loop manual   -> quando você precisa de controle que o runner não expõe,
                    quando não quer depender de uma API beta, ou quando
                    precisa rodar em mais de um provedor. É o único caminho
                    portátil — e note que ele custou ~40 linhas a mais,
                    quase todas de schema escrito à mão.

   Você não "subiu de nível" trocando um pelo outro. O valor está em saber
   o que tem dentro — e isso você já tem.

──────────────────────────────────────────────────────────────────────
   ATÉ AQUI VOCÊ APRENDEU (níveis 0 a 5):

     ✓ LLM é texto -> texto, e nada mais
     ✓ memória é sua, e custa caro reenviar
     ✓ o loop do agente: pedir -> executar -> devolver -> repetir
     ✓ a descrição da ferramenta é o prompt que decide tudo
     ✓ erro volta como resultado, nunca como exceção
     ✓ escrita precisa de portão humano
     ✓ limite de voltas não é opcional

   Próximo: 06_contexto.py — cache, compactação e memória.
──────────────────────────────────────────────────────────────────────
"""
    )
