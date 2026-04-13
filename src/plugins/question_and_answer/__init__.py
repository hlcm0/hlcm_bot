from nonebot import get_plugin_config, on_message, on_command
from nonebot.rule import to_me
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
import base64
import httpx, ssl
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)

from nonebot import require 
require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="question_and_answer",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
data_dir = store.get_plugin_data_dir()

async def get_pic_from_url(url):
    SSL_CONTEXT = ssl.create_default_context()
    SSL_CONTEXT.set_ciphers('DEFAULT')
    User_Agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        "AppleWebKit/537.36 (KHTML, like Gecko)"
        "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
    )
    async with httpx.AsyncClient(verify=SSL_CONTEXT) as client:
        response = await client.get(url, headers={"User-Agent": User_Agent})
        response.raise_for_status()
        content = response.content
        return base64.b64encode(content).decode("ascii")

save_answer = on_command("answer", priority=5, permission=SUPERUSER)
answer_question = on_message(priority=10, rule=to_me(), block=True)
answer_list = on_command("answer_list", priority=5, permission=SUPERUSER)
delete_answer = on_command("delete_answer", priority=5, permission=SUPERUSER)

@save_answer.handle()
async def handle_save_answer(bot: Bot, event: Event, args: Message = CommandArg()):
    question = args.extract_plain_text().strip()
    if not question:
        await save_answer.finish("请提供问题")
        return
    if not event.reply:
        await save_answer.finish("请回复一个消息来提供答案")
        return
    answer = []
    for item in event.reply.message:
        if item.type == "text":
            answer.append({"type": "text", "content": item.data["text"]})
            continue

        if item.type == "image":
            image_url = item.data.get("url")
            if not image_url:
                continue
            base64_text = await get_pic_from_url(image_url)
            if not base64_text:
                continue
            answer.append({"type": "image", "content": base64_text})
    if not answer:
        await save_answer.finish("请提供文本或图片作为答案")
        return
    answer_file = store.get_plugin_data_file(f"{question}.json")
    if answer_file.exists():
        await save_answer.finish("名称重复")
        return
    answer_file.write_text(str(answer), encoding="utf-8")
    await save_answer.finish("保存成功")

@answer_question.handle()
async def handle_answer_question(bot: Bot, event: Event):
    question = event.get_message().extract_plain_text().strip()
    if not question:
        return
    answer_file = store.get_plugin_data_file(f"{question}.json")
    if not answer_file.exists():
        return
    answer_content = answer_file.read_text(encoding="utf-8")
    answer = eval(answer_content)
    message_segments = []
    for item in answer:
        if item["type"] == "text":
            message_segments.append(MessageSegment.text(item["content"]))
        elif item["type"] == "image":
            image_data = base64.b64decode(item["content"])
            message_segments.append(MessageSegment.image(image_data))
    await answer_question.finish(Message(message_segments))

@answer_list.handle()
async def handle_answer_list(bot: Bot, event: Event):
    answer_files = store.get_plugin_data_dir().glob("*.json")
    questions = [file.stem for file in answer_files]
    if not questions:
        await answer_list.finish("没有保存的问题")
        return
    await answer_list.finish("已保存的问题列表：\n" + "\n".join(questions))

@delete_answer.handle()
async def handle_delete_answer(bot: Bot, event: Event, args: Message = CommandArg()):
    question = args.extract_plain_text().strip()
    if not question:
        await delete_answer.finish("请提供要删除的问题")
        return
    answer_file = store.get_plugin_data_file(f"{question}.json")
    if not answer_file.exists():
        await delete_answer.finish("问题不存在")
        return
    answer_file.unlink()
    await delete_answer.finish("删除成功")