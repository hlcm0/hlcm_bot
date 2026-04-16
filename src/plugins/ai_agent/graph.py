from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.compat import type_validate_python
from nonebot.adapters.onebot.v11 import Message

from .registry import can_execute_tool, get_args_schema, list_tools
from .types import AgentState, ToolExecutionContext
from .safety import ANTI_POLITICAL_POLICY, ANTI_SEXUAL_POLICY

async def _get_reply_message_id(bot: Bot, message: dict[str, Any]) -> int | None:
    message_object = message.get("message", None)
    if message_object is None:
        return None
    for segment in message_object:
        if segment.get("type") == "reply":
            reply_id = segment.get("data",{}).get("id", None)
            if reply_id is not None:
                try:
                    reply_id = int(reply_id)
                except ValueError:
                    logger.warning(f"消息 {message} 的 reply id {reply_id} 不是有效的整数")
                    return None
                return reply_id
    return None
        

async def build_initial_messages(
    bot: Bot,
    event: MessageEvent,
    system_prompt: str,
    first_ai_message: str,
    maximum_context_window: int,
) -> list[BaseMessage] | None:
    bot_id = bot.self_id
    message_id = event.message_id
    message_list: list[BaseMessage] = []
    while len(message_list) < maximum_context_window:
        message = await bot.get_msg(message_id=message_id)
        if not message:
            logger.warning(f"消息 ID {message_id} 不存在，无法获取消息内容。")
            return None
        sender = message.get("sender", None)
        if not sender:
            logger.warning(f"消息 ID {message_id} 没有 sender 字段，无法判断发送者。")
            return None
        user_id = sender.get("user_id", None)
        if not user_id:
            logger.warning(f"消息 ID {message_id} 的 sender 字段没有 user_id，无法判断发送者。")
            return None
        user_id = str(user_id)
        nickname = sender.get("nickname", "")
        if not nickname:
            logger.warning(f"消息 ID {message_id} 的 sender 字段没有 nickname，使用QQ号 {user_id} 代替。")
            nickname = f"用户{user_id}"
        message_segment_list = message.get("message", None)
        if not message_segment_list:
            logger.warning(f"消息 ID {message_id} 没有 message 字段，无法获取消息内容。")
            return None
        message_object = type_validate_python(Message, message_segment_list)
        plain_text = message_object.extract_plain_text()
        if not plain_text:
            logger.warning(f"消息 ID {message_id} 的 message 字段无法提取纯文本，使用空字符串代替。")
            plain_text = ""
        if user_id == bot_id:
            message_list.append(AIMessage(content=plain_text))
        else:
            message_list.append(HumanMessage(content=f"{nickname}: {plain_text}"))
        
        message_id = await _get_reply_message_id(bot, message)
        if not message_id:
            break

    return [
        SystemMessage(
            content=(
                f"{system_prompt}\n"
                "用户的消息格式为“昵称: 消息内容”。"
                "如需获取结果，优先调用工具。"
                "工具返回后请结合结果继续判断是否还需要调用其他工具，多次充分获取信息后，再回答。"
                "总结输出工具结果时，要全面，不要省略细节，不要删改。"
                "如果你不确定答案，请明确说“我不确定”，不要猜测或编造。"
                "所有结论必须基于已知信息或提供的上下文。"
                "回复时不要使用markdown格式。"
            )
        ),
        AIMessage(content=first_ai_message),
    ] + message_list[::-1]


class GraphState(AgentState):
    messages: Annotated[list[Any], add_messages]
    political_detected: bool
    sexual_detected: bool


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


def build_agent_graph(llm: Any, safeguard_llm: Any, tools: list[StructuredTool]) -> Any:
    model = llm.bind_tools(tools) if tools else llm

    async def political_detector(state: GraphState) -> dict[str, bool]:
        messages = [
            SystemMessage(content=ANTI_POLITICAL_POLICY),
            state["messages"][-1],
        ]
        response = await safeguard_llm.ainvoke(messages)
        logger.info(f"政治检测结果: {response.content}")
        return {"political_detected": "1" in response.content}
    
    async def sexual_detector(state: GraphState) -> dict[str, bool]:
        messages = [
            SystemMessage(content=ANTI_SEXUAL_POLICY),
            state["messages"][-1],
        ]
        response = await safeguard_llm.ainvoke(messages)
        logger.info(f"色情检测结果: {response.content}")
        return {"sexual_detected": "1" in response.content}
    
    async def should_continue_process(state: GraphState) -> str:
        if state["political_detected"]:
            return "end"
        if state["sexual_detected"]:
            return "end"
        return "continue"

    async def model_call(state: GraphState) -> dict[str, list[Any]]:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}
    
    def should_continue_tool(state: GraphState) -> str:
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tool"
        return "end"

    graph = StateGraph(GraphState)
    graph.add_node("political_detector", political_detector)
    graph.add_node("sexual_detector", sexual_detector)
    graph.add_node("router", lambda state: state)
    graph.add_node("our_agent", model_call)
    graph.add_node("tools", ToolNode(tools=tools))
    graph.add_edge(START, "political_detector")
    graph.add_edge(START, "sexual_detector")
    graph.add_edge(["political_detector", "sexual_detector"], "router")
    graph.add_conditional_edges(
        "router",
        should_continue_process,
        {
            "continue": "our_agent",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "our_agent",
        should_continue_tool,
        {
            "tool": "tools",
            "end": END,
        },
    )
    graph.add_edge("tools", "our_agent")
    return graph.compile()
