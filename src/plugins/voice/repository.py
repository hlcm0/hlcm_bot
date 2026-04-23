from __future__ import annotations

import asyncio
import time

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import VoiceRecord

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"


class VoiceRepository:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    async def get(self, name: str) -> VoiceRecord | None:
        async with get_session() as session:
            return await session.get(VoiceRecord, name)

    async def exists(self, name: str) -> bool:
        return await self.get(name) is not None

    async def add_pending(
        self,
        *,
        name: str,
        filename: str,
        original_filename: str,
        submitter_id: int,
    ) -> bool:
        async with self.lock:
            async with get_session() as session:
                if await session.get(VoiceRecord, name) is not None:
                    return False
                session.add(
                    VoiceRecord(
                        name=name,
                        filename=filename,
                        original_filename=original_filename,
                        status=STATUS_PENDING,
                        submitter_id=submitter_id,
                        created_at=int(time.time()),
                        approved_at=None,
                    )
                )
                await session.commit()
                return True

    async def list_all(self) -> list[VoiceRecord]:
        async with get_session() as session:
            result = await session.execute(select(VoiceRecord).order_by(VoiceRecord.name))
            return list(result.scalars().all())

    async def approve(self, name: str) -> VoiceRecord | None:
        async with self.lock:
            async with get_session() as session:
                record = await session.get(VoiceRecord, name)
                if record is None:
                    return None
                record.status = STATUS_APPROVED
                record.approved_at = int(time.time())
                await session.commit()
                await session.refresh(record)
                return record

    async def delete(self, name: str) -> VoiceRecord | None:
        async with self.lock:
            async with get_session() as session:
                record = await session.get(VoiceRecord, name)
                if record is None:
                    return None
                snapshot = VoiceRecord(
                    name=record.name,
                    filename=record.filename,
                    original_filename=record.original_filename,
                    status=record.status,
                    submitter_id=record.submitter_id,
                    created_at=record.created_at,
                    approved_at=record.approved_at,
                )
                await session.delete(record)
                await session.commit()
                return snapshot

    async def get_approved(self, name: str) -> VoiceRecord | None:
        async with get_session() as session:
            record = await session.get(VoiceRecord, name)
            if record is None or record.status != STATUS_APPROVED:
                return None
            return record
