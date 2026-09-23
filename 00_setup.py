r"""
NÍVEL 0 — Ambiente

Objetivo: confirmar que Python, SDK, chave e provedor estão funcionando,
sem gastar um único token.

Rode com:
    .\.venv\Scripts\python.exe 00_setup.py
"""

import sys

# Força UTF-8 na saída: sem isto o console do Windows quebra os acentos.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

print("=" * 64)
print("VERIFICAÇÃO DE AMBIENTE")
print("=" * 64)

# --- 1. Python -------------------------------------------------------------
print(f"\n[1] Python {sys.version.split()[0]}")
print(f"    Executável: {sys.executable}")
if ".venv" not in sys.executable:
    print("    ⚠  Você não está usando o .venv. Rode com .\\.venv\\Scripts\\python.exe")

# --- 2. SDKs ---------------------------------------------------------------
# A trilha usa dois SDKs, um por provedor:
#   anthropic  -> fala /v1/messages (formato Anthropic)
#   openai     -> fala /v1/chat/completions (formato usado pelo OpenRouter)
print("\n[2] SDKs instalados")
faltando = []
for pacote in ("anthropic", "openai"):
    try:
        mod = __import__(pacote)
        print(f"    ✓ {pacote} {mod.__version__}")
    except ImportError:
        print(f"    ✗ {pacote} — ausente")
        faltando.append(pacote)
if faltando:
    sys.exit(
        f"\n    Instale com: .\\.venv\\Scripts\\python.exe -m pip install {' '.join(faltando)}"
    )

# --- 3. Provedor e chave ---------------------------------------------------
# `config` escolhe o provedor, valida a chave e sai com mensagem clara se faltar.
from config import (  # noqa: E402
    client,
    MODEL,
    PROVEDOR,
    erros,
    suporta,
    RECURSOS,
    preco_do_modelo,
)

print(f"\n[3] Provedor: {PROVEDOR}")
print(f"    Modelo configurado: {MODEL}")

# --- 4. Conexão ------------------------------------------------------------
# Listar modelos é a chamada mais barata que existe: não consome tokens.
# Perfeita para validar credenciais sem gastar nada.
print("\n[4] Testando conexão...")
try:
    modelos = client.models.list()
except erros.AuthenticationError:
    sys.exit("    ✗ Chave inválida ou revogada. Gere outra no painel do provedor.")
except erros.APIConnectionError:
    sys.exit("    ✗ Sem conexão com a API. Verifique internet, proxy ou VPN.")
except Exception as e:
    sys.exit(f"    ✗ {type(e).__name__}: {e}")

ids = [m.id for m in modelos.data]
print(f"    ✓ Conectado. {len(ids)} modelos disponíveis.")

if MODEL in ids:
    print(f"    ✓ '{MODEL}' existe neste provedor.")
else:
    print(f"\n    ⚠  '{MODEL}' NÃO aparece na lista deste provedor.")
    print("       Defina MODELO no .env com um dos identificadores abaixo.")

# No OpenRouter são centenas de modelos — mostramos uma amostra útil.
print("\n    Amostra do catálogo:")
if PROVEDOR == "openrouter":
    interessantes = [
        i for i in ids
        if any(p in i for p in ("anthropic/", "openai/gpt", "google/gemini", "llama"))
    ]
    for mid in interessantes[:12]:
        print(f"        {mid}")
    print(f"        ... e mais {len(ids) - len(interessantes[:12])}. "
          "Lista completa: https://openrouter.ai/models")
else:
    for mid in ids[:8]:
        print(f"        {mid}{'  <- em uso' if mid == MODEL else ''}")

# --- 5. Preço e recursos ---------------------------------------------------
if preco_do_modelo() is None:
    print(f"\n[5] ⚠  Preço de '{MODEL}' não está cadastrado em config.py.")
    print("       As aulas vão mostrar tokens, mas não o custo em dólar.")
    print("       Adicione o par (entrada, saída) em PRECOS_POR_MILHAO se quiser.")
else:
    p_in, p_out = preco_do_modelo()
    print(f"\n[5] Preço: US$ {p_in}/1M entrada, US$ {p_out}/1M saída")

print(f"\n[6] Recursos disponíveis em '{PROVEDOR}':")
for recurso in sorted(RECURSOS[PROVEDOR]):
    print(f"    {'✓' if suporta(recurso) else '—'} {recurso}")

if PROVEDOR == "openrouter":
    print(
        """
    Os marcados com — são específicos da API da Anthropic. As aulas que
    dependem deles vão avisar e seguir em frente, sem quebrar.
    Para ver essas partes funcionando, rode com PROVEDOR=anthropic."""
    )

print("\n" + "=" * 64)
print("Tudo certo. Próximo: 01_primeira_chamada.py")
print("=" * 64)
