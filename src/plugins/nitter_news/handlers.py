from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from .service import NitterNewsService


def register_handlers(service: NitterNewsService) -> None:
    clear_posts = on_command(
        "clear_posts", aliases={"清空推文"}, priority=10, block=True, permission=SUPERUSER
    )

    @clear_posts.handle()
    async def handle_clear_posts() -> None:
        await service.posts.clear()
        await clear_posts.finish("已清空所有推文。")

    recent = on_command("recent", priority=5)

    @recent.handle()
    async def handle_recent(bot: Bot, event: Event, args: Message = CommandArg()) -> None:
        args_list = args.extract_plain_text().strip().split()
        if not args_list:
            await recent.finish("请指定推文源名称")

        source_name = args_list[0]
        sources = await service.sources.as_mapping()
        if source_name not in sources:
            await recent.finish(
                f"未知的推文源名称：{source_name}\n可用的推文源：{', '.join(sources.keys())}"
            )

        quantity = 10
        if len(args_list) > 1:
            try:
                quantity = int(args_list[1])
                if quantity <= 0 or quantity > 99:
                    raise ValueError
            except ValueError:
                await recent.finish("推文条数必须是1到99之间的整数")

        posts = await service.posts.list_recent(source_name, quantity)
        if event.message_type == "private":
            await service.send_news(bot, event.message_type, event.user_id, posts)
            return
        await service.send_news(bot, event.message_type, event.group_id, posts)

    add_push_group = on_command(
        "add_push_group",
        aliases={"添加推送群"},
        priority=10,
        block=True,
        permission=SUPERUSER,
    )

    @add_push_group.handle()
    async def handle_add_push_group(event: Event, args: Message = CommandArg()) -> None:
        args_list = args.extract_plain_text().strip().split()
        if len(args_list) < 1 or len(args_list) > 2:
            await add_push_group.finish("格式错误，例：add_push_group source_name group_id（可选）")
        if len(args_list) == 2:
            source_name, group_id = args_list[0], args_list[1]
        else:
            source_name = args_list[0]
            if event.message_type != "group":
                await add_push_group.finish("请在群内使用此命令，或指定群号")
            group_id = str(event.group_id)
        if await service.push_groups.add(source_name, group_id):
            await add_push_group.finish(f"已添加推送群组：{source_name} -> {group_id}")
        await add_push_group.finish(f"推送群组已存在或推文源不存在：{source_name} -> {group_id}")

    remove_push_group = on_command(
        "remove_push_group",
        aliases={"删除推送群"},
        priority=10,
        block=True,
        permission=SUPERUSER,
    )

    @remove_push_group.handle()
    async def handle_remove_push_group(event: Event, args: Message = CommandArg()) -> None:
        args_list = args.extract_plain_text().strip().split()
        if len(args_list) < 1 or len(args_list) > 2:
            await remove_push_group.finish("格式错误，例：remove_push_group source_name group_id（可选）")
        if len(args_list) == 2:
            source_name, group_id = args_list[0], args_list[1]
        else:
            source_name = args_list[0]
            if event.message_type != "group":
                await remove_push_group.finish("请在群内使用此命令，或指定群号")
            group_id = str(event.group_id)
        if await service.push_groups.remove(source_name, group_id):
            await remove_push_group.finish(f"已删除推送群组：{source_name} -> {group_id}")
        await remove_push_group.finish(f"推送群组不存在：{source_name} -> {group_id}")

    list_push_group = on_command(
        "list_push_group",
        aliases={"列出推送群"},
        priority=10,
        block=True,
        permission=SUPERUSER,
    )

    @list_push_group.handle()
    async def handle_list_push_group(args: Message = CommandArg()) -> None:
        source_name = args.extract_plain_text().strip()
        if not source_name:
            await list_push_group.finish("请指定推文源名称")
        groups = await service.push_groups.list_by_source(source_name)
        if groups:
            await list_push_group.finish(f"{source_name} 的推送群组列表：{', '.join(groups)}")
        await list_push_group.finish(f"{source_name} 暂无推送群组")

    add_source = on_command(
        "add_source", aliases={"添加推文源"}, priority=10, block=True, permission=SUPERUSER
    )

    @add_source.handle()
    async def handle_add_source(args: Message = CommandArg()) -> None:
        args_list = args.extract_plain_text().strip().split()
        if len(args_list) < 2:
            await add_source.finish("请指定推文源名称和用户名，例如：add_source name username")
        source_name, username = args_list[0], args_list[1]
        if await service.sources.add(source_name, username):
            await add_source.finish(f"已添加推文源：{source_name} -> {username}")
        await add_source.finish(f"推文源已存在：{source_name}")

    remove_source = on_command(
        "remove_source", aliases={"删除推文源"}, priority=10, block=True, permission=SUPERUSER
    )

    @remove_source.handle()
    async def handle_remove_source(args: Message = CommandArg()) -> None:
        source_name = args.extract_plain_text().strip()
        if not source_name:
            await remove_source.finish("请指定推文源名称")
        if await service.sources.remove(source_name):
            await remove_source.finish(f"已删除推文源：{source_name}")
        await remove_source.finish(f"推文源不存在：{source_name}")

    list_source = on_command(
        "list_source", aliases={"列出推文源"}, priority=10, block=True, permission=SUPERUSER
    )

    @list_source.handle()
    async def handle_list_source() -> None:
        sources = await service.sources.list_all()
        if sources:
            source_list = [f"{source.source_name}: {source.username}" for source in sources]
            await list_source.finish("推文源列表：\n" + "\n".join(source_list))
        await list_source.finish("暂无推文源")
