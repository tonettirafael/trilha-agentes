r"""
NÍVEL 2 — Estado: a API não lembra de nada

A API é STATELESS (sem estado). Cada chamada começa do zero absoluto.
Não existe "sessão" do lado da Anthropic. Se o modelo parece lembrar da
conversa, é porque VOCÊ reenviou o histórico inteiro na requisição.

Isso tem três consequências que definem o design de todo agente:

  1. Memória é responsabilidade sua. Você guarda e reenvia.
  2. Cada turno custa mais que o anterior — o histórico só cresce.
  3. O contexto tem limite. Conversa longa demais precisa ser gerenciada.

Rode com:
    .\.venv\Scripts\python.exe 02_conversa.py
"""

from config import (
    client,
    MODEL,
    mostrar_custo,
    cabecalho,
    suporta,
    avisar_indisponivel,
)

cabecalho()

# ===========================================================================
# PARTE A — A prova de que não há memória
# ===========================================================================

print("=" * 70)
print("A) Duas chamadas independentes: o modelo não conecta uma à outra")
print("=" * 70)

client.messages.create(
    model=MODEL,
    max_tokens=200,
    messages=[{"role": "user", "content": "Meu nome é Rafael e trabalho com logística."}],
)

r2 = client.messages.create(
    model=MODEL,
    max_tokens=200,
    messages=[{"role": "user", "content": "Qual é o meu nome?"}],  # histórico não foi enviado
)
print("\nPergunta: Qual é o meu nome?")
print("Resposta:", next(b.text for b in r2.content if b.type == "text"))


# ===========================================================================
# PARTE B — Memória = você reenvia a lista
# ===========================================================================
# A "memória" é literalmente uma lista Python que você mantém e reenvia.
# Note o padrão: toda resposta do modelo volta para a lista como `assistant`.

print("\n" + "=" * 70)
print("B) Agora com histórico")
print("=" * 70)


class Conversa:
    """O gerenciador de histórico mais simples que funciona."""

    def __init__(self, system: str | None = None):
        self.system = system
        self.mensagens: list[dict] = []

    def enviar(self, texto_usuario: str) -> str:
        # 1. Registra o que o usuário disse
        self.mensagens.append({"role": "user", "content": texto_usuario})

        # 2. Manda a conversa INTEIRA, sempre
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=self.system,
            messages=self.mensagens,
        )

        texto = next((b.text for b in resposta.content if b.type == "text"), "")

        # 3. Registra o que o modelo respondeu — senão o próximo turno
        #    não saberá o que ele mesmo disse
        self.mensagens.append({"role": "assistant", "content": texto})

        mostrar_custo(resposta, prefixo="    ")
        return texto


conversa = Conversa(system="Você é direto. Máximo 2 frases por resposta.")

for pergunta in [
    "Meu nome é Rafael e trabalho com logística.",
    "Qual é o meu nome?",
    "E com o que eu trabalho mesmo?",
]:
    print(f"\n[você] {pergunta}")
    print(f"[bot ] {conversa.enviar(pergunta)}")


# ===========================================================================
# PARTE C — O custo escondido
# ===========================================================================
# Repare nos números de tokens de entrada acima: eles SOBEM a cada turno,
# mesmo quando sua pergunta é curtíssima. Você está pagando pelo histórico
# inteiro, de novo, em toda chamada.

print("\n" + "=" * 70)
print("C) O histórico acumulado")
print("=" * 70)

print(f"\nMensagens na memória: {len(conversa.mensagens)}")

# `count_tokens` calcula o tamanho SEM fazer a chamada (e sem custo).
# Use isso antes de mandar contexto grande, para não tomar susto.
#
# Só a API da Anthropic tem esse endpoint. No OpenRouter você só descobre
# o tamanho DEPOIS de pagar pela chamada, lendo o `usage` da resposta.
if suporta("contagem_tokens"):
    contagem = client.messages.count_tokens(
        model=MODEL,
        system=conversa.system,
        messages=conversa.mensagens,
    )
    print(f"Tokens que a PRÓXIMA chamada já vai gastar só de histórico: "
          f"{contagem.input_tokens}")
else:
    avisar_indisponivel(
        "contagem_tokens",
        "Você não consegue medir o prompt ANTES de enviar — só depois, "
        "pelo `usage`.",
    )
    print("  Alternativa neste provedor: some `resposta.usage.input_tokens` "
          "das chamadas já feitas.")

print(
    """
──────────────────────────────────────────────────────────────────────
   Três problemas que nascem aqui, e onde cada um é resolvido:

   "reenviar sempre custa caro"     -> prompt caching        (nível 6)
   "o histórico não cabe mais"      -> compactação/resumo    (nível 6)
   "quero lembrar entre execuções"  -> memória persistente   (nível 6)

   Mas nada disso importa enquanto o agente não souber AGIR.
   Próximo: 03_primeira_tool.py — o coração de tudo.
──────────────────────────────────────────────────────────────────────
"""
)
