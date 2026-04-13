from __future__ import annotations

import asyncio

from nonebot_plugin_orm import get_session
from sqlalchemy import delete, event, select
from sqlalchemy.engine import Engine

from .models import NitterNews, NitterPushConfig, NitterSource
from .schemas import NewsPost, NewsSource


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class SourceRepository:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    async def add(self, source_name: str, username: str) -> bool:
        async with self.lock:
            async with get_session() as session:
                existing = await session.get(NitterSource, source_name)
                if existing is not None:
                    return False
                session.add(NitterSource(source_name=source_name, username=username))
                await session.commit()
                return True

    async def remove(self, source_name: str) -> bool:
        async with self.lock:
            async with get_session() as session:
                source = await session.get(NitterSource, source_name)
                if source is None:
                    return False
                await session.delete(source)
                await session.commit()
                return True

    async def list_all(self) -> list[NewsSource]:
        async with self.lock:
            async with get_session() as session:
                result = await session.execute(select(NitterSource).order_by(NitterSource.source_name))
                return [
                    NewsSource(source_name=item.source_name, username=item.username)
                    for item in result.scalars().all()
                ]

    async def as_mapping(self) -> dict[str, str]:
        sources = await self.list_all()
        return {source.source_name: source.username for source in sources}


class PushGroupRepository:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    async def add(self, source_name: str, group_id: str) -> bool:
        async with self.lock:
            async with get_session() as session:
                source = await session.get(NitterSource, source_name)
                if source is None:
                    return False
                result = await session.execute(
                    select(NitterPushConfig).where(
                        NitterPushConfig.source_name == source_name,
                        NitterPushConfig.group_id == group_id,
                    )
                )
                if result.scalar_one_or_none() is not None:
                    return False
                session.add(NitterPushConfig(source_name=source_name, group_id=group_id))
                await session.commit()
                return True

    async def remove(self, source_name: str, group_id: str) -> bool:
        async with self.lock:
            async with get_session() as session:
                result = await session.execute(
                    select(NitterPushConfig).where(
                        NitterPushConfig.source_name == source_name,
                        NitterPushConfig.group_id == group_id,
                    )
                )
                push_config = result.scalar_one_or_none()
                if push_config is None:
                    return False
                await session.delete(push_config)
                await session.commit()
                return True

    async def list_by_source(self, source_name: str) -> list[str]:
        async with self.lock:
            async with get_session() as session:
                result = await session.execute(
                    select(NitterPushConfig.group_id)
                    .where(NitterPushConfig.source_name == source_name)
                    .order_by(NitterPushConfig.group_id)
                )
                return list(result.scalars().all())


class PostRepository:
    async def exists(self, post_id: str) -> bool:
        async with get_session() as session:
            return await session.get(NitterNews, post_id) is not None

    async def list_existing_ids(self, post_ids: list[str]) -> set[str]:
        if not post_ids:
            return set()
        async with get_session() as session:
            result = await session.execute(select(NitterNews.id).where(NitterNews.id.in_(post_ids)))
            return set(result.scalars().all())

    async def save_many(self, posts: list[NewsPost]) -> None:
        if not posts:
            return
        async with get_session() as session:
            session.add_all([post.to_model() for post in posts])
            await session.commit()

    async def list_recent(self, source_name: str, limit: int) -> list[NewsPost]:
        async with get_session() as session:
            result = await session.execute(
                select(NitterNews)
                .where(NitterNews.source_name == source_name)
                .order_by(NitterNews.timestamp.desc())
                .limit(limit)
            )
            return [NewsPost.from_model(item) for item in result.scalars().all()]

    async def clear(self) -> None:
        async with get_session() as session:
            await session.execute(delete(NitterNews))
            await session.commit()
