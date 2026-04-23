from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx
from nonebot import get_plugin_config, on_command, on_message, require
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State

from .._bot_path import bot_file_uri
from .config import Config
from .repository import STATUS_APPROVED, STATUS_PENDING, VoiceRepository

__plugin_meta__ = PluginMetadata(
    name="voice",
    description="管理和播放自定义语音",
    usage="/add_voice [语音名称]\n/list_voice\n/approve_voice [语音名称]\n/delete_voice [语音名称]",
    config=Config,
)

config = get_plugin_config(Config)

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store

AUDIO_SUFFIXES = {
    ".aac",
    ".amr",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".silk",
    ".wav",
    ".wma",
}
VOICE_NAME_PATTERN = re.compile(r"^[0-9A-Za-z_\-\u4e00-\u9fff]+$")

voice_repository = VoiceRepository()


def _data_dir() -> Path:
    return Path(store.get_plugin_data_dir())


def _unapproved_dir() -> Path:
    return _data_dir() / "unapproved"


def _approved_dir() -> Path:
    return _data_dir() / "approved"


def _ensure_voice_dirs() -> None:
    _unapproved_dir().mkdir(parents=True, exist_ok=True)
    _approved_dir().mkdir(parents=True, exist_ok=True)


def _parse_name(args: Message) -> str | None:
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 1:
        return None
    name = parts[0]
    if (
        not VOICE_NAME_PATTERN.fullmatch(name)
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
    ):
        return None
    return name


def _extract_reply_file(event: MessageEvent) -> dict | None:
    if event.reply is None:
        return None
    for segment in event.reply.message:
        if segment.type == "file":
            return segment.data
    return None


def _suffix_from_filename(filename: str) -> str:
    return Path(filename).suffix.lower()


def _is_audio_file(filename: str, content_type: str = "") -> bool:
    suffix = _suffix_from_filename(filename)
    if suffix in AUDIO_SUFFIXES:
        return True
    return content_type.lower().split(";", 1)[0].startswith("audio/")


async def _get_file_source(bot: Bot, file_data: dict) -> tuple[str, str] | None:
    url = file_data.get("url")
    if url:
        return "url", str(url)
    return None


async def _download_audio(url: str, dest: Path, original_filename: str) -> None:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not _is_audio_file(original_filename, content_type):
                raise ValueError("文件不是支持的音频格式")
            with dest.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    file.write(chunk)


def _copy_audio(source: Path, dest: Path, original_filename: str) -> None:
    if not (_is_audio_file(original_filename) or _is_audio_file(source.name)):
        raise ValueError("文件不是支持的音频格式")
    shutil.copyfile(source, dest)


async def _approved_voice_path(name: str) -> Path | None:
    record = await voice_repository.get_approved(name)
    if record is None:
        return None
    voice_path = _approved_dir() / record.filename
    if not voice_path.is_file():
        return None
    return voice_path


add_voice = on_command("add_voice", priority=5, block=True)
list_voice = on_command("list_voice", priority=5, block=True)
approve_voice = on_command("approve_voice", priority=5, block=True, permission=SUPERUSER)
delete_voice = on_command("delete_voice", priority=5, block=True, permission=SUPERUSER)


