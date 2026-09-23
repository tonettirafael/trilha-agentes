r"""
provedor.py — a camada que faz a trilha rodar em dois mundos

A Anthropic e o OpenRouter falam PROTOCOLOS DIFERENTES:

    Anthropic   POST /v1/messages          blocos de conteúdo, tool_use/tool_result
    OpenRouter  POST /v1/chat/completions  strings + tool_calls (formato OpenAI)

Os CONCEITOS são os mesmos — loop do agente, ferramentas, histórico. Só a
embalagem muda. Este arquivo traduz a embalagem, para que as aulas continuem
ensinando um modelo mental só.

Ler este arquivo é opcional na primeira passada. Mas quando você for integrar
qualquer LLM na vida real, é exatamente este mapeamento que vai precisar fazer —
então vale voltar aqui depois do nível 4.

MAPA DA TRADUÇÃO

    Anthropic                         ->  OpenAI / OpenRouter
    system="..." (parâmetro à parte)  ->  primeira mensagem role="system"
    content = [blocos]                ->  content = string
    bloco tool_use {id,name,input}    ->  tool_calls[].function{name,arguments}
    bloco tool_result (role user)     ->  mensagem role="tool" (UMA POR RESULTADO)
    tools[].input_schema              ->  tools[].function.parameters
    stop_reason end_turn/tool_use     ->  finish_reason stop/tool_calls
    usage.input_tokens                ->  usage.prompt_tokens
"""

import json
from dataclasses import dataclass, field
from typing import Any


class RecursoIndisponivel(RuntimeError):
    """O provedor atual não oferece esse recurso. As aulas capturam e avisam."""


# Quais recursos cada provedor suporta. As aulas consultam isto ANTES de tentar
# algo que pode não existir, em vez de quebrar no meio da lição.
RECURSOS = {
    "anthropic": {
        "contagem_tokens": True,    # /v1/messages/count_tokens
        "metricas_cache": True,     # cache_creation/cache_read no usage
        "cache_control": True,      # prompt caching explícito
        "tool_runner": True,        # loop automático do SDK (nível 5)
        "saida_estruturada": True,  # messages.parse com Pydantic
        "compactacao": True,        # context editing / compaction (beta)
        "listar_modelos": True,
    },
    "openrouter": {
        "contagem_tokens": False,   # não há endpoint equivalente
        "metricas_cache": False,    # o formato OpenAI não devolve esses campos
        "cache_control": False,     # exigiria o endpoint nativo /api/v1/messages
        "tool_runner": False,       # é um helper do SDK da Anthropic, não da API
        "saida_estruturada": True,  # via response_format json_schema (varia por modelo)
        "compactacao": False,       # beta exclusivo da API da Anthropic
        "listar_modelos": True,
    },
}


# ---------------------------------------------------------------------------
# Blocos: o formato da Anthropic, reconstruído a partir da resposta OpenAI.
# As aulas fazem `for bloco in resposta.content: if bloco.type == "text"`.
# Estas classes garantem que isso continue funcionando nos dois provedores.
# ---------------------------------------------------------------------------


@dataclass
class BlocoTexto:
    text: str
    type: str = "text"


@dataclass
class BlocoFerramenta:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class Uso:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Resposta:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Uso = field(default_factory=Uso)
    model: str = ""


# ---------------------------------------------------------------------------
# Tradução: Anthropic -> OpenAI (o pedido)
# ---------------------------------------------------------------------------


def _ferramentas_para_openai(ferramentas):
    if not ferramentas:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": f["name"],
                "description": f.get("description", ""),
                "parameters": f.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for f in ferramentas
    ]


def _attr(bloco: Any, nome: str, padrao=None):
    """Blocos chegam ora como objeto (nosso ou do SDK), ora como dict."""
    if isinstance(bloco, dict):
        return bloco.get(nome, padrao)
    return getattr(bloco, nome, padrao)


