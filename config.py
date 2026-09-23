"""
Configuração compartilhada por todas as aulas.

Escolhe o PROVEDOR, monta o cliente certo e diz às aulas quais recursos
existem ali. Tudo o mais na trilha continua escrito em um formato só.

    PROVEDOR=anthropic    -> API da Anthropic (SDK anthropic), só modelos Claude
    PROVEDOR=openrouter   -> OpenRouter (SDK openai), qualquer modelo do catálogo
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. Acentuação no console do Windows
# ---------------------------------------------------------------------------
# O terminal do Windows ainda usa cp1252 por padrão, e "NÍVEL" vira "N�VEL".
# Estas linhas forçam UTF-8 na saída. Em Linux/macOS são inofensivas.

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")  # mensagens de erro também

# ---------------------------------------------------------------------------
# 1. Carregar o .env
# ---------------------------------------------------------------------------
# Um `.env` é só um arquivo texto com `CHAVE=valor` por linha. Existem
# bibliotecas para isso (python-dotenv), mas são 8 linhas — dá para ver
# como funciona.


def carregar_env(caminho: Path = Path(__file__).parent / ".env") -> None:
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        # `setdefault`: uma variável já definida no sistema vence o .env
        os.environ.setdefault(chave.strip(), valor.strip())


carregar_env()

# ---------------------------------------------------------------------------
# 2. Qual provedor?
# ---------------------------------------------------------------------------
# Se você não disser, deduzimos pela chave que existe.

CHAVE_ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CHAVE_OPENROUTER = os.environ.get("OPENROUTER_API_KEY", "").strip()

PROVEDOR = os.environ.get("PROVEDOR", "").strip().lower()
if not PROVEDOR:
    PROVEDOR = "anthropic" if CHAVE_ANTHROPIC else ("openrouter" if CHAVE_OPENROUTER else "")

if PROVEDOR not in ("anthropic", "openrouter"):
    sys.exit(
        "\n[ERRO] Nenhum provedor configurado.\n"
        "  1. Copie o .env.example para .env\n"
        "  2. Preencha UMA das opções:\n"
        "       ANTHROPIC_API_KEY=sk-ant-...    (console.anthropic.com)\n"
        "       OPENROUTER_API_KEY=sk-or-...    (openrouter.ai/keys)\n"
    )

# ---------------------------------------------------------------------------
# 3. O modelo
# ---------------------------------------------------------------------------
# No OpenRouter o identificador tem a forma "fornecedor/modelo".
# Rode 00_setup.py para ver a lista real disponível na sua conta.

MODELOS_PADRAO = {
    "anthropic": "claude-opus-5",
    "openrouter": "anthropic/claude-sonnet-4.5",
}
MODEL = os.environ.get("MODELO", "").strip() or MODELOS_PADRAO[PROVEDOR]

# ---------------------------------------------------------------------------
# 4. O cliente, e as exceções do SDK correspondente
# ---------------------------------------------------------------------------
# Os dois SDKs expõem classes de erro com os MESMOS nomes (BadRequestError,
# RateLimitError, APIStatusError...). Por isso as aulas podem escrever
# `erros.RateLimitError` e funcionar nos dois provedores.

if PROVEDOR == "anthropic":
    if not CHAVE_ANTHROPIC:
        sys.exit("\n[ERRO] PROVEDOR=anthropic mas ANTHROPIC_API_KEY está vazia.\n")
    import anthropic as erros  # noqa: N813  (namespace de exceções)

    client = erros.Anthropic()

else:
    if not CHAVE_OPENROUTER:
        sys.exit("\n[ERRO] PROVEDOR=openrouter mas OPENROUTER_API_KEY está vazia.\n")
    import openai as erros  # noqa: N813

    from provedor import ClienteOpenRouter

    client = ClienteOpenRouter(api_key=CHAVE_OPENROUTER)

# ---------------------------------------------------------------------------
# 5. O que este provedor sabe fazer
# ---------------------------------------------------------------------------

from provedor import RECURSOS, RecursoIndisponivel  # noqa: E402,F401


def suporta(recurso: str) -> bool:
    """As aulas perguntam isto antes de tentar algo que pode não existir."""
    return RECURSOS[PROVEDOR].get(recurso, False)


def avisar_indisponivel(recurso: str, o_que_perde: str) -> None:
    """Degradação com aviso: a aula continua, mas você sabe o que ficou de fora."""
    print(
        f"\n  ⚠ '{recurso}' não existe em PROVEDOR={PROVEDOR}."
        f"\n    {o_que_perde}"
        f"\n    Para ver esta parte funcionando, rode com PROVEDOR=anthropic.\n"
    )


# ---------------------------------------------------------------------------
# 6. Custo
# ---------------------------------------------------------------------------
# Preços em dólares por 1 milhão de tokens (entrada, saída).
# No OpenRouter cada modelo tem o seu — a lista abaixo cobre alguns comuns.
# Se o seu não estiver aqui, o custo aparece como indisponível em vez de zero:
# um zero mentiroso é pior que um "não sei".

PRECOS_POR_MILHAO = {
    # Anthropic direto
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenRouter (confira em openrouter.ai/models — mudam com frequência)
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "anthropic/claude-opus-4.5": (5.00, 25.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "meta-llama/llama-3.3-70b-instruct": (0.12, 0.30),
}


def preco_do_modelo(modelo: str = MODEL):
    return PRECOS_POR_MILHAO.get(modelo)


def mostrar_custo(resposta, prefixo: str = "") -> None:
    entrada = resposta.usage.input_tokens
    saida = resposta.usage.output_tokens
    precos = preco_do_modelo()
    if precos is None:
        print(f"{prefixo}[tokens: {entrada} entrada + {saida} saída | preço de "
              f"'{MODEL}' não cadastrado em config.py]")
        return
    p_in, p_out = precos
    total = (entrada / 1_000_000 * p_in) + (saida / 1_000_000 * p_out)
    print(f"{prefixo}[tokens: {entrada} entrada + {saida} saída | ~US$ {total:.5f}]")


def cabecalho() -> None:
    """Toda aula imprime isto no começo, para você nunca confundir onde rodou."""
    print(f"[provedor: {PROVEDOR} | modelo: {MODEL}]")
