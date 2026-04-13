from nonebot_plugin_orm import Model, get_session
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import CreateTable
from sqlalchemy import select, ForeignKey
import json

class NitterNews(Model):
    __tablename__ = "nitter_news"
    id: Mapped[str] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(ForeignKey('nitter_source.source_name', ondelete='CASCADE'))
    timestamp: Mapped[int]
    author: Mapped[str]
    content: Mapped[str]
    image_urls: Mapped[str]
    gif_urls: Mapped[str]
    video_urls: Mapped[str]
    content_translated: Mapped[str]

class NitterPushConfig(Model):
    __tablename__ = "nitter_push_config"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[str]
    source_name: Mapped[str] = mapped_column(ForeignKey('nitter_source.source_name', ondelete='CASCADE'))

class NitterSource(Model):
    __tablename__ = "nitter_source"
    source_name: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str]
