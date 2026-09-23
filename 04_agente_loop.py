r"""
NÍVEL 4 — Um agente de verdade

Mesmo loop do nível 3, agora com o que separa um exemplo de algo usável:

  - várias ferramentas, e o modelo escolhendo e encadeando sozinho
  - ferramentas que LEEM vs. ferramentas que ESCREVEM (e a diferença de risco)
  - confirmação humana antes de qualquer ação irreversível
  - system prompt definindo as regras do agente
  - tratamento de erro que não derruba o loop

Domínio: acompanhamento de entregas. Trocando os dados por chamadas ao seu
ERP/API real, isto vira um agente de produção.

Rode com:
    .\.venv\Scripts\python.exe 04_agente_loop.py
"""

import json
from datetime import date, datetime, timezone

from config import client, MODEL, cabecalho

# ===========================================================================
# "BANCO DE DADOS" — em produção, isto seria seu ERP, API ou SQL
# ===========================================================================

PEDIDOS = {
    "PED-1001": {"cliente": "Atacadão Norte", "status": "em_transito",
                 "previsao": "2026-09-24", "cidade": "Manaus/AM", "valor": 48200.00},
    "PED-1002": {"cliente": "Mercado Sul",    "status": "entregue",
                 "previsao": "2026-09-19", "cidade": "Pelotas/RS", "valor": 12750.50},
    "PED-1003": {"cliente": "Atacadão Norte", "status": "atrasado",
                 "previsao": "2026-09-18", "cidade": "Porto Velho/RO", "valor": 93100.00},
    "PED-1004": {"cliente": "Distribuidora Lima", "status": "em_transito",
                 "previsao": "2026-09-30", "cidade": "Recife/PE", "valor": 7300.00},
}

OCORRENCIAS: list[dict] = []


# ===========================================================================
# AS FERRAMENTAS (código Python comum)
# ===========================================================================

def buscar_pedido(pedido_id: str) -> str:
    p = PEDIDOS.get(pedido_id.upper())
    if not p:
        # Mensagem de erro ÚTIL: diz o que existe. O modelo lê isso e se corrige
        # sozinho na próxima volta. Um "não encontrado" seco desperdiça a volta.
        return f"Pedido {pedido_id} não existe. IDs válidos: {', '.join(PEDIDOS)}"
    return json.dumps({"pedido_id": pedido_id.upper(), **p}, ensure_ascii=False)


def listar_pedidos(status: str | None = None) -> str:
    itens = {
        pid: p for pid, p in PEDIDOS.items()
        if status is None or p["status"] == status
    }
    if not itens:
        return f"Nenhum pedido com status '{status}'."
    return json.dumps(itens, ensure_ascii=False)


def dias_ate(data_iso: str) -> str:
    """Dias entre hoje e uma data. Negativo = já passou."""
    try:
        alvo = date.fromisoformat(data_iso)
    except ValueError:
        return f"Data inválida: '{data_iso}'. Use o formato AAAA-MM-DD."
    delta = (alvo - datetime.now(timezone.utc).date()).days
    return f"{delta} dias (hoje é {datetime.now(timezone.utc).date().isoformat()})"


def registrar_ocorrencia(pedido_id: str, descricao: str) -> str:
    """⚠ ESCRITA — altera o estado do sistema."""
    if pedido_id.upper() not in PEDIDOS:
        return f"Pedido {pedido_id} não existe. Nada foi registrado."
    registro = {
        "pedido_id": pedido_id.upper(),
        "descricao": descricao,
        "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OCORRENCIAS.append(registro)
    return f"Ocorrência registrada em {pedido_id.upper()}."


# ===========================================================================
# DESCRIÇÃO PARA O MODELO
# ===========================================================================
# Note o nível de detalhe nas descrições. Cada frase ali evita um erro:
# ferramenta usada na hora errada, argumento no formato errado, alucinação
# quando o dado não existe.

FERRAMENTAS = [
    {
        "name": "buscar_pedido",
        "description": (
            "Busca os dados completos de UM pedido pelo ID (formato PED-0000): "
            "cliente, status, previsão de entrega, cidade e valor. "
            "Use quando o usuário citar um pedido específico. "
            "Nunca invente dados de pedido — se não achar, diga que não achou."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string", "description": "Ex.: PED-1001"}
            },
            "required": ["pedido_id"],
        },
    },
    {
        "name": "listar_pedidos",
        "description": (
            "Lista pedidos, opcionalmente filtrando por status. "
            "Use para perguntas amplas ('quais estão atrasados?'). "
            "Omita o status para trazer todos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["em_transito", "entregue", "atrasado"],
                    "description": "Filtro opcional de status",
                }
            },
            "required": [],
        },
    },
    {
        "name": "dias_ate",
        "description": (
            "Calcula quantos dias faltam (ou se passaram) até uma data. "
            "Resultado negativo significa data no passado. "
            "Use SEMPRE que precisar comparar uma data com hoje — você não "
            "sabe a data atual por conta própria."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_iso": {"type": "string", "description": "Data em AAAA-MM-DD"}
            },
            "required": ["data_iso"],
        },
    },
    {
        "name": "registrar_ocorrencia",
        "description": (
            "Registra uma ocorrência no histórico de um pedido. "
            "ATENÇÃO: esta ação ALTERA o sistema e é visível para a operação. "
            "Use apenas quando o usuário pedir explicitamente para registrar algo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string"},
                "descricao": {"type": "string", "description": "O que aconteceu"},
            },
            "required": ["pedido_id", "descricao"],
        },
    },
]

IMPLEMENTACOES = {
    "buscar_pedido": buscar_pedido,
    "listar_pedidos": listar_pedidos,
    "dias_ate": dias_ate,
    "registrar_ocorrencia": registrar_ocorrencia,
}