def _mensagens_para_openai(mensagens: list, system) -> list:
    saida = []

    # Diferença 1: na Anthropic o system é um parâmetro separado.
    # No formato OpenAI ele é a primeira mensagem da lista.
    if system:
        texto_system = (
            system
            if isinstance(system, str)
            else "\n".join(_attr(b, "text", "") for b in system)
        )
        saida.append({"role": "system", "content": texto_system})

    for msg in mensagens:
        papel, conteudo = msg["role"], msg["content"]

        if isinstance(conteudo, str):
            saida.append({"role": papel, "content": conteudo})
            continue

        textos, chamadas, resultados = [], [], []
        for bloco in conteudo:
            tipo = _attr(bloco, "type")

            if tipo == "text":
                textos.append(_attr(bloco, "text", ""))

            elif tipo == "tool_use":
                # Diferença 2: argumentos viajam como STRING JSON, não como objeto.
                chamadas.append(
                    {
                        "id": _attr(bloco, "id"),
                        "type": "function",
                        "function": {
                            "name": _attr(bloco, "name"),
                            "arguments": json.dumps(_attr(bloco, "input", {}) or {}),
                        },
                    }
                )

            elif tipo == "tool_result":
                # Diferença 3, a mais traiçoeira: na Anthropic TODOS os resultados
                # vão em UMA mensagem de usuário. No formato OpenAI cada resultado
                # é uma MENSAGEM SEPARADA com role="tool".
                resultados.append(
                    {
                        "role": "tool",
                        "tool_call_id": _attr(bloco, "tool_use_id"),
                        "content": str(_attr(bloco, "content", "")),
                    }
                )

            elif tipo == "thinking":
                pass  # raciocínio não tem equivalente no formato OpenAI

        if resultados:
            saida.extend(resultados)
        elif papel == "assistant":
            entrada = {"role": "assistant", "content": "\n".join(textos) or None}
            if chamadas:
                entrada["tool_calls"] = chamadas
            saida.append(entrada)
        else:
            saida.append({"role": papel, "content": "\n".join(textos)})

    return saida


# ---------------------------------------------------------------------------
# Tradução: OpenAI -> Anthropic (a resposta)
# ---------------------------------------------------------------------------

_MOTIVOS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def _resposta_para_anthropic(bruta) -> Resposta:
    escolha = bruta.choices[0]
    msg = escolha.message
    blocos = []

    if getattr(msg, "content", None):
        blocos.append(BlocoTexto(text=msg.content))

    for chamada in getattr(msg, "tool_calls", None) or []:
        try:
            argumentos = json.loads(chamada.function.arguments or "{}")
        except json.JSONDecodeError:
            # Modelos menores às vezes devolvem JSON quebrado. Melhor entregar
            # dict vazio e deixar a ferramenta reclamar do que estourar aqui.
            argumentos = {}
        blocos.append(
            BlocoFerramenta(id=chamada.id, name=chamada.function.name, input=argumentos)
        )

    u = getattr(bruta, "usage", None)
    uso = Uso(
        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
        output_tokens=getattr(u, "completion_tokens", 0) or 0,
    )
    detalhes = getattr(u, "prompt_tokens_details", None)
    if detalhes is not None:
        uso.cache_read_input_tokens = getattr(detalhes, "cached_tokens", 0) or 0

    motivo = _MOTIVOS.get(escolha.finish_reason or "stop", "end_turn")
    # Se veio pedido de ferramenta, isso manda: alguns modelos devolvem
    # finish_reason="stop" mesmo tendo chamado ferramenta.
    if any(b.type == "tool_use" for b in blocos):
        motivo = "tool_use"

    return Resposta(
        content=blocos,
        stop_reason=motivo,
        usage=uso,
        model=getattr(bruta, "model", ""),
    )


# ===========================================================================
# O CLIENTE ADAPTADO
# ===========================================================================
# Expõe a mesma superfície que as aulas já usam do SDK da Anthropic:
#   client.messages.create(...)   client.messages.stream(...)
#   client.messages.parse(...)    client.messages.count_tokens(...)
#   client.models.list()          client.with_options(...)


