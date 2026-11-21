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


def parse_candidates(text: str) -> list[dict]:
    """Extrae [{'artist','title'}] de la respuesta del modelo, tolerando ruido.

    Ignora bloques <think>…</think> de modelos con razonamiento visible.
    """
    text = _THINK.sub("", text or "")
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("La respuesta no contiene JSON")
    data = json.loads(text[start:end + 1])
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


def generate(http: HttpClient, scenario: str, n: int, base_url: str, model: str,
             api_key: str | None = None, temperature: float = 0.3,
             attempts: int = 3) -> list[dict]:
    """Pide n canciones. Intenta modo JSON; si el servidor no lo soporta, sigue sin él.

    Si la respuesta no se puede parsear, reintenta (sin usar la caché de ese intento).
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{base_url.rstrip('/')}/chat/completions"
    json_mode = True
    last_error = ""
    for attempt in range(attempts):
        body = {"model": model, "messages": build_messages(scenario, n), "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = http.post(url, json_body=body, headers=headers,
                      cache_tag=f"llm:{model}:{attempt}:{json_mode}")
        if r.status in (400, 422) and json_mode:
            json_mode = False  # el servidor no acepta response_format
            continue
        if not r.ok or not r.data:
            raise RuntimeError(f"LLM http {r.status}: {r.data}")
        content = r.data["choices"][0]["message"].get("content") or ""
        try:
            out = parse_candidates(content)
            if out:
                return out
            last_error = "JSON sin canciones"
        except (ValueError, json.JSONDecodeError) as e:
            last_error = f"{e}: {content[:200]!r}"
    raise ValueError(f"No se pudo obtener una lista válida tras {attempts} intentos ({last_error})")
