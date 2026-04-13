from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import on_command, require, get_driver, on_message
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)
from nonebot.permission import SUPERUSER

from .config import Config
from .models import PeopleToResponse
import asyncio

__plugin_meta__ = PluginMetadata(
    name="发消息时自动给ta回应",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

async def set_emoji(bot: Bot, event: GroupMessageEvent, emoji_id: str):
    try:
        await bot.call_api(
            "set_msg_emoji_like", message_id=event.message_id, emoji_id=emoji_id
        )
    except Exception as e:
        logger.error(f"[auto_response]贴{emoji_id}表情失败：{e}")

async def set_emoji_spam(bot: Bot, event: GroupMessageEvent, emoji_id: str):
    flag = True
    for _ in range(20):
        try:
            await bot.call_api(
                "set_msg_emoji_like", message_id=event.message_id, emoji_id=emoji_id, set=flag
            )
            flag = not flag
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"[auto_response]贴{emoji_id}表情失败：{e}")

async def need_response_message(event):
    user_id = event.sender.user_id
    group_id = event.group_id
    return await PeopleToResponse.exists(user_id, group_id)

response_message = on_message(priority=10, block=False, rule=need_response_message)

@response_message.handle()
async def handle_response_message(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    emoji_list = await PeopleToResponse.get_emoji_list(user_id, group_id)
    for emoji_id in emoji_list:
        await set_emoji(bot, event, emoji_id)

'''
    敲人，emoji_id = 38
'''

add_person_knock = on_command("敲我", priority=5, block=False)

@add_person_knock.handle()
async def handle_add_person(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if await PeopleToResponse.exists(user_id, group_id, 38):
        await add_person_knock.finish("哦")
    await PeopleToResponse.add_person(user_id, group_id, 38)
    await add_person_knock.finish("好，敲你")

remove_person_knock = on_command("别敲我", priority=5, block=False)

@remove_person_knock.handle()
async def handle_remove_person(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if not await PeopleToResponse.exists(user_id, group_id, 38):
        await remove_person_knock.finish("哦")
    await PeopleToResponse.remove_person(user_id, group_id, 38)
    await remove_person_knock.finish("好，不敲你")

'''
    爱人，emoji_id = 66
'''

add_person_love = on_command("爱我", priority=5, block=False)

@add_person_love.handle()
async def handle_add_person_love(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if await PeopleToResponse.exists(user_id, group_id, 66):
        await add_person_love.finish("哦")
    await PeopleToResponse.add_person(user_id, group_id, 66)
    await add_person_love.finish("好，爱你")

remove_person_love = on_command("别爱我", priority=5, block=False)

@remove_person_love.handle()
async def handle_remove_person_love(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if not await PeopleToResponse.exists(user_id, group_id, 66):
        await remove_person_love.finish("哦")
    await PeopleToResponse.remove_person(user_id, group_id, 66)
    await remove_person_love.finish("好，不爱你")

'''
    抱人，emoji_id = 49
'''

add_person_hug = on_command("抱我", priority=5, block=False)

@add_person_hug.handle()
async def handle_add_person_hug(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if await PeopleToResponse.exists(user_id, group_id, 49):
        await add_person_hug.finish("哦")
    await PeopleToResponse.add_person(user_id, group_id, 49)
    await add_person_hug.finish("好，抱你")

remove_person_hug = on_command("别抱我", priority=5, block=False)

@remove_person_hug.handle()
async def handle_remove_person_hug(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if not await PeopleToResponse.exists(user_id, group_id, 49):
        await remove_person_hug.finish("哦")
    await PeopleToResponse.remove_person(user_id, group_id, 49)
    await remove_person_hug.finish("好，不抱你")

'''
    爱死我贴表情
'''

love_to_death = on_command("爱死我", priority=5, block=False)
@love_to_death.handle()
async def handle_love_to_death(bot: Bot, event: GroupMessageEvent):
    user_id = event.sender.user_id
    group_id = event.group_id
    if not await PeopleToResponse.exists(user_id, group_id, 66):
        await PeopleToResponse.add_person(user_id, group_id, 66)
    await love_to_death.send("爱死你")
    await set_emoji_spam(bot, event, 66)
    

def check_at_messages(event: GroupMessageEvent):
    at_segments = [seg for seg in event.message if seg.type == "at"]  
    return at_segments
