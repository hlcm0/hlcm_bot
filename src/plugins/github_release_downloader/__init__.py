import asyncio
from pathlib import Path

import httpx
from nonebot import get_driver, get_plugin_config, require
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata
from nonebot.plugin import on_fullmatch

from .._bot_path import bot_local_path
from .config import Config

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="github_release_downloader",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config).github_release_downloader
file_lock = asyncio.Lock()
last_checked_release: str | None = None


def _cache_path(release_name: str) -> Path:
    cache_dir = Path(store.get_plugin_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{release_name}.zip"


async def _fetch_latest_kfc_release() -> dict | None:
    url = f"https://api.github.com/repos/{config.repo}/releases"
    async with httpx.AsyncClient(
        proxy=config.proxy.get("http"),
        timeout=config.timeout,
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        releases = response.json()

    for release in releases:
        release_name = release.get("name", "")
        if release_name.startswith("kfc"):
            return release
    return None


async def _download_file(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(
        proxy=config.proxy.get("http"),
        timeout=None,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    file.write(chunk)


async def _ensure_release_archive(release: dict) -> Path:
    download_path = _cache_path(release["name"])
    if download_path.exists():
        return download_path

    await _download_file(release["zipball_url"], download_path)
    return download_path


async def upload_file(bot: Bot, group_id: int, file_path: Path, file_name: str) -> bool:
    try:
        await bot.call_api(
            "upload_group_file",
            group_id=group_id,
            file=bot_local_path(file_path),
            name=file_name,
        )
        return True
    except Exception as exception:
        logger.error(f"上传文件失败：{exception}")
        return False


download_new_plugin = on_fullmatch("最新氧无插件", priority=5)


@download_new_plugin.handle()
async def handle_download_new_plugin(bot: Bot, event: Event, matcher: Matcher) -> None:
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("这个命令暂时只能在群聊里使用。")

    try:
        latest_release = await _fetch_latest_kfc_release()
    except Exception as exception:
        logger.error(f"获取最新 release 失败：{exception}")
        await matcher.finish("获取最新版本失败，请稍后重试。")

    if not latest_release:
        await matcher.finish("没有找到符合条件的 release。")

    async with file_lock:
        download_path = await _ensure_release_archive(latest_release)

    release_name = latest_release["name"]
    release_body = (latest_release.get("body") or "").splitlines()
    release_summary = release_body[0] if release_body else release_name
    if await upload_file(bot, event.group_id, download_path, f"{release_name}.zip"):
        await matcher.finish(release_summary)
    await matcher.finish("上传群文件失败")


async def check_new_release(bot: Bot | None = None, on_startup: bool = False) -> None:
    global last_checked_release
    logger.info("检查新氧无插件版本中...")

    try:
        latest_release = await _fetch_latest_kfc_release()
    except Exception as exception:
        logger.error(f"检查 release 失败：{exception}")
        return

    if not latest_release:
        logger.warning("未找到符合条件的 release")
        return

    release_name = latest_release["name"]
    if release_name == last_checked_release:
        return

    logger.info(f"发现新版本：{release_name}")
    last_checked_release = release_name

    async with file_lock:
        try:
            download_path = await _ensure_release_archive(latest_release)
        except Exception as exception:
            logger.error(f"下载 release 失败：{exception}")
            return

    if on_startup or not bot:
        return

    release_body = (latest_release.get("body") or "").splitlines()
    version = release_body[0] if release_body else release_name
    version_number = ""
    if "(" in version and ")" in version:
        version_number = version[version.find("(") + 1 : version.find(")")]
    upload_name = f"{release_name}({version_number}).zip" if version_number else f"{release_name}.zip"

    for group_id in config.push_group:
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=Message(f"发现新版本氧无插件：{version}"),
            )
            await upload_file(bot, group_id, download_path, upload_name)
        except Exception as exception:
            logger.error(f"上传新版本失败：{exception}")


@scheduler.scheduled_job("interval", minutes=30, id="check_new_release")
async def scheduled_check() -> None:
    bots = get_driver().bots
    bot = next(iter(bots.values()), None)
    await check_new_release(bot=bot)


async def init_releases_check(bot: Bot) -> None:
    await check_new_release(bot=bot, on_startup=True)


driver = get_driver()
driver.on_bot_connect(init_releases_check)
