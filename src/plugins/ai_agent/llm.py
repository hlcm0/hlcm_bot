from __future__ import annotations

from langchain_openrouter import ChatOpenRouter
from pydantic import SecretStr

from .config import AiAgentConfig


class AgentConfigurationError(RuntimeError):
    """Raised when AI agent config is incomplete."""


def build_chat_model(config: AiAgentConfig) -> ChatOpenRouter:
    if not config.api_key:
        raise AgentConfigurationError("missing api_key")
    if not config.model:
        raise AgentConfigurationError("missing model")

    return ChatOpenRouter(
        api_key=SecretStr(config.api_key),
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
