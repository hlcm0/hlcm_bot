from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from pydantic import BaseModel


RequiredRole = Literal["any", "superuser"]


@dataclass(slots=True)
class ToolExecutionContext:
    bot: Bot
    event: MessageEvent
    user_id: int
    group_id: int | None
    message_type: str
    is_superuser: bool


ToolHandler = Callable[[dict[str, Any], ToolExecutionContext], Awaitable[str]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    args_schema: type[BaseModel] | None = None
    required_role: RequiredRole = "any"
    enabled: bool = True


class AgentState(TypedDict, total=False):
    context: ToolExecutionContext
    available_tools: list[str]
    messages: list[BaseMessage]
    response_text: str
    error_message: str
