import asyncio

from nonebot import get_driver, get_plugin_config, require
from nonebot.log import logger
from nonebot.plugin import PluginMetadata

from .config import Config

require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

from .handlers import register_handlers
from .service import NitterNewsService

__plugin_meta__ = PluginMetadata(
    name="nitter_news",
    description="",
    usage="",
    config=Config,
)

plugin_config = get_plugin_config(Config).nitter_news
service = NitterNewsService(plugin_config)
register_handlers(service)

_init_complete = False
_check_lock = asyncio.Lock()


@scheduler.scheduled_job("interval", minutes=2, id="check_nitter_news")
async def scheduled_check() -> None:
    if not _init_complete:
        logger.info("nitter_news 初始化未完成，跳过此次检查")
        return
    if _check_lock.locked():
        logger.info("nitter_news 上次检查未完成，跳过此次检查")
        return
    async with _check_lock:
        await service.check_news()


async def init_news_check() -> None:
    global _init_complete
    async with _check_lock:
        try:
            await service.check_news(first_run=True)
        finally:
            _init_complete = True


driver = get_driver()
driver.on_bot_connect(init_news_check)
