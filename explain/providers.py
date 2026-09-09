"""explain/providers.py — Explanation provider interfaces and adapters for joulectrl.

Per PLAN §10:
- Provider Selector: Basic (default, offline), Local model, Cloud API.
- If an LLM fails or times out, fall back to Basic.
- Never silently send data to the cloud.
- The LLM has no path to control; it only explains grounded facts.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
import urllib.request
import urllib.error

from explain.templates import generate_explanation

logger = logging.getLogger("joulectrl.explain")

GROUNDING_SYSTEM_PROMPT = (
    "You are an explanation assistant for joulectrl, a Linux CPU energy profiling tool.\n"
    "Your duty is to explain the provided experimental facts in clear, plain language.\n"
    "Grounding Rules:\n"
    "1. Only state facts directly present in the provided JSON.\n"
    "2. Do NOT invent, extrapolate, or alter any numbers, percentages, or measurements.\n"
    "3. Do NOT claim hardware causes that are not explicitly confirmed by the experiment.\n"
    "4. Do NOT make future performance guarantees.\n"
    "5. Keep the explanation concise and professional (2 to 3 short paragraphs)."
)


class ExplanationProvider(ABC):
    """Abstract base class for explanation generators."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def explain(self, facts: dict[str, Any]) -> str:
        """Generate an explanation text given grounded facts."""
        ...


class BasicProvider(ExplanationProvider):
    """Deterministic, offline rule-based explanation provider (guaranteed default)."""

    @property
    def name(self) -> str:
        return "basic"

    def explain(self, facts: dict[str, Any]) -> str:
        return generate_explanation(facts)


class LocalLlamaProvider(ExplanationProvider):
    """Local llama.cpp compatible endpoint provider (e.g. 127.0.0.1:8081)."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:8081/v1/chat/completions",
        model: str = "local-model",
        timeout_s: float = 8.0,
    ):
        self.endpoint_url = endpoint_url
        self.model = model
        self.timeout_s = timeout_s
        self._fallback = BasicProvider()

    @property
    def name(self) -> str:
        return "local_llama"

    def explain(self, facts: dict[str, Any]) -> str:
        """Query local model; falls back to Basic on any error or timeout."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Explain the following experiment outcome:\n{json.dumps(facts, indent=2)}"},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        try:
            req = urllib.request.Request(
                self.endpoint_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"].strip()
                    if content:
                        return content
        except Exception as e:
            logger.warning("Local LLM provider failed (%s), falling back to Basic provider.", e)

        # Fallback to basic
        return self._fallback.explain(facts)


class CloudOpenAIProvider(ExplanationProvider):
    """Generic OpenAI-compatible cloud provider (explicit opt-in)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_s: float = 10.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._fallback = BasicProvider()

    @property
    def name(self) -> str:
        return "cloud_openai"

    def explain(self, facts: dict[str, Any]) -> str:
        """Query cloud API; falls back to Basic on error or timeout."""
        if not self.api_key:
            return self._fallback.explain(facts)

        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Explain the following experiment outcome:\n{json.dumps(facts, indent=2)}"},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"].strip()
                    if content:
                        return content
        except Exception as e:
            logger.warning("Cloud LLM provider failed (%s), falling back to Basic provider.", e)

        return self._fallback.explain(facts)


def get_provider(provider_type: str = "basic", **kwargs: Any) -> ExplanationProvider:
    """Factory to instantiate explanation provider."""
    ptype = provider_type.lower()
    if ptype == "local" or ptype == "local_llama":
        return LocalLlamaProvider(
            endpoint_url=kwargs.get("endpoint_url", "http://127.0.0.1:8081/v1/chat/completions"),
            model=kwargs.get("model", "local-model"),
        )
    elif ptype == "cloud" or ptype == "cloud_openai":
        return CloudOpenAIProvider(
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", "https://api.openai.com/v1"),
            model=kwargs.get("model", "gpt-4o-mini"),
        )
    else:
        return BasicProvider()
