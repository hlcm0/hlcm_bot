from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from nonebot.log import logger

from .registry import can_execute_tool, get_args_schema, list_tools
from .types import AgentState, ToolExecutionContext


def build_initial_messages(
    input_text: str,
    system_prompt: str,
    first_ai_message: str,
    context: ToolExecutionContext,
) -> list[BaseMessage]:
    return [
        SystemMessage(
            content=(
                f"{system_prompt}\n"
                "如需获取结果，优先调用工具。"
                "工具返回后请结合结果继续判断是否还需要调用其他工具，多次充分获取信息后，再回答。"
                "总结输出工具结果时，要全面，不要省略细节，不要删改。"
                "如果你不确定答案，请明确说“我不确定”，不要猜测或编造。"
                "所有结论必须基于已知信息或提供的上下文。"
                "回复时不要使用markdown格式。"
            )
        ),
        AIMessage(content=first_ai_message),
        HumanMessage(content=input_text),
    ]


class GraphState(AgentState):
    messages: Annotated[list[Any], add_messages]


def build_graph_tools(context: ToolExecutionContext) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    for spec in list_tools():
        if not spec.enabled:
            continue

        async def tool_coroutine(
            _spec=spec,
            _context=context,
            **kwargs: Any,
        ) -> str:
            if not can_execute_tool(_spec, _context):
                result = f"工具{_spec.name}无权限执行。"
                logger.info(f"工具{_spec.name}无权限执行。")
                return result
            try:
                result = await _spec.handler(kwargs, _context)
            except Exception as exception:
                logger.exception(f"工具{_spec.name}执行失败，参数{kwargs}，错误信息{exception}")
                raise
            show_result = result
            if isinstance(result, str):
                show_result = show_result[:1000] + "..." if len(show_result) > 1000 else show_result
                show_result = show_result.replace("\n", "\\n")
            logger.info(f"工具{_spec.name}执行成功，参数{kwargs}，结果{show_result}")
            return result

        tools.append(
            StructuredTool.from_function(
                coroutine=tool_coroutine,
                name=spec.name,
                description=spec.description,
                args_schema=get_args_schema(spec),
            )
        )
    return tools


def should_continue(state: GraphState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool"
    return "end"


def build_agent_graph(llm: Any, tools: list[StructuredTool]) -> Any:
    model = llm.bind_tools(tools) if tools else llm

    async def model_call(state: GraphState) -> dict[str, list[Any]]:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(GraphState)
    graph.add_node("our_agent", model_call)
    graph.add_node("tools", ToolNode(tools=tools))
    graph.add_edge(START, "our_agent")
    graph.add_conditional_edges(
        "our_agent",
        should_continue,
        {
            "tool": "tools",
            "end": END,
        },
    )
    graph.add_edge("tools", "our_agent")
    return graph.compile()
