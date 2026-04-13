import asyncio
import base64
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from nonebot import get_plugin_config, on_command
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)
from .utils.music_search import MusicSearcher

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="sdvx_chart",
    description="",
    usage="",
    config=Config,
)

plugin_config = get_plugin_config(Config).sdvx_chart

_PLUGIN_DIR = Path(__file__).parent
_DEFAULT_RESOURCE_ROOT = _PLUGIN_DIR / "data"
_DEFAULT_XML_PATH = _DEFAULT_RESOURCE_ROOT / "others" / "music_db.xml"
_DEFAULT_CHART_ROOT = _DEFAULT_RESOURCE_ROOT / "music"
_DEFAULT_GAIJI_PATH = _PLUGIN_DIR / "utils" / "gaiji_map.json"
_DEFAULT_ALIASES_PATH = _PLUGIN_DIR / "aliases.json"
_aliases_lock = asyncio.Lock()
_resource_lock = asyncio.Lock()
_resource_error: str | None = None
alias_map: dict[str, list[str]] | None = None
searcher: MusicSearcher | None = None
music_db: dict[str, dict] | None = None

DIFFICULTY_LEVELS = ["novice", "advanced", "exhaust", "infinite", "maximum", "ultimate"]

LEVEL_SUFFIX = {
    "novice": "1n",
    "advanced": "2a",
    "exhaust": "3e",
    "infinite": "4i",
    "maximum": "5m",
    "ultimate": "6u",
}

LEVEL_ABBR = {
    "novice": "NOV",
    "advanced": "ADV",
    "exhaust": "EXH",
    "infinite": "INF",
    "maximum": "MXM",
    "ultimate": "ULT",
}

INF_VER_ABBR = {
    "1": "INF",
    "2": "INF",
    "3": "GRV",
    "4": "HVN",
    "5": "VVD",
    "6": "XCD",
    "7": "NBL",
}


def _resolve_path(raw_path: str | None, default_path: Path) -> Path:
    return Path(raw_path).expanduser() if raw_path else default_path


def _resource_root() -> Path:
    return _resolve_path(plugin_config.resource_root, _DEFAULT_RESOURCE_ROOT)


def _xml_path() -> Path:
    if plugin_config.music_db_path:
        return Path(plugin_config.music_db_path).expanduser()
    if plugin_config.resource_root:
        return _resource_root() / "others" / "music_db.xml"
    return _DEFAULT_XML_PATH


def _chart_root() -> Path:
    if plugin_config.chart_root:
        return Path(plugin_config.chart_root).expanduser()
    if plugin_config.resource_root:
        return _resource_root() / "music"
    return _DEFAULT_CHART_ROOT


def _gaiji_path() -> Path:
    return _resolve_path(plugin_config.gaiji_map_path, _DEFAULT_GAIJI_PATH)


def _aliases_path() -> Path:
    return _resolve_path(plugin_config.aliases_path, _DEFAULT_ALIASES_PATH)

def parse_music_db(xml_path: str, gaiji_path: str | None = None, encoding: str = "cp932") -> dict[str, dict]:
    """解析 music_db.xml，返回以 music id 为 key 的字典。

    每首歌的结构::

        {
            "id": "1",
            "info": { "title_name": "...", "bpm_max": "15600", ... },
            "difficulty": {
                "novice":   { "difnum": "50", "illustrator": "...", "radar": { ... }, ... },
                "advanced":  { ... },
                ...
            }
        }
    """
    gaiji_table: dict[str, str] = {}
    if gaiji_path and Path(gaiji_path).exists():
        with open(gaiji_path, "r", encoding="utf-8") as f:
            raw_map = json.load(f)
        gaiji_table = {entry["cp932_char"]: entry["char"] for entry in raw_map.values()}

    with open(xml_path, "rb") as f:
        raw = f.read()
    text = raw.decode(encoding, errors="replace")
    for wrong, correct in gaiji_table.items():
        text = text.replace(wrong, correct)
    text = re.sub(r'<\?xml[^?]*\?>', '<?xml version="1.0"?>', text, count=1)
    root = ET.fromstring(text)

    def _element_to_dict(el: ET.Element) -> dict | str:
        """递归地将 XML 元素转为 dict；叶子节点返回文本。"""
        children = list(el)
        if not children:
            return (el.text or "").strip()
        result = {}
        for child in children:
            result[child.tag] = _element_to_dict(child)
        return result

    music_db: dict[str, dict] = {}
    for music_el in root.findall("music"):
        music_id = music_el.get("id", "")
        entry: dict = {"id": music_id, "info": {}, "difficulty": {}}

        info_el = music_el.find("info")
        if info_el is not None:
            entry["info"] = _element_to_dict(info_el)

        diff_el = music_el.find("difficulty")
        if diff_el is not None:
            for level in DIFFICULTY_LEVELS:
                level_el = diff_el.find(level)
                if level_el is not None:
                    entry["difficulty"][level] = _element_to_dict(level_el)

        music_db[music_id] = entry
    return music_db