class _Stream:
    """Contexto de streaming com a mesma interface do SDK da Anthropic."""

    def __init__(self, gerador_openai):
        self._bruto = gerador_openai
        self._pedacos = []
        self._final = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    @property
    def text_stream(self):
        for evento in self._bruto:
            if not evento.choices:
                continue
            delta = evento.choices[0].delta
            pedaco = getattr(delta, "content", None)
            if pedaco:
                self._pedacos.append(pedaco)
                yield pedaco

    def get_final_message(self) -> Resposta:
        if self._final is None:
            texto = "".join(self._pedacos)
            self._final = Resposta(
                content=[BlocoTexto(text=texto)] if texto else [],
                stop_reason="end_turn",
                usage=Uso(),  # o streaming do formato OpenAI nem sempre devolve usage
            )
        return self._final


class _Messages:
    def __init__(self, dono):
        self._dono = dono

    # -- a chamada principal ------------------------------------------------
    def create(self, *, model, max_tokens, messages, system=None, tools=None,
               cache_control=None, tool_choice=None, **extras):
        # `cache_control`, `thinking`, `output_config`, `betas` e afins são
        # específicos da Anthropic. Descartamos em silêncio no corpo da
        # requisição — mas `config.suporta()` já avisou a aula antes de chegar aqui.
        extras.pop("thinking", None)
        extras.pop("output_config", None)
        extras.pop("betas", None)
        extras.pop("context_management", None)

        argumentos = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": _mensagens_para_openai(messages, system),
        }
        ferramentas = _ferramentas_para_openai(tools)
        if ferramentas:
            argumentos["tools"] = ferramentas
        if tool_choice:
            argumentos["tool_choice"] = "required" if tool_choice.get("type") == "any" else "auto"

        bruta = self._dono._oai.chat.completions.create(**argumentos)
        return _resposta_para_anthropic(bruta)

    # -- streaming ----------------------------------------------------------
    def stream(self, *, model, max_tokens, messages, system=None, tools=None, **extras):
        gerador = self._dono._oai.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=_mensagens_para_openai(messages, system),
            stream=True,
        )
        return _Stream(gerador)

    # -- saída estruturada --------------------------------------------------
    def parse(self, *, model, max_tokens, messages, output_format, system=None, **extras):
        """Equivalente ao messages.parse da Anthropic, via response_format."""
        esquema = output_format.model_json_schema()
        esquema["additionalProperties"] = False

        bruta = self._dono._oai.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=_mensagens_para_openai(messages, system),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_format.__name__,
                    "strict": True,
                    "schema": esquema,
                },
            },
        )
        texto = bruta.choices[0].message.content or "{}"
        resultado = _resposta_para_anthropic(bruta)
        # Nem todo modelo no OpenRouter honra json_schema. Se vier lixo, a aula
        # precisa saber disso em vez de receber um objeto meia-boca.
        try:
            resultado.parsed_output = output_format.model_validate_json(texto)
        except Exception as e:
            raise RecursoIndisponivel(
                f"o modelo '{model}' não devolveu JSON válido para o esquema "
                f"{output_format.__name__} ({type(e).__name__}). "
                "Escolha um modelo com suporte a structured outputs."
            ) from e
        return resultado

    # -- não existe do lado OpenAI -----------------------------------------
    def count_tokens(self, **_):
        raise RecursoIndisponivel(
            "o OpenRouter não expõe um endpoint de contagem de tokens. "
            "Use o campo `usage` da resposta para medir depois do fato."
        )


class _Modelos:
    def __init__(self, dono):
        self._dono = dono

    def list(self):
        return self._dono._oai.models.list()


class ClienteOpenRouter:
    """Fala formato OpenAI por baixo, formato Anthropic por cima."""

    def __init__(self, api_key: str, timeout: float = 600.0, max_retries: int = 2,
                 referer: str = "https://localhost/trilha-agentes",
                 titulo: str = "Trilha de Agentes"):
        from openai import OpenAI

        self._oai = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            # Cabeçalhos opcionais do OpenRouter: identificam seu app nos rankings.
            default_headers={"HTTP-Referer": referer, "X-Title": titulo},
        )
        self._config = {"api_key": api_key, "timeout": timeout, "max_retries": max_retries}
        self.messages = _Messages(self)
        self.models = _Modelos(self)

    def with_options(self, **novas):
        config = {**self._config, **novas}
        return ClienteOpenRouter(**config)
