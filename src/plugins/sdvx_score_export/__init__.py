from nonebot import get_plugin_config
from nonebot import require
from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)
from nonebot.matcher import Matcher
from nonebot.log import logger
from .._bot_path import bot_local_path
from .utils.score import Client, convert_to_asphyxia_format
import sys
import os
import json
import asyncio
import base64
from pathlib import Path

from .config import Config

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

__plugin_meta__ = PluginMetadata(
    name="sdvx_score_export",
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
        logger.error(f"[sdvx_score_export]贴{emoji_id}表情失败：{e}")

async def upload_file(bot: Bot, event: GroupMessageEvent, file_path: str):
    try:
        await bot.call_api(
            "upload_group_file",
            group_id=event.group_id,
            file=bot_local_path(file_path),
            name="sdvx@asphyxia.db",
        )
        return True
    except Exception as e:
        logger.error(f"[sdvx_score_export]上传文件失败：{e}")
        return False

export = on_command("export", priority=5)

file_lock = asyncio.Lock()

@export.handle()
async def handle_export(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    args = args.extract_plain_text().strip().split()
    if (not args) or len(args)<2 or len(args)>3:
        await export.finish("请输入服务器地址和卡号以导出存档\n格式为/export [服务器地址] [卡号] [版本号，可选，默认为6]")

    # 贴一个OK表情提示已开始处理请求
    await set_emoji(bot, event, "124")
    
    server_url = args[0]
    client = Client(server_url)

    card_no = args[1]
    logger.info("[sdvx_score_export]开始查询账号信息……")
    refid = client.get_refid(card_no)
    if not refid:
        logger.error("[sdvx_score_export]获取账号信息失败")
        await matcher.send("账号信息获取失败")
        return
    
    version = 6
    if len(args) == 3:
        try:
            version = int(args[2])
        except:
            await matcher.send("版本号格式错误，应为数字")
            return
    
    logger.info("[sdvx_score_export]获取到账号的refid: {}".format(refid))
    logger.info("[sdvx_score_export]开始查询分数……")
    records = client.get_score(refid, version=version)
    if not records:
        logger.error("[sdvx_score_export]获取分数失败")
        await matcher.send("分数记录获取失败")
        return

    logger.info("[sdvx_score_export]查询成功，开始转为氧无存档……")
    asphyxia_records = convert_to_asphyxia_format(records)
    await matcher.send(f"导出了{len(asphyxia_records)}条记录，开始上传文件")
    export_file = Path(store.get_plugin_cache_dir()) / "sdvx@asphyxia.db"
    export_file.parent.mkdir(parents=True, exist_ok=True)

    async with file_lock:
        with export_file.open("w", encoding="utf-8") as f:
            f.write('{"$$indexCreated":{"fieldName":"__s"}}\n{"$$indexCreated":{"fieldName":"__refid"}}\n')
            for record in asphyxia_records:
                f.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')

        if await upload_file(bot, event, str(export_file)):
            await matcher.send("上传成功，如需导入氧无请修改refid，完整导入教程可发送指令 /refid 来查看\n同时，机器人导出的存档为6代存档，不包括7代歌曲的分数，如需导出7代存档请使用网页hlcm.top")
        else:
            await matcher.send("文件上传失败")

refid = on_command("refid", priority=5)

@refid.handle()
async def handle_refid():
    image_path = Path(__file__).with_name("如何导入氧无存档.png")
    if image_path.exists():
        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        await refid.send(MessageSegment.image(f"base64://{image_data}"))
    else:
        await refid.send("未找到导入教程图片文件。")
