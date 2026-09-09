"""explain package — Deterministic facts, templates, and providers for joulectrl."""

from explain.facts import extract_explanation_facts
from explain.providers import (
    BasicProvider,
    CloudOpenAIProvider,
    ExplanationProvider,
    LocalLlamaProvider,
    get_provider,
)
from explain.templates import generate_explanation

__all__ = [
    "BasicProvider",
    "CloudOpenAIProvider",
    "ExplanationProvider",
    "LocalLlamaProvider",
    "extract_explanation_facts",
    "generate_explanation",
    "get_provider",
]
