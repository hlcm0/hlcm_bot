from __future__ import annotations

from langchain_openrouter import ChatOpenRouter
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr

from .config import AiAgentConfig


class AgentConfigurationError(RuntimeError):
    """Raised when AI agent config is incomplete."""


def build_chat_model(config: AiAgentConfig) -> ChatOpenRouter | ChatDeepSeek:
    if not config.provider:
        raise AgentConfigurationError("missing provider")
    if not config.api_key:
        raise AgentConfigurationError("missing api_key")
    if not config.model:
        raise AgentConfigurationError("missing model")
    if not config.temperature:
        raise AgentConfigurationError("missing temperature")
    if not config.max_tokens:
        raise AgentConfigurationError("missing max_tokens")

    if config.provider == "openrouter":
        return ChatOpenRouter(
            api_key=SecretStr(config.api_key),
            model=config.model,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    elif config.provider == "deepseek":
        return ChatDeepSeek(
            api_key=SecretStr(config.api_key),
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    else:
        raise AgentConfigurationError(f"unsupported provider: {config.provider}")

def build_safeguard_model(config: AiAgentConfig) -> ChatOpenRouter | ChatDeepSeek:
    if not config.provider:
        raise AgentConfigurationError("missing provider")
    if not config.api_key:
        raise AgentConfigurationError("missing api_key")
    if not config.safeguard_model:
        raise AgentConfigurationError("missing safeguard_model")
    if not config.safeguard_temperature:
        raise AgentConfigurationError("missing safeguard_temperature")
    if not config.max_tokens:
        raise AgentConfigurationError("missing max_tokens")
    
    if config.provider == "openrouter":
        return ChatOpenRouter(
            api_key=SecretStr(config.api_key),
            model=config.safeguard_model,
            base_url=config.base_url,
            temperature=config.safeguard_temperature,
            max_tokens=100,
        )
    elif config.provider == "deepseek":
        return ChatDeepSeek(
            api_key=SecretStr(config.api_key),
            model=config.safeguard_model,
            temperature=config.safeguard_temperature,
            max_tokens=100,
        )
    else:
        raise AgentConfigurationError(f"unsupported provider: {config.provider}")