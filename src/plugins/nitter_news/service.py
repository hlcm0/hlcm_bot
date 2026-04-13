from __future__ import annotations

import asyncio
import time
import urllib.parse
from pathlib import Path

import aiohttp
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.log import logger
import nonebot_plugin_localstore as store

from .._bot_path import bot_file_uri
from .config import NitterNewsConfig
from .media import download_images_with_proxy, download_mp4_as_gif, normalize_proxy
from .news_util import News, Translator
from .repository import PostRepository, PushGroupRepository, SourceRepository
from .schemas import NewsPost, NewsSource


class NitterNewsService:
    def __init__(self, config: NitterNewsConfig) -> None:
        self.config = config
        self.news_client = News(config.nitter_base_url)
        self.translator = Translator(
            config.ds_api_url,
            config.ds_api_key,
            config.ds_model_name,
        )
        self.sources = SourceRepository()
        self.push_groups = PushGroupRepository()
        self.posts = PostRepository()

    async def send_news(
        self,
        bot: Bot,
        message_type: str,
        target_id: int | str,
        posts: list[NewsPost],
    ) -> None:
        bot_info = await bot.get_login_info()
        messages = []
        for post in posts:
            nodes = await self._build_forward_nodes(post, bot_info)
            messages.extend(nodes)

        if message_type == "group":
            await bot.send_group_forward_msg(group_id=int(target_id), messages=messages)
            return
        await bot.send_private_forward_msg(user_id=int(target_id), messages=messages)

    async def _build_forward_nodes(
        self, post: NewsPost, bot_info: dict
    ) -> list[dict]:
        """构建合并转发消息节点列表
        
        根据测试结果，视频必须单独作为一个节点，不能和文本混在一起
        """
        nodes = []
        date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(post.timestamp + 9 * 3600))
        prefix = f"【转发自 @{post.author}】\n" if post.author else ""
        
        # 节点 1：文本 + 图片 + GIF（不含视频）
        text_content = Message([
            MessageSegment.text(f"{prefix}[日本 {date}]\n{post.content_translated}")
        ])
        
        # 添加图片
        if post.image_urls:
            images = await download_images_with_proxy(post.image_urls, self.config.proxy["http"])
            for image in images:
                text_content.append(MessageSegment.image(image))
        
        # 添加 GIF
        if post.gif_urls:
            gif_url = post.gif_urls[0]
            try:
                base64_data = download_mp4_as_gif(gif_url, self.config.proxy["http"])
                text_content.append(MessageSegment.image(f"base64://{base64_data}"))
            except Exception as exception:
                logger.error(f"下载或转换 GIF 失败：{exception}, url: {gif_url}")
        
        nodes.append({
            "type": "node",
            "data": {
                "uin": int(bot_info["user_id"]),
                "name": bot_info["nickname"],
                "content": text_content,
            },
        })
        
        # 节点 2+：每个视频单独一个节点
        if post.video_urls:
            for video_url in post.video_urls:
                video_node = await self._create_video_node(video_url, bot_info)
                if video_node:
                    nodes.append(video_node)
        
        return nodes

    async def _create_video_node(
        self, video_url: str, bot_info: dict
    ) -> dict | None:
        """创建单独的视频节点"""
        try:
            video_file_uri = await self._download_video_to_file_uri(video_url)
            if not video_file_uri:
                return None

            return {
                "type": "node",
                "data": {
                    "uin": int(bot_info["user_id"]),
                    "name": bot_info["nickname"],
                    "content": Message([MessageSegment.video(video_file_uri)]),
                },
            }
        except Exception as exception:
            logger.error(f"下载或发送视频失败：{exception}, url: {video_url}")
            return None

    async def _download_video_to_file_uri(self, video_url: str) -> str | None:
        """下载视频并返回 file URI。"""
        proxy_url = normalize_proxy(self.config.proxy["http"])
        cache_dir = Path(store.get_plugin_cache_dir()) / "videos"
        cache_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlparse(video_url)
        filename = Path(parsed.path).name or "nitter-video.mp4"
        if parsed.query:
            query_suffix = str(abs(hash(parsed.query)))
            stem = Path(filename).stem or "nitter-video"
            suffix = Path(filename).suffix or ".mp4"
            filename = f"{stem}-{query_suffix}{suffix}"
        video_path = cache_dir / filename

        if video_path.exists():
            return bot_file_uri(video_path)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, proxy=proxy_url, timeout=120) as response:
                    if response.status != 200:
                        logger.error(f"下载视频失败：{video_url}, 状态码：{response.status}")
                        return None
                    video_data = await response.read()
                    video_path.write_bytes(video_data)
                    return bot_file_uri(video_path)
        except Exception as exception:
            logger.error(f"下载视频出错：{exception}, url: {video_url}")
            return None

    async def check_news(self, first_run: bool = False) -> None:
        logger.info("检查推文更新开始")
        for source in await self.sources.list_all():
            await self._sync_source(source, first_run)
        logger.info("检查推文更新结束")

    async def _sync_source(self, source: NewsSource, first_run: bool) -> None:
        logger.info(f"检查推文源: {source.source_name}, 用户名: {source.username}")
        try:
            fetched_posts = await asyncio.to_thread(self.news_client.recent, source.username)
            posts = [NewsPost.from_feed_dict(post) for post in fetched_posts]
            existing_ids = await self.posts.list_existing_ids([post.id for post in posts])
            new_posts: list[NewsPost] = []
            for post in posts:
                if post.id in existing_ids:
                    continue
                prepared = await self._prepare_post(source.source_name, post)
                new_posts.append(prepared)
            await self.posts.save_many(new_posts)
        except Exception as exception:
            logger.error(f"处理推文源 {source.source_name} 时出错: {exception}")
            return

        if not new_posts or first_run:
            return

        new_posts.sort(key=lambda item: item.timestamp, reverse=True)
        bot = get_bot()
        group_ids = await self.push_groups.list_by_source(source.source_name)
        logger.info(f"发现 {len(new_posts)} 条新推文，开始推送")
        for group_id in group_ids:
            try:
                await bot.send_group_msg(
                    group_id=int(group_id),
                    message=Message(f"{source.source_name}有{len(new_posts)}条新消息"),
                )
                await self.send_news(bot, "group", group_id, new_posts)
            except Exception as exception:
                logger.error(f"向群 {group_id} 推送新推文失败: {exception}")

    async def _prepare_post(self, source_name: str, post: NewsPost) -> NewsPost:
        post.source_name = source_name
        if post.content.strip():
            translated = await asyncio.to_thread(
                self.translator.translate_post,
                {
                    "id": post.id,
                    "content": post.content,
                    "image_urls": post.image_urls,
                    "gif_urls": post.gif_urls,
                    "video_urls": post.video_urls,
                    "timestamp": post.timestamp,
                    "username": post.username,
                    "author": post.author,
                    "tweet_url": post.tweet_url,
                },
            )
            post.content_translated = translated["content_translated"]
        else:
            post.content_translated = ""
        return post
