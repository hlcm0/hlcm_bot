from pydantic import BaseModel, Field


class SdvxChartConfig(BaseModel):
    resource_root: str | None = None
    music_db_path: str | None = None
    chart_root: str | None = None
    gaiji_map_path: str | None = None
    aliases_path: str | None = None


class Config(BaseModel):
    """Plugin Config Here"""
    sdvx_chart: SdvxChartConfig = Field(default_factory=SdvxChartConfig)