@add_voice.handle()
async def handle_add_voice(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    name = _parse_name(args)
    if name is None:
        await add_voice.finish("格式错误，例：/add_voice hello。语音名称只能包含中英文、数字、下划线和短横线。")

    if await voice_repository.exists(name):
        await add_voice.finish(f"语音已存在：{name}")

    file_data = _extract_reply_file(event)
    if file_data is None:
        await add_voice.finish("请回复一条音频文件消息使用此命令。")

    original_filename = str(file_data.get("file") or file_data.get("name") or name)
    file_source = await _get_file_source(bot, file_data)
    if not file_source:
        await add_voice.finish("无法获取文件下载地址，请重新发送音频文件后再试。")
    source_type, source_value = file_source

    suffix = _suffix_from_filename(original_filename)
    if suffix.lower() not in AUDIO_SUFFIXES:
        parsed_suffix = _suffix_from_filename(
            urlparse(source_value).path if source_type == "url" else source_value
        )
        if parsed_suffix:
            suffix = parsed_suffix

    filename = f"{name}{suffix.lower()}"
    dest = _unapproved_dir() / filename

    _ensure_voice_dirs()
    try:
        if source_type == "url":
            await _download_audio(source_value, dest, original_filename)
        else:
            _copy_audio(Path(source_value), dest, original_filename)
    except ValueError as exception:
        if dest.exists():
            dest.unlink()
        await add_voice.finish(str(exception))
    except Exception as exception:
        if dest.exists():
            dest.unlink()
        logger.error(f"下载语音文件失败：{exception}")
        await add_voice.finish("下载语音文件失败，请稍后重试。")

    added = await voice_repository.add_pending(
        name=name,
        filename=filename,
        original_filename=original_filename,
        submitter_id=event.user_id,
    )
    if not added:
        if dest.exists():
            dest.unlink()
        await add_voice.finish(f"语音已存在：{name}")

    await add_voice.finish(f"已添加待审核语音：{name}")


@list_voice.handle()
async def handle_list_voice() -> None:
    records = await voice_repository.list_all()
    if not records:
        await list_voice.finish("暂无语音。")

    lines = []
    for record in records:
        if record.status == STATUS_APPROVED:
            lines.append(record.name)
        elif record.status == STATUS_PENDING:
            lines.append(f"{record.name}-未通过")
        else:
            lines.append(f"{record.name}-{record.status}")
    await list_voice.finish("语音列表：\n" + "\n".join(lines))


@approve_voice.handle()
async def handle_approve_voice(args: Message = CommandArg()) -> None:
    name = _parse_name(args)
    if name is None:
        await approve_voice.finish("格式错误，例：/approve_voice hello")

    record = await voice_repository.get(name)
    if record is None:
        await approve_voice.finish(f"语音不存在：{name}")
    if record.status == STATUS_APPROVED:
        await approve_voice.finish(f"语音已通过：{name}")
    if record.status != STATUS_PENDING:
        await approve_voice.finish(f"语音状态异常：{name} ({record.status})")

    _ensure_voice_dirs()
    source = _unapproved_dir() / record.filename
    target = _approved_dir() / record.filename
    if not source.is_file():
        await approve_voice.finish(f"待审核文件不存在：{record.filename}")
    if target.exists():
        await approve_voice.finish(f"目标文件已存在：{record.filename}")

    try:
        shutil.move(str(source), str(target))
    except Exception as exception:
        logger.error(f"移动语音文件失败：{exception}")
        await approve_voice.finish("移动语音文件失败，请稍后重试。")

    await voice_repository.approve(name)
    await approve_voice.finish(f"已通过语音：{name}")


@delete_voice.handle()
async def handle_delete_voice(args: Message = CommandArg()) -> None:
    name = _parse_name(args)
    if name is None:
        await delete_voice.finish("格式错误，例：/delete_voice hello")

    record = await voice_repository.get(name)
    if record is None:
        await delete_voice.finish(f"语音不存在：{name}")

    voice_dir = _approved_dir() if record.status == STATUS_APPROVED else _unapproved_dir()
    voice_path = voice_dir / record.filename
    try:
        if voice_path.exists():
            voice_path.unlink()
    except Exception as exception:
        logger.error(f"删除语音文件失败：{exception}")
        await delete_voice.finish(f"删除文件失败：{record.filename}")

    await voice_repository.delete(name)
    await delete_voice.finish(f"已删除语音：{name}")


async def is_approved_voice(event: Event, state: T_State) -> bool:
    if not isinstance(event, MessageEvent):
        return False
    name = event.get_message().extract_plain_text().strip()
    if not name or len(name.split()) != 1:
        return False
    voice_path = await _approved_voice_path(name)
    if voice_path is None:
        return False
    state["voice_path"] = voice_path
    return True


voice_message = on_message(rule=is_approved_voice, priority=10, block=False)


@voice_message.handle()
async def handle_voice_message(matcher: Matcher, state: T_State) -> None:
    voice_path = state.get("voice_path")
    if not isinstance(voice_path, Path):
        return
    await matcher.finish(MessageSegment.record(bot_file_uri(voice_path)))
