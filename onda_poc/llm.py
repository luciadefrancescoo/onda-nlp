"""Generación de candidatos con un LLM vía API compatible con OpenAI.

Sirve con OpenAI, Groq, OpenRouter, Together, y modelos locales con Ollama
(LLM_BASE_URL=http://localhost:11434/v1) o LM Studio.
"""

from __future__ import annotations

import json
import re

from .http import HttpClient

SYSTEM = (
    "Sos un curador musical. Recomendás canciones reales que existen en "
    "servicios de streaming. Nunca inventes canciones ni artistas."
)

USER_TEMPLATE = """Escenario: "{scenario}"

Proponé exactamente {n} canciones distintas que encajen con el escenario.
Priorizá música conocida salvo que el escenario pida otra cosa.
Respondé SOLO con JSON, sin texto extra, con este formato:
{{"canciones": [{{"artista": "...", "titulo": "..."}}]}}
Usá el artista principal (sin "feat.") y el título tal como figura en streaming."""


def build_messages(scenario: str, n: int) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER_TEMPLATE.format(scenario=scenario, n=n)},
    ]


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Devuelve el objeto JSON de la respuesta, tolerando <think>, ``` y texto alrededor."""
    text = _THINK.sub("", text or "")
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("La respuesta no contiene JSON")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("El JSON no es un objeto")
    return data


def parse_candidates(text: str) -> list[dict]:
    """Extrae [{'artist','title'}] de la respuesta del modelo, tolerando ruido.

    Ignora bloques <think>…</think> de modelos con razonamiento visible.
    """
    data = extract_json(text)
    items = data.get("canciones") or data.get("songs") or data.get("tracks") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        artist = it.get("artista") or it.get("artist") or ""
        title = it.get("titulo") or it.get("título") or it.get("title") or ""
        if artist.strip() and title.strip():
            out.append({"artist": artist.strip(), "title": title.strip()})
    return out


# Tope de tokens de salida. 30 canciones en JSON son ~600 tokens; sin tope, un
# modelo que se queda "pensando" puede generar decenas de miles hasta el timeout.
MAX_TOKENS = 4096


def chat_json(http: HttpClient, messages: list[dict], base_url: str, model: str, parse,
              api_key: str | None = None, temperature: float = 0.3, attempts: int = 3,
              reasoning_effort: str | None = "none", max_tokens: int = MAX_TOKENS,
              cache_prefix: str = "llm"):
    """Pide una respuesta JSON y la pasa por parse(texto). Reintenta si no sirve.

    Intenta modo JSON; si el servidor no lo soporta, sigue sin él.
    reasoning_effort="none" apaga el razonamiento de modelos como gemma4 o qwen3
    (si no, gastan todos los tokens pensando y la respuesta llega vacía). Si el
    servidor no acepta el parámetro, se saca. None = no mandarlo.
    Cada intento usa su propia clave de caché, así un reintento no repite la respuesta mala.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{base_url.rstrip('/')}/chat/completions"
    json_mode = True
    last_error = ""
    attempt = 0
    while attempt < attempts:
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        r = http.post(url, json_body=body, headers=headers,
                      cache_tag=f"{cache_prefix}:{model}:{attempt}:{json_mode}:{reasoning_effort}:{max_tokens}")
        if r.status in (400, 422) and (reasoning_effort or json_mode):
            # El servidor rechaza un parámetro opcional: primero el razonamiento, después el JSON.
            if reasoning_effort:
                reasoning_effort = None
            else:
                json_mode = False
            continue  # no cuenta como intento
        attempt += 1
        if not r.ok or not r.data:
            raise RuntimeError(f"LLM http {r.status}: {r.data}")
        choice = r.data["choices"][0]
        content = choice["message"].get("content") or ""
        if not content.strip() and choice.get("finish_reason") == "length":
            last_error = (f"respuesta vacía: el modelo usó los {max_tokens} tokens "
                          "razonando (probá LLM_REASONING_EFFORT=none)")
            continue
        try:
            out = parse(content)
            if out:
                return out
            last_error = "respuesta sin datos"
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            last_error = f"{e}: {content[:200]!r}"
    raise ValueError(f"No se pudo obtener una respuesta válida tras {attempts} intentos ({last_error})")


def generate(http: HttpClient, scenario: str, n: int, base_url: str, model: str,
             api_key: str | None = None, temperature: float = 0.3,
             attempts: int = 3, reasoning_effort: str | None = "none",
             max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Pide n canciones directamente al LLM (el enfoque original, ver `build` para el nuevo)."""
    return chat_json(http, build_messages(scenario, n), base_url, model, parse_candidates,
                     api_key=api_key, temperature=temperature, attempts=attempts,
                     reasoning_effort=reasoning_effort, max_tokens=max_tokens, cache_prefix="llm")
