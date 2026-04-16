from nonebot import get_plugin_config, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me

from .config import AiAgentConfig, Config
from .runtime import AiAgentRuntime

__plugin_meta__ = PluginMetadata(
    name="ai_agent",
    description="LangGraph-based AI agent runtime for @bot natural language interactions.",
    usage="@机器人 + 自然语言",
    config=Config,
)

try:
    config = get_plugin_config(Config).ai_agent
except ValueError:
    config = AiAgentConfig()

agent_runtime = AiAgentRuntime(config)

try:
    ai_chat = on_message(rule=to_me(), priority=20, block=False)

    @ai_chat.handle()
    async def handle_ai_chat(bot: Bot, event: MessageEvent) -> None:
        if ai_chat is None:
            return
        response = await agent_runtime.run(bot, event)
        if response:
            await ai_chat.send(response, reply_message=True)
except ValueError:
    ai_chat = None
