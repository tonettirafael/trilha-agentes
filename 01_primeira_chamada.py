r"""
NÍVEL 1 — A chamada crua

A lição mais importante deste arquivo é NEGATIVA:
um LLM sozinho não é um agente. Ele recebe texto e devolve texto. Ponto.
Não navega, não lê arquivo, não consulta banco, não sabe que horas são.

Tudo que você vai construir daqui pra frente existe para resolver essa limitação.

Rode com:
    .\.venv\Scripts\python.exe 01_primeira_chamada.py
"""

from config import client, MODEL, mostrar_custo, cabecalho

cabecalho()

# ===========================================================================
# PARTE A — A chamada mínima possível
# ===========================================================================

print("=" * 70)
print("A) Chamada mínima")
print("=" * 70)

resposta = client.messages.create(
    model=MODEL,
    max_tokens=1000,
    messages=[
        {"role": "user", "content": "Explique o que é um agente de IA em 2 frases."}
    ],
)

# `resposta.content` NÃO é uma string. É uma LISTA de blocos, e cada bloco tem
# um `.type`. Pode vir bloco de texto, de raciocínio ("thinking"), de uso de
# ferramenta ("tool_use")... Por isso sempre cheque o tipo antes de ler `.text`.
#
# Este é o erro nº 1 de quem começa: fazer `resposta.content[0].text` e quebrar
# quando o primeiro bloco não é texto.
for bloco in resposta.content:
    if bloco.type == "text":
        print(f"\n{bloco.text}")

mostrar_custo(resposta, prefixo="\n")


# ===========================================================================
# PARTE B — Os três papéis (roles)
# ===========================================================================
# Uma conversa é uma lista de mensagens, cada uma com um papel:
#
#   system     -> instrução de fundo. Quem o modelo é, o que pode/não pode.
#                 Vai em um parâmetro separado, NÃO dentro de `messages`.
#   user       -> o que a pessoa (ou seu sistema) disse.
#   assistant  -> o que o modelo respondeu antes.
#
# O `system` é onde você molda o comportamento. É a diferença entre um
# chatbot genérico e um assistente que segue as regras do seu negócio.

print("\n" + "=" * 70)
print("B) O system prompt muda tudo")
print("=" * 70)

PERGUNTA = "Como faço para melhorar a performance do meu código?"

for descricao, system in [
    ("SEM system prompt", None),
    (
        "COM system prompt",
        "Você é um engenheiro sênior cético. Responda em no máximo 3 linhas. "
        "Antes de sugerir qualquer otimização, pergunte se a pessoa mediu o "
        "gargalo. Nunca sugira otimização sem medição.",
    ),
]:
    print(f"\n--- {descricao} ---")
    r = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=system,  # `None` = sem system prompt
        messages=[{"role": "user", "content": PERGUNTA}],
    )
    print(next(b.text for b in r.content if b.type == "text"))


# ===========================================================================
# PARTE C — A prova de que o LLM sozinho não é um agente
# ===========================================================================
# Pergunte algo que exige informação do mundo real, agora.
# O modelo não tem como saber. Ele vai dizer que não sabe (bom) ou inventar
# (ruim). Nenhum dos dois resolve seu problema.

print("\n" + "=" * 70)
print("C) O limite: o modelo não tem acesso a nada")
print("=" * 70)

r = client.messages.create(
    model=MODEL,
    max_tokens=500,
    messages=[
        {
            "role": "user",
            "content": "Que horas são agora, e quantos arquivos existem nesta pasta?",
        }
    ],
)
print("\n" + next(b.text for b in r.content if b.type == "text"))

print(
    """
──────────────────────────────────────────────────────────────────────
   Guarde isso: o modelo acabou de dizer que não consegue.
   Ele está certo. Um LLM é uma função pura texto -> texto.

   Dar "mãos" a ele — deixá-lo executar funções suas — é exatamente o
   que transforma um LLM em um agente. É o nível 3.

   Antes disso, o nível 2 resolve um problema mais básico:
   ele também não lembra de nada.
──────────────────────────────────────────────────────────────────────
"""
)