def get_level_name(level: str, inf_ver: str) -> str:
    if level == "infinite":
        return INF_VER_ABBR.get(str(inf_ver), "INF")
    return LEVEL_ABBR.get(level, level.upper())


def _normalize_music_id(music_id: str) -> str | None:
    music_id = music_id.strip()
    if not music_id.isdigit():
        return None
    return str(int(music_id))


def _normalize_aliases(raw_data: object) -> dict[str, list[str]]:
    if not isinstance(raw_data, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for raw_music_id, raw_aliases in raw_data.items():
        music_id = _normalize_music_id(str(raw_music_id))
        if not music_id:
            continue

        if isinstance(raw_aliases, str):
            alias_items = [raw_aliases]
        elif isinstance(raw_aliases, list):
            alias_items = raw_aliases
        else:
            continue

        aliases: list[str] = []
        seen: set[str] = set()
        for item in alias_items:
            if not isinstance(item, str):
                continue
            alias = item.strip()
            if not alias or alias in seen:
                continue
            seen.add(alias)
            aliases.append(alias)

        if aliases:
            normalized[music_id] = aliases

    return normalized


def load_aliases() -> dict[str, list[str]]:
    aliases_path = _aliases_path()
    if not aliases_path.exists():
        return {}

    try:
        with open(aliases_path, "r", encoding="utf-8") as file:
            return _normalize_aliases(json.load(file))
    except (json.JSONDecodeError, OSError):
        return {}


def save_aliases(aliases: dict[str, list[str]]) -> None:
    normalized = _normalize_aliases(aliases)
    aliases_path = _aliases_path()
    aliases_path.parent.mkdir(parents=True, exist_ok=True)
    with open(aliases_path, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_searcher(aliases: dict[str, list[str]] | None = None) -> MusicSearcher:
    xml_path = _xml_path()
    gaiji_path = _gaiji_path()
    return MusicSearcher(
        xml_path=str(xml_path),
        gaiji_path=str(gaiji_path) if gaiji_path.exists() else None,
        aliases=aliases,
    )


def _load_music_resources_sync(
    aliases: dict[str, list[str]],
) -> tuple[MusicSearcher, dict[str, dict]]:
    xml_path = _xml_path()
    gaiji_path = _gaiji_path()
    gaiji_arg = str(gaiji_path) if gaiji_path.exists() else None
    built_searcher = build_searcher(aliases)
    built_music_db = parse_music_db(str(xml_path), gaiji_arg)
    return built_searcher, built_music_db


async def ensure_music_resources_loaded() -> str | None:
    global alias_map, searcher, music_db, _resource_error
    if searcher is not None and music_db is not None:
        return None

    async with _resource_lock:
        if searcher is not None and music_db is not None:
            return None

        xml_path = _xml_path()
        if not xml_path.exists():
            _resource_error = f"SDVX 曲库文件未找到：{xml_path}"
            logger.warning(_resource_error)
            return _resource_error

        aliases = load_aliases()
        try:
            built_searcher, built_music_db = await asyncio.to_thread(
                _load_music_resources_sync,
                aliases,
            )
        except Exception as exception:
            _resource_error = f"加载 SDVX 资源失败：{exception}"
            logger.exception(_resource_error)
            return _resource_error

        alias_map = aliases
        searcher = built_searcher
        music_db = built_music_db
        _resource_error = None
        logger.info(f"sdvx_chart 资源已加载，曲库路径：{xml_path}")
        return None


async def reload_searcher(aliases: dict[str, list[str]]) -> str | None:
    global alias_map, searcher
    normalized_aliases = _normalize_aliases(aliases)
    alias_map = normalized_aliases
    if searcher is None:
        return await ensure_music_resources_loaded()

    try:
        searcher = await asyncio.to_thread(build_searcher, normalized_aliases)
    except Exception as exception:
        message = f"重建 SDVX 搜索索引失败：{exception}"
        logger.exception(message)
        return message
    return None

chart = on_command("chart", priority=5, block=True)
search_music = on_command("search", priority=5, block=True)
alias_command = on_command("alias", priority=5, block=True)

def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_search_args(raw_text: str) -> tuple[str, str, int | None, str | None]:
    raw_text = raw_text.strip()
    if not raw_text:
        return "search", "", None, None

    parts = raw_text.split()
    if len(parts) >= 2 and parts[0].lower() == "id" and parts[1].isdigit():
        music_id = str(int(parts[1]))
        if len(parts) >= 3 and _is_number(parts[2]):
            difficulty_text = parts[2]
            return "id", music_id, int(float(difficulty_text)), difficulty_text
        return "id", music_id, None, None

    if parts and _is_number(parts[-1]):
        difficulty_text = parts[-1]
        song_name = " ".join(parts[:-1]).strip()
        if song_name:
            return "search", song_name, int(float(difficulty_text)), difficulty_text

    return "search", raw_text, None, None


def select_difficulty(music_info: dict, requested_level: int | None) -> tuple[str | None, list[str]]:
    difficulties = music_info.get("difficulty", {})
    info = music_info.get("info", {})
    inf_ver = str(info.get("inf_ver", ""))

    if not difficulties:
        return None, []

    available = []
    for level_name, level_data in difficulties.items():
        difnum = int(level_data["difnum"])
        available.append(f"  {get_level_name(level_name, inf_ver)}: {difnum / 10:g}")

    if requested_level is None:
        matched_level = max(
            difficulties.items(),
            key=lambda item: int(item[1]["difnum"]),
        )[0]
        return matched_level, available

    for level_name, level_data in difficulties.items():
        if int(level_data["difnum"]) // 10 == requested_level:
            return level_name, available

    return None, available


async def send_forward_nodes(bot: Bot, event: Event, contents: list[str]) -> None:
    if not contents:
        return

    bot_info = await bot.get_login_info()
    nodes = [
        {
            "type": "node",
            "data": {
                "uin": int(bot_info["user_id"]),
                "name": bot_info["nickname"],
                "content": Message([MessageSegment.text(content)]),
            },
        }
        for content in contents
    ]

    if isinstance(event, GroupMessageEvent):
        await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
    elif isinstance(event, PrivateMessageEvent):
        await bot.send_private_forward_msg(user_id=event.user_id, messages=nodes)


def format_chart_candidate(song: dict) -> str:
    music_info = (music_db or {}).get(song["id"])
    if not music_info:
        return f"ID: {song['id']}\n曲名: {song['title_name']}"

    info = music_info.get("info", {})
    artist_name = info.get("artist_name", "未知曲师")
    difficulties = []
    for level_name in DIFFICULTY_LEVELS:
        level_data = music_info.get("difficulty", {}).get(level_name)
        if not level_data:
            continue
        difficulties.append(f"{int(level_data['difnum']) / 10:g}")

    difficulty_text = ",".join(difficulties) if difficulties else "无"
    return (
        f"ID: {song['id']}\n"
        f"曲名: {info.get('title_name', song['title_name'])}\n"
        f"曲师: {artist_name}\n"
        f"难度: {difficulty_text}"
    )


def format_alias_entry(music_id: str, aliases: list[str]) -> str:
    music_info = (music_db or {}).get(music_id)
    title = music_info.get("info", {}).get("title_name", f"ID {music_id}") if music_info else f"ID {music_id}"
    artist = music_info.get("info", {}).get("artist_name", "未知曲师") if music_info else "未知曲师"
    alias_text = "、".join(aliases) if aliases else "无"
    return (
        f"ID: {music_id}\n"
        f"曲名: {title}\n"
        f"曲师: {artist}\n"
        f"别名: {alias_text}"
    )


@alias_command.handle()
async def handle_alias_command(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    resource_error = await ensure_music_resources_loaded()
    if resource_error:
        await matcher.finish(resource_error)

    local_music_db = music_db or {}
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await matcher.finish(
            "格式错误哦，例：/alias add 551 火暴\n"
            "删除：/alias del 551 火暴\n"
            "查询：/alias list 551"
        )
        return

    parts = raw_args.split()
    action = parts[0].lower()

    if action in {"add", "新增", "添加"}:
        if len(parts) < 3:
            await matcher.finish("格式错误哦，例：/alias add 551 火暴")
            return

        music_id = _normalize_music_id(parts[1])
        alias = " ".join(parts[2:]).strip()
        if not music_id or music_id not in local_music_db:
            await matcher.finish(f"没有找到 ID 为 {parts[1]} 的歌曲")
            return
        if not alias:
            await matcher.finish("请提供要添加的别名")
            return

        async with _aliases_lock:
            aliases = load_aliases()
            alias_list = aliases.setdefault(music_id, [])
            if alias in alias_list:
                await matcher.finish("已经加过这个别名了")
                return
            alias_list.append(alias)
            aliases[music_id] = alias_list
            save_aliases(aliases)
            reload_error = await reload_searcher(aliases)
            if reload_error:
                await matcher.finish(reload_error)

        await matcher.finish(f"已为 ID {music_id} 添加别名：{alias}")
        return

    if action in {"del", "delete", "remove", "删除", "移除"}:
        if len(parts) < 3:
            await matcher.finish("格式错误哦，例：/alias del 551 火暴")
            return

        music_id = _normalize_music_id(parts[1])
        alias = " ".join(parts[2:]).strip()
        if not music_id:
            await matcher.finish(f"找不到歌曲 ID：{parts[1]}")
            return
        if not alias:
            await matcher.finish("请提供要删除的别名")
            return

        async with _aliases_lock:
            aliases = load_aliases()
            alias_list = aliases.get(music_id)
            if not alias_list or alias not in alias_list:
                await matcher.finish("该别名不存在")
                return

            alias_list.remove(alias)
            if alias_list:
                aliases[music_id] = alias_list
            else:
                aliases.pop(music_id, None)

            save_aliases(aliases)
            reload_error = await reload_searcher(aliases)
            if reload_error:
                await matcher.finish(reload_error)

        await matcher.finish(f"已删除 ID {music_id} 的别名：{alias}")
        return

    if action in {"list", "ls", "查询", "查看", "查"}:
        async with _aliases_lock:
            aliases = load_aliases()

        if len(parts) >= 2:
            music_id = _normalize_music_id(parts[1])
            if not music_id:
                await matcher.finish(f"找不到歌曲 ID：{parts[1]}")
                return
            alias_list = aliases.get(music_id, [])
            if not alias_list:
                await matcher.finish(f"ID {music_id} 暂无别名")
                return
            await matcher.finish(format_alias_entry(music_id, alias_list))
            return

        if not aliases:
            await matcher.finish("当前没有已保存的别名捏")
            return

        contents = [
            format_alias_entry(music_id, aliases[music_id])
            for music_id in sorted(aliases, key=lambda item: int(item))
        ]
        await send_forward_nodes(bot, event, contents)
        return

    await matcher.finish("看不懂哦")


@search_music.handle()
async def handle_search_music(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    resource_error = await ensure_music_resources_loaded()
    if resource_error:
        await matcher.finish(resource_error)

    query = args.extract_plain_text().strip()
    if not query:
        await matcher.finish("格式错误，例：/search everlasting message")
        return

    local_searcher = searcher
    if local_searcher is None:
        await matcher.finish("SDVX 搜索资源尚未加载完成，请稍后再试。")

    results = local_searcher.search(query, limit=10)
    if not results:
        await matcher.finish("没有找到匹配的歌曲")
        return

    contents = [format_chart_candidate(result["song"]) for result in results]
    await send_forward_nodes(bot, event, contents)

@chart.handle()
async def handle_chart(bot: Bot, event: Event, matcher: Matcher, args: Message = CommandArg()):
    resource_error = await ensure_music_resources_loaded()
    if resource_error:
        await matcher.finish(resource_error)

    raw_args = args.extract_plain_text().strip()
    query_type, query_value, difficulty_val, difficulty_text = parse_search_args(raw_args)

    if not query_value:
        await chart.finish("格式错误，例：/chart everlasting message 20 或 /chart id 636 19")
        return

    if difficulty_val is not None and not (1 <= difficulty_val <= 21):
        await chart.finish("难度必须在1到21之间")
        return

    song = None
    music_info = None
    local_music_db = music_db or {}
    local_searcher = searcher
    if local_searcher is None:
        await matcher.finish("SDVX 搜索资源尚未加载完成，请稍后再试。")

    if query_type == "id":
        music_info = local_music_db.get(query_value)
        if not music_info:
            await matcher.finish(f"没有找到 ID 为 {query_value} 的歌曲")
            return
        song = {
            "id": music_info["id"],
            "title_name": music_info.get("info", {}).get("title_name", f"ID {query_value}"),
            "artist_name": music_info.get("info", {}).get("artist_name", ""),
            "ascii": music_info.get("info", {}).get("ascii", ""),
        }
    else:
        results = local_searcher.search(query_value)

        if not results:
            await matcher.finish("没有找到匹配的歌曲")
            return

        top = results[0]
        if top["score"] <= 60:
            await matcher.send("不太确定呢，这里有你想搜的乐曲吗")
            contents = [f"ID: {result['song']['id']}\n曲名: {result['song']['title_name']}" for result in results]
            await send_forward_nodes(bot, event, contents)
            return

        top_score = top["score"]
        tied_results = [result for result in results if result["score"] == top_score]
        if len(tied_results) > 1:
            await matcher.send("有多个相同置信度结果，请使用id来查询哦。\n例：/chart id 636")
            contents = [format_chart_candidate(result["song"]) for result in tied_results]
            await send_forward_nodes(bot, event, contents)
            return

        song = top["song"]
        music_info = local_music_db.get(song["id"])

    if not music_info:
        await matcher.finish(f"获取{song['title_name']}谱面信息时发生错误")
        return
    inf_ver = str(music_info.get("info", {}).get("inf_ver", ""))

    matched_level, available = select_difficulty(music_info, difficulty_val)

    if not matched_level:
        await matcher.finish(
            f"{music_info['info']['title_name']} 没有难度 {difficulty_text} 的谱面\n"
            f"可用难度:\n" + "\n".join(available)
        )
        return
    level_data = music_info["difficulty"][matched_level]
    radar = level_data.get("radar", {})
    radar_str = "\n".join(f"  {k}: {v}" for k, v in radar.items())
    level_name = get_level_name(matched_level, inf_ver)

    music_id_padded = music_info["id"].zfill(4)
    ascii_name = music_info["info"].get("ascii", "")
    folder_name = f"{music_id_padded}_{ascii_name}"
    suffix = LEVEL_SUFFIX[matched_level]
    chart_filename = f"{music_id_padded}_{ascii_name}_{suffix}.png"
    chart_path = _chart_root() / folder_name / chart_filename

    if not chart_path.exists():
        await matcher.finish(
            f"{music_info['info']['title_name']} - {level_name}\n"
            f"难度值: {int(level_data['difnum']) / 10:g}\n"
            f"谱面图片不存在: {chart_filename}"
        )
        return

    img = Image.open(chart_path)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        img = bg
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    await matcher.send(
        Message([
            MessageSegment.text(
                f"{music_info['id']}: {music_info['info']['title_name']} - {level_name}\n"
                f"难度值: {int(level_data['difnum']) / 10:g}\n"
                f"雷达:\n{radar_str}\n"
            ),
            MessageSegment.image(f"base64://{img_b64}"),
        ])
    )
