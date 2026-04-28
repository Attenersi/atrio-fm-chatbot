from __future__ import annotations

from openai import OpenAI
from .config import (
    EMBED_MODEL,
    LLM_MODEL,
    LLM_MAX_TOKENS,
    NVIDIA_API_KEY,
    NVIDIA_BASE_URL,
    NVIDIA_EMBED_API_KEY,
)


def _chat_client() -> OpenAI:
    return OpenAI(
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
    )


def _embed_client() -> OpenAI:
    return OpenAI(
        api_key=NVIDIA_EMBED_API_KEY,
        base_url=NVIDIA_BASE_URL,
    )


def chat(messages: list[dict], temperature: float = 0.2) -> str:
    client = _chat_client()
    completion = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    return completion.choices[0].message.content or ""


def chat_stream(messages: list[dict], temperature: float = 0.2):
    client = _chat_client()
    stream = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    client = _embed_client()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
        extra_body={"input_type": input_type},
    )
    return [item.embedding for item in response.data]
