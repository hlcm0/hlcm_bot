from nonebot import get_plugin_config, on_message
from nonebot.plugin import PluginMetadata
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)
from nonebot.matcher import Matcher
from .._bot_path import bot_file_uri, bot_local_path
from .config import Config

import os
from pathlib import Path
import asyncio
import httpx
from nonebot import require

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

cache_dir = store.get_plugin_cache_dir()

from moviepy import VideoFileClip


def convert_video_to_gif(video_name, gif_name):
    """Download a video from a URL, convert it to GIF, and save.

    Args:
        url (str): The video URL to download
        file_name (str): The base file name (without extension)
    """

    # Convert to GIF
    video_path = os.path.join(cache_dir, video_name)
    gif_path = os.path.join(cache_dir, gif_name)
    clip = VideoFileClip(video_path)
    clip.write_gif(gif_path)
    clip.close()

    logger.info("Video converted to GIF successfully!")
    return gif_path


async def download_video(video_url, video_name):
    """Download a video from a URL, and save.

    Args:
        url (str): The video URL to download
        file_name (str): The base file name (without extension)
    """

    # 确保url以http或https开头
    if not video_url.startswith("http://") and not video_url.startswith("https://"):
        video_url = "https://" + video_url

    video_path = os.path.join(cache_dir, video_name)

    # Download video
    async with httpx.AsyncClient(proxy=plugin_config.proxy.get("http"), timeout=120) as client:
        async with client.stream("GET", video_url) as response:
            response.raise_for_status()
            with open(video_path, "wb") as file:
                async for data in response.aiter_bytes(1024):
                    file.write(data)

    logger.info("Video downloaded successfully!")
    return bot_file_uri(video_path)


def _normalize_media_url(raw_url: str) -> str:
    """规范化媒体 URL，遵循 api.md 的推荐规则"""
    if not raw_url:
        return ""
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    if raw_url.startswith(("pbs.twimg.com/", "abs.twimg.com/", "video.twimg.com/")):
        return f"https://{raw_url}"
    return f"https://pbs.twimg.com/{raw_url.lstrip('/')}"


async def get_tweet(url):
    """使用单推文 API 获取推文信息
    
    API 端点: GET /<username>/status/<tweet_id>/api
    直接返回单个 tweet 对象，不需要在数组中查找
    """
    try:
        # 移除查询参数
        url = url.split("?")[0]
        # 提取路径部分: x.com/<username>/status/<id>
        parts = url.split("x.com/")[1].split("/")
        username = parts[0]
        status_id = parts[2] if len(parts) > 2 else parts[1]
        
        # 使用单推文 API 端点
        api_url = f"{plugin_config.nitter_api_base_url.rstrip('/')}/{username}/status/{status_id}/api"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(api_url)
        
        if response.status_code == 404:
            logger.error(f"推文未找到：{status_id}")
            return None
        if response.status_code != 200:
            logger.error(f"获取推文失败：{response.status_code}")
            return None
            
        data = response.json()
        
        # 检查错误响应
        if "error" in data:
            logger.error(f"API 错误：{data['error']}")
            return None
            
        # 单推文 API 直接返回 tweet 对象
        return data
    except Exception as e:
        logger.error(f"解析 URL 或获取推文时出错：{e}")
        return None


def get_twitter_video_url(tweet):
    """从推文的 media 数组中提取视频 URL
    
    根据 api.md，视频媒体有以下特点：
    - type 可能是 "video" 或 "application/x-mpegURL"
    - 实际的播放 URL 在 variants 数组中
    - 优先选择 MP4 格式中码率最高的
    """
    media_list = tweet.get("media", [])
    
    for media in media_list:
        media_type = media.get("type", "")
        # 视频类型的判断：包括 video 和 application/x-mpegURL
        if media_type in ("video", "application/x-mpegURL"):
            variants = media.get("variants", [])
            # 过滤出 MP4 格式并按码率排序
            mp4_variants = [
                v for v in variants 
                if v.get("content_type") == "video/mp4" and v.get("url")
            ]
            if mp4_variants:
                # 选择码率最高的 variant
                best_variant = max(mp4_variants, key=lambda v: v.get("bitrate", 0))
                return _normalize_media_url(best_variant["url"])
    
    return None


def get_twitter_gif_url(tweet):
    """从推文的 media 数组中提取 GIF URL
    
    根据 api.md，GIF 媒体的特点：
    - type = "gif"
    - url 通常是 video.twimg.com/... 格式（无 scheme）
    - 需要规范化为 https:// 开头
    """
    media_list = tweet.get("media", [])
    
    for media in media_list:
        if media.get("type") == "gif":
            url = media.get("url", "")
            return _normalize_media_url(url)
    
    return None


__plugin_meta__ = PluginMetadata(
    name="twitter_video_downloader",
    description="",
    usage="",
    config=Config,
)


async def contains_twitter_link(event: Event) -> bool:
    if not isinstance(event, (GroupMessageEvent, PrivateMessageEvent)):
        return False
    text = event.get_message().extract_plain_text()
    return "x.com" in text and "/status/" in text


plugin_config = get_plugin_config(Config).twitter_video_downloader


async def upload_file(
    bot: Bot, event: GroupMessageEvent, file_path: str, file_name: str
):
    try:
        await bot.call_api(
            "upload_group_file",
            group_id=event.group_id,
            file=bot_local_path(file_path),
            name=file_name,
        )
        return True
    except Exception as e:
        logger.error(f"上传文件失败：{str(e)}")
        return False


video_to_gif = on_message(priority=10, block=False, rule=contains_twitter_link)


@video_to_gif.handle()
async def _(bot: Bot, event: Event, matcher: Matcher):
    if not isinstance(event, (GroupMessageEvent, PrivateMessageEvent)):
        return
    if str(event.sender.user_id) not in plugin_config.whitelist:
        return
    url = event.get_message().extract_plain_text()

    # 获取推文信息
    tweet = await get_tweet(url)
    if tweet is None:
        await matcher.finish("无法获取推文信息，请检查链接是否正确。")

    # 判断推文是否有视频
    video_url = get_twitter_video_url(tweet)
    if video_url:
        video_uri = await download_video(video_url, "twitter_video.mp4")
        await matcher.finish(MessageSegment.video(file=video_uri))

    # 判断推文是否有gif
    gif_url = get_twitter_gif_url(tweet)
    if gif_url:
        await download_video(gif_url, "twitter_video.mp4")
        gif_path = await asyncio.to_thread(
            convert_video_to_gif,
            "twitter_video.mp4",
            "twitter_video.gif",
        )
        await matcher.finish(MessageSegment.image(file=bot_local_path(gif_path)))

    await matcher.finish("该推文不包含视频或GIF。")
