from __future__ import annotations

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class VoiceRecord(Model):
    __tablename__ = "voice_records"

    name: Mapped[str] = mapped_column(primary_key=True)
    filename: Mapped[str]
    original_filename: Mapped[str]
    status: Mapped[str]
    submitter_id: Mapped[int]
    created_at: Mapped[int]
    approved_at: Mapped[int | None] = mapped_column(nullable=True)
