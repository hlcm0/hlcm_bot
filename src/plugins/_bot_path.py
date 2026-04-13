from __future__ import annotations

import os
from pathlib import Path

from nonebot.log import logger

_host_root_warned = False


def _host_root() -> Path | None:
    raw = os.getenv("BOT_FILE_MOUNT_HOST_ROOT")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _container_root() -> Path | None:
    raw = os.getenv("BOT_FILE_MOUNT_CONTAINER_ROOT")
    if not raw:
        return None
    return Path(raw).expanduser()


def map_path_for_bot(path: str | Path) -> Path:
    global _host_root_warned
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = source.resolve()

    host_root = _host_root()
    container_root = _container_root()
    if not host_root or not container_root:
        return source

    try:
        relative = source.relative_to(host_root)
    except ValueError:
        if not _host_root_warned:
            logger.warning(
                "BOT_FILE_MOUNT_HOST_ROOT 已配置，但部分文件不在该目录下，"
                "这些路径将不会被映射到 NapCat 容器内。"
            )
            _host_root_warned = True
        return source

    return container_root / relative


def bot_local_path(path: str | Path) -> str:
    return str(map_path_for_bot(path))


def bot_file_uri(path: str | Path) -> str:
    mapped = map_path_for_bot(path)
    if not mapped.is_absolute():
        raise ValueError(f"映射后的路径必须是绝对路径：{mapped}")
    return mapped.as_uri()
