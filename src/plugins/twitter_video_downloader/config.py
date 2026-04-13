from pydantic import BaseModel, Field


class TwitterVideoDownloaderConfig(BaseModel):
    whitelist: list[str] = Field(default_factory=list)
    proxy: dict[str, str] = Field(
        default_factory=lambda: {
            "http": "http://127.0.0.1:7897",
            "https": "http://127.0.0.1:7897",
        }
    )
    nitter_api_base_url: str = "http://127.0.0.1:1145"


class Config(BaseModel):
    """Plugin Config Here"""

    twitter_video_downloader: TwitterVideoDownloaderConfig
