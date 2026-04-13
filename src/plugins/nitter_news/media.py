from __future__ import annotations

import base64
import os
import re
import urllib.parse

import aiohttp
import requests
from nonebot.log import logger

import nonebot_plugin_localstore as store


def normalize_proxy(proxy: str) -> str:
    if not proxy.startswith("http://") and not proxy.startswith("https://"):
        return f"http://{proxy}"
    return proxy


def _media_filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    filename = "-".join(path_parts)
    query_params = urllib.parse.parse_qs(parsed.query)
    if "format" in query_params:
        filename += f".{query_params['format'][0]}"
    return filename


def download_mp4_as_gif(url: str, http_proxy: str) -> str:
    from moviepy import VideoFileClip

    cache_dir = store.get_plugin_cache_dir()
    match = re.search(r"([^/]+)(?=\.\w+$)", url)
    filename = match.group(1) if match else "nitter-gif"
    video_path = os.path.join(cache_dir, f"{filename}.mp4")
    gif_path = os.path.join(cache_dir, f"{filename}.gif")

    if os.path.exists(gif_path):
        with open(gif_path, "rb") as file:
            return base64.b64encode(file.read()).decode()

    proxy_url = normalize_proxy(http_proxy)
    response = requests.get(
        url,
        stream=True,
        proxies={"http": proxy_url, "https": proxy_url},
        timeout=60,
    )
    response.raise_for_status()

    with open(video_path, "wb") as file:
        for data in response.iter_content(1024):
            file.write(data)

    clip = VideoFileClip(video_path)
    clip.write_gif(gif_path)
    clip.close()

    with open(gif_path, "rb") as file:
        return base64.b64encode(file.read()).decode()


async def download_images_with_proxy(image_urls: list[str], http_proxy: str) -> list[str]:
    images: list[str] = []
    cache_dir = store.get_plugin_cache_dir()
    proxy_url = normalize_proxy(http_proxy)

    async with aiohttp.ClientSession() as session:
        for image_url in image_urls:
            cache_filename = _media_filename_from_url(image_url)
            cache_path = os.path.join(cache_dir, cache_filename)
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "rb") as file:
                        image_data = file.read()
                    images.append(f"base64://{base64.b64encode(image_data).decode()}")
                    continue
                except Exception as exception:
                    logger.error(f"读取缓存图片出错: {exception}, path: {cache_path}")
                    images.append(cache_path)
                    continue

            try:
                async with session.get(image_url, proxy=proxy_url, timeout=60) as response:
                    if response.status != 200:
                        logger.error(f"下载图片失败: {image_url}, 状态码: {response.status}")
                        images.append(image_url)
                        continue
                    image_data = await response.read()
            except Exception as exception:
                logger.error(f"下载图片出错: {exception}, url: {image_url}")
                images.append(image_url)
                continue

            try:
                with open(cache_path, "wb") as file:
                    file.write(image_data)
            except Exception as exception:
                logger.error(f"保存图片到缓存失败: {exception}, path: {cache_path}")

            images.append(f"base64://{base64.b64encode(image_data).decode()}")

    return images
