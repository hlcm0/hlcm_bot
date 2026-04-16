from __future__ import annotations

import re

from markdown_it import MarkdownIt
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger

from .config import AiAgentConfig
from .graph import build_agent_graph, build_graph_tools, build_initial_messages
from .llm import AgentConfigurationError, build_chat_model, build_safeguard_model
from .registry import list_tools
from .types import AgentState, ToolExecutionContext

_MARKDOWN = MarkdownIt()


# def md_to_text(content: str) -> str:
#     tokens = _MARKDOWN.parse(content)
#     parts: list[str] = []
#     for token in tokens:
#         if token.type == "inline" and token.children:
#             inline_parts: list[str] = []
#             for child in token.children:
#                 if child.type in {"text", "code_inline"} and child.content:
#                     inline_parts.append(child.content)
#             if inline_parts:
#                 parts.append("".join(inline_parts))
#         elif token.type in {"code_block", "fence"} and token.content:
#             parts.append(token.content)
#         elif token.type in {"softbreak", "hardbreak"}:
#             parts.append("\n")

#     text = "\n".join(part.strip() for part in parts if part and part.strip())
#     text = re.sub(r"\n{3,}", "\n\n", text)
#     return text.strip()


class AiAgentRuntime:
    def __init__(self, config: AiAgentConfig) -> None:
        self.config = config
        self._llm = None
        self._safeguard_llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = build_chat_model(self.config)
        return self._llm
    
    def _get_safeguard_llm(self):
        if self._safeguard_llm is None:
            self._safeguard_llm = build_safeguard_model(self.config)
        return self._safeguard_llm

    def _build_context(self, bot: Bot, event: MessageEvent) -> ToolExecutionContext:
        superusers = {str(item) for item in getattr(get_driver().config, "superusers", set())}
        user_id = int(event.get_user_id())
        group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
        return ToolExecutionContext(
            bot=bot,
            event=event,
            user_id=user_id,
            group_id=group_id,
            message_type=event.message_type,
            is_superuser=str(user_id) in superusers,
        )

    async def run(self, bot: Bot, event: MessageEvent) -> str | None:
        if not self.config.enabled:
            return None
        
        text = event.get_plaintext().strip()
        if not text:
            return "可以直接 @我 然后告诉我你的问题。"

        try:
            context = self._build_context(bot, event)
            tools = build_graph_tools(context)
            app = build_agent_graph(self._get_llm(), self._get_safeguard_llm(), tools)
            messages = await build_initial_messages(bot, event, self.config.system_prompt, self.config.first_ai_message, self.config.maximum_context_window)
            if messages is None:
                return "构建消息记录失败了，请稍后再试。"
            state: AgentState = {
                "context": context,
                "available_tools": [tool.name for tool in list_tools() if tool.enabled],
                "messages": messages,
            }
            logger.info(messages)
            result = await app.ainvoke(state)
        except AgentConfigurationError:
            return "AI Agent 配置不完整，暂时无法使用。"
        except Exception as exception:
            logger.exception(f"AI Agent 运行过程中出现错误: {exception}")
            return "AI Agent 运行过程中出现错误，请稍后再试。"

        if result["political_detected"]:
            return "抱歉，您的消息中包含政治敏感内容，无法生成回复。"
        if result["sexual_detected"]:
            return "抱歉，您的消息中包含色情内容，无法生成回复。"
        messages = result.get("messages", [])
        if not messages:
            return "回复生成失败了，请稍后再试。"

        final_message = messages[-1]
        response_text = getattr(final_message, "content", "")
        if isinstance(response_text, list):
            response_text = "\n".join(
                item.get("text", "")
                for item in response_text
                if isinstance(item, dict) and item.get("type") == "text"
            )
        logger.info(f"AI Agent 最终回复原始内容: {response_text}")
        # response_text = md_to_text(str(response_text))
        return response_text or "回复生成失败了，请稍后再试。"
