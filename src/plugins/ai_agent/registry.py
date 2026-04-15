from __future__ import annotations

from pydantic import BaseModel, create_model

from .types import ToolExecutionContext, ToolSpec

_TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    if spec.name in _TOOL_REGISTRY:
        raise ValueError(f"Tool '{spec.name}' is already registered")
    _TOOL_REGISTRY[spec.name] = spec


def get_tool(name: str) -> ToolSpec | None:
    return _TOOL_REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    return [_TOOL_REGISTRY[name] for name in sorted(_TOOL_REGISTRY)]


def can_execute_tool(spec: ToolSpec, context: ToolExecutionContext) -> bool:
    if not spec.enabled:
        return False
    if spec.required_role == "superuser":
        return context.is_superuser
    return True


def get_args_schema(spec: ToolSpec) -> type[BaseModel]:
    if spec.args_schema is not None:
        return spec.args_schema
    return create_model(f"{spec.name.replace('.', '_')}_args")
