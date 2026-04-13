from nonebot_plugin_orm import Model, get_session
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import CreateTable
from sqlalchemy import select, ForeignKey
import json
from typing import Optional

class PeopleToResponse(Model):
    __tablename__ = "people_to_response"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int]
    group_id: Mapped[int]
    emoji_id: Mapped[int]

    @classmethod
    async def get_emoji_list(cls, user_id: int, group_id: int) -> dict[int, int]:
        async with get_session() as session:
            result = await session.execute(select(cls).where(cls.user_id == user_id, cls.group_id == group_id))
            emoji_list = result.scalars().all()
            return [p.emoji_id for p in emoji_list]

    @classmethod
    async def add_person(cls, user_id: int, group_id: int, emoji_id: int):
        async with get_session() as session:
            new_person = cls(user_id=user_id, group_id=group_id, emoji_id=emoji_id)
            session.add(new_person)
            await session.commit()
    
    @classmethod
    async def remove_person(cls, user_id: int, group_id: int, emoji_id: int):
        async with get_session() as session:
            person = await session.execute(
                select(cls).where(cls.user_id == user_id, cls.group_id == group_id, cls.emoji_id == emoji_id)
            )
            person = person.scalars().first()
            if person:
                await session.delete(person)
                await session.commit()
        
    @classmethod
    async def exists(cls, user_id: int, group_id: int, emoji_id: Optional[int] = None) -> bool:
        async with get_session() as session:
            query = select(cls).where(cls.user_id == user_id, cls.group_id == group_id)
            if emoji_id is not None:
                query = query.where(cls.emoji_id == emoji_id)
            result = await session.execute(query)
            return result.scalars().first() is not None