from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import on_keyword

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="hlcm_messages",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

hlcm = on_keyword({"hlcm在"})

@hlcm.handle()
async def handle_hlcm():
    await hlcm.finish("我在")