# Ferramentas que mudam o mundo. Estas pedem confirmação humana.
# Separar leitura de escrita é a decisão de segurança mais importante
# no desenho de um agente.
FERRAMENTAS_DE_ESCRITA = {"registrar_ocorrencia"}


SYSTEM = """Você é um assistente da operação logística.

Regras:
- Responda apenas com base no que as ferramentas retornarem. Nunca invente \
pedido, status, data ou valor.
- Se um dado não existir, diga claramente que não existe.
- Você pode encadear ferramentas: buscar um pedido e depois calcular o prazo dele.
- Seja direto. Valores em reais, datas em DD/MM/AAAA nas respostas ao usuário.
- Antes de registrar qualquer ocorrência, tenha certeza de que o usuário pediu isso."""


# ===========================================================================
# O LOOP (mesma estrutura do nível 3, com o portão de confirmação)
# ===========================================================================

def executar_ferramenta(nome: str, argumentos: dict, auto_aprovar: bool) -> tuple[str, bool]:
    """Executa uma ferramenta. Devolve (resultado, houve_erro)."""

    # --- Portão humano para ações irreversíveis ---------------------------
    # O modelo pode errar, e pode ser induzido a errar por dados que ele lê
    # (um e-mail, um PDF, um campo de texto). Por isso a regra não é "confie
    # no modelo": é "ação que muda o mundo passa por um humano".
    if nome in FERRAMENTAS_DE_ESCRITA and not auto_aprovar:
        print(f"  │ ⚠  AÇÃO DE ESCRITA: {nome}({json.dumps(argumentos, ensure_ascii=False)})")
        if input("  │    Autorizar? [s/N] ").strip().lower() != "s":
            # Recusa volta como RESULTADO, não como exceção. O modelo lê,
            # entende que foi negado e responde ao usuário adequadamente.
            return "O usuário NÃO autorizou esta ação. Ela não foi executada.", False

    try:
        return str(IMPLEMENTACOES[nome](**argumentos)), False
    except KeyError:
        return f"Ferramenta '{nome}' não existe.", True
    except TypeError as e:
        return f"Argumentos inválidos para {nome}: {e}", True
    except Exception as e:
        return f"Falha em {nome}: {type(e).__name__}: {e}", True


def rodar_agente(pergunta: str, max_voltas: int = 10, auto_aprovar: bool = False) -> str:
    mensagens = [{"role": "user", "content": pergunta}]

    for volta in range(1, max_voltas + 1):
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM,
            tools=FERRAMENTAS,
            messages=mensagens,
        )

        if resposta.stop_reason == "end_turn":
            return next((b.text for b in resposta.content if b.type == "text"), "")

        # "max_tokens" = a resposta foi cortada no meio. Não é erro da sua
        # lógica, é limite baixo demais. Vale avisar em vez de falhar calado.
        if resposta.stop_reason == "max_tokens":
            return "[resposta truncada — aumente max_tokens]"

        pedidos = [b for b in resposta.content if b.type == "tool_use"]
        mensagens.append({"role": "assistant", "content": resposta.content})

        resultados = []
        for pedido in pedidos:
            print(f"  │ [volta {volta}] {pedido.name}({json.dumps(pedido.input, ensure_ascii=False)})")
            saida, houve_erro = executar_ferramenta(pedido.name, pedido.input, auto_aprovar)
            print(f"  │            -> {saida[:110]}{'...' if len(saida) > 110 else ''}")
            resultados.append({
                "type": "tool_result",
                "tool_use_id": pedido.id,
                "content": saida,
                "is_error": houve_erro,
            })

        mensagens.append({"role": "user", "content": resultados})

    return "[limite de voltas atingido — o agente não conseguiu concluir]"


# ===========================================================================
# DEMONSTRAÇÃO
# ===========================================================================

if __name__ == "__main__":
    cabecalho()
    perguntas = [
        # 1 ferramenta
        "Qual o status do pedido PED-1003?",
        # encadeamento: listar -> buscar -> calcular, o modelo monta o plano sozinho
        "Quais pedidos estão atrasados e há quantos dias cada um passou da previsão?",
        # agregação: exige ler tudo e somar
        "Qual o valor total em trânsito e para quais cidades?",
        # o caminho do erro: o pedido não existe
        "Me dá os detalhes do PED-9999.",
    ]

    for p in perguntas:
        print("\n" + "=" * 70)
        print(f"[você] {p}")
        print("-" * 70)
        print(f"[bot ] {rodar_agente(p)}")

    # Escrita: este vai PARAR e pedir sua autorização no terminal.
    print("\n" + "=" * 70)
    p = "Registre no PED-1003 que o cliente ligou reclamando do atraso."
    print(f"[você] {p}")
    print("-" * 70)
    print(f"[bot ] {rodar_agente(p)}")

    print(f"\nOcorrências gravadas: {OCORRENCIAS}")

    print(
        """
──────────────────────────────────────────────────────────────────────
   Observe o que aconteceu na pergunta 2: você não disse ao agente
   "liste, depois busque, depois calcule". Ele montou o plano sozinho.
   Essa autonomia é o que você ganha — e é também o que você precisa
   conter com limites, confirmação e boas descrições.

   Os quatro pontos de controle que você tem sobre um agente:
     1. system prompt      -> as regras
     2. quais ferramentas   -> o que ele consegue alcançar
     3. descrição de cada   -> quando ele usa cada uma
     4. o portão de escrita -> o que exige um humano

   Próximo: 05_tool_runner.py — o mesmo agente, com 70% menos código.
──────────────────────────────────────────────────────────────────────
"""
    )
