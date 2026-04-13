from pydantic import BaseModel, Field


class NitterNewsConfig(BaseModel):
    ds_api_url: str
    ds_api_key: str
    ds_model_name: str
    proxy: dict[str, str] = Field(
        default_factory=lambda: {
            "http": "http://127.0.0.1:7897",
            "https": "http://127.0.0.1:7897",
        }
    )
    nitter_base_url: str = "http://127.0.0.1:1145"


class Config(BaseModel):
    """Plugin Config Here"""

    nitter_news: NitterNewsConfig
