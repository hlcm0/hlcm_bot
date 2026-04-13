from pydantic import BaseModel, Field

class GitHubReleaseDownloaderConfig(BaseModel):
    repo: str = "22vv0/asphyxia_plugins"
    push_group: list[int] = Field(default_factory=list)
    proxy: dict[str, str] = Field(
        default_factory=lambda: {
            "http": "http://127.0.0.1:7897",
            "https": "http://127.0.0.1:7897",
        }
    )
    timeout: float = 30.0

class Config(BaseModel):
    """Plugin Config Here"""
    github_release_downloader: GitHubReleaseDownloaderConfig
