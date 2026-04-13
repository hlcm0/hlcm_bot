from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from nonebot.log import logger
from openai import OpenAI


def _normalize_media_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    if raw_url.startswith(("pbs.twimg.com/", "abs.twimg.com/", "video.twimg.com/")):
        return f"https://{raw_url}"
    return f"https://pbs.twimg.com/{raw_url.lstrip('/')}"


def _parse_timestamp(created_at: str) -> int:
    return int(datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def _best_video_url(media: dict) -> str:
    variants = media.get("variants") or []
    mp4_variants = [
        variant
        for variant in variants
        if variant.get("content_type") == "video/mp4" and variant.get("url")
    ]
    if mp4_variants:
        best = max(
            mp4_variants,
            key=lambda item: (item.get("bitrate", 0), item.get("resolution", 0)),
        )
        return _normalize_media_url(best["url"])
    return _normalize_media_url(media.get("url", ""))


def _extract_plain_text(tweet: dict, base_url: str) -> str:
    source_tweet = tweet.get("retweet") or tweet
    text = (source_tweet.get("text") or "").strip()
    html = (source_tweet.get("html") or "").strip()

    candidate = text
    if "<" in candidate and ">" in candidate:
        candidate = html or candidate

    if not html and ("<" not in candidate or ">" not in candidate):
        return candidate

    soup = BeautifulSoup(html or candidate, "html.parser")
    for link in soup.find_all("a"):
        href = (link.get("href") or "").strip()
        label = link.get_text(" ", strip=True)
        if label.startswith("#"):
            link.replace_with(label)
            continue
        link.replace_with(href if href else label)
    return soup.get_text(" ", strip=True)


def _extract_author(tweet: dict, username: str) -> str:
    source_tweet = tweet.get("retweet") or tweet
    user = source_tweet.get("user") or {}
    author = user.get("username", "")
    if author == username:
        return ""
    return author


class News:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.base_host = urlparse(self.base_url).netloc

    def recent(self, username: str) -> list[dict]:
        response = requests.get(f"{self.base_url}/{username}/api", timeout=30)
        response.raise_for_status()
        data = response.json()
        tweets = data.get("tweets", [])
        posts = []

        for tweet in tweets:
            if not tweet.get("available", True):
                continue
            author = _extract_author(tweet, username)

            image_urls: list[str] = []
            gif_urls: list[str] = []
            video_urls: list[str] = []

            for media in tweet.get("media") or []:
                media_type = media.get("type")
                if media_type == "photo":
                    normalized = _normalize_media_url(media.get("url", ""))
                    if normalized and "card_img" not in normalized:
                        image_urls.append(normalized)
                elif media_type == "gif":
                    normalized = _normalize_media_url(media.get("url", ""))
                    if normalized:
                        gif_urls.append(normalized)
                else:
                    video_url = _best_video_url(media)
                    if video_url:
                        video_urls.append(video_url)

            post = {
                "id": str(tweet["id"]),
                "content": _extract_plain_text(tweet, self.base_url),
                "image_urls": image_urls,
                "gif_urls": gif_urls,
                "video_urls": video_urls,
                "timestamp": _parse_timestamp(tweet["created_at"]),
                "username": username,
                "author": author,
                "tweet_url": tweet.get("url") or urljoin(self.base_url + "/", f"{username}/status/{tweet['id']}") ,
            }
            posts.append(post)

        return posts


class Translator:
    def __init__(self, ds_api_url: str, ds_api_key: str, ds_model_name: str) -> None:
        self.ds_api_url = ds_api_url
        self.ds_api_key = ds_api_key
        self.ds_model_name = ds_model_name
        self.system_prompt = (
            "【翻译注意事项】你是一个翻译助手，需要将下述的推文外文翻译成中文。注意保持原贴文的可爱格式和语气，保留原文的各种颜文字和emoji。只需要给出译文，不要给出任何解释，有时待翻译的内容是空的，直接回复一个空格即可。"
            "部分专有名词翻译："
            "1.ポラリスコード Polaris Chord "
            "2.ボルテ SDVX "
            "3.スタンダードスタート Standard Start "
            "4.コナステ 家用版 "
            "5.ひなビタ 日向美 "
            "6.hinabitter 日向美 "
            "部分游戏角色名："
            "1.レイシス Rasis "
            "2.つまぶき 乳贴精 "
            "3.マキシマ 大老师 "
            "4.グレイス Grace "
            "5.ニア Near "
            "6.ノア Noah "
            "对于部分歌名和日语专有名词请不要翻译【翻译注意事项说明结束】"
        )
        self.translate_prefix = "现在，请你将以下内容翻译成中文："

    def translate_post(self, post: dict) -> dict:
        post_id = post["id"]
        logger.info(f"ID{post_id}开始翻译")

        client = OpenAI(base_url=self.ds_api_url, api_key=self.ds_api_key)
        messages = client.chat.completions.create(
            model=self.ds_model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.translate_prefix + post["content"]},
            ],
            stream=False,
        )
        post["content_translated"] = messages.choices[0].message.content
        return post
