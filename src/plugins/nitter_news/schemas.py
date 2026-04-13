from __future__ import annotations

from dataclasses import dataclass
import json

from .models import NitterNews


@dataclass(slots=True)
class NewsPost:
    id: str
    username: str
    timestamp: int
    content: str
    image_urls: list[str]
    author: str = ""
    content_translated: str = ""
    gif_urls: list[str] | None = None
    video_urls: list[str] | None = None
    source_name: str = ""
    tweet_url: str = ""

    def __post_init__(self) -> None:
        if self.gif_urls is None:
            self.gif_urls = []
        if self.video_urls is None:
            self.video_urls = []

    @classmethod
    def from_feed_dict(cls, data: dict) -> "NewsPost":
        return cls(
            id=str(data["id"]),
            username=data["username"],
            timestamp=int(data["timestamp"]),
            content=data["content"],
            image_urls=list(data.get("image_urls", [])),
            author=data.get("author", ""),
            content_translated=data.get("content_translated", ""),
            gif_urls=list(data.get("gif_urls", [])),
            video_urls=list(data.get("video_urls", [])),
            source_name=data.get("source_name", ""),
            tweet_url=data.get("tweet_url", ""),
        )

    @classmethod
    def from_model(cls, model: NitterNews) -> "NewsPost":
        return cls(
            id=model.id,
            username="",
            timestamp=model.timestamp,
            content=model.content,
            image_urls=json.loads(model.image_urls),
            author=model.author,
            content_translated=model.content_translated,
            gif_urls=json.loads(model.gif_urls),
            video_urls=json.loads(model.video_urls),
            source_name=model.source_name,
        )

    def to_model(self) -> NitterNews:
        return NitterNews(
            id=self.id,
            source_name=self.source_name,
            timestamp=self.timestamp,
            author=self.author,
            content=self.content,
            image_urls=json.dumps(self.image_urls),
            gif_urls=json.dumps(self.gif_urls),
            video_urls=json.dumps(self.video_urls),
            content_translated=self.content_translated,
        )


@dataclass(slots=True)
class NewsSource:
    source_name: str
    username: str
