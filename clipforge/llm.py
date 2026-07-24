from __future__ import annotations
import json
import re
from abc import ABC, abstractmethod
from typing import Callable

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> dict: ...
    @abstractmethod
    def generate_text(self, prompt: str) -> str: ...


def _default_gemini_client(model: str, api_key: str):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)


class GeminiProvider(LLMProvider):
    def __init__(self, model: str, api_key: str,
                 client_factory: Callable[[str, str], object] = _default_gemini_client):
        self._model = client_factory(model, api_key)

    def _raw(self, prompt: str) -> str:
        try:
            resp = self._model.generate_content(prompt) # type: ignore
            return resp.text
        except Exception as e:  # quota, network, safety blocks
            raise LLMError(str(e)) from e

    def generate_text(self, prompt: str) -> str:
        return self._raw(prompt)

    def generate_json(self, prompt: str) -> dict:
        text = self._raw(prompt).strip()
        m = _FENCE.search(text)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from LLM: {e}") from e


def get_provider(provider: str, model: str, api_key: str) -> LLMProvider:
    if provider == "gemini":
        return GeminiProvider(model, api_key)
    raise ValueError(f"unknown llm provider: {provider}")
