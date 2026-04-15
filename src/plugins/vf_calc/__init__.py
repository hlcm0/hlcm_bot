from pydantic import BaseModel, Field

from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message

from ..ai_agent.registry import register_tool
from ..ai_agent.types import ToolExecutionContext, ToolSpec
from .config import Config
from .service import calculate_vf_message

__plugin_meta__ = PluginMetadata(
    name="vf_calc",
    description="单曲vf计算器",
    usage="/vf [等级] [分数] - 计算单曲vf",
    config=Config,
)

try:
    config = get_plugin_config(Config)
except ValueError:
    config = Config()


class VfCalcToolArgs(BaseModel):
    level: float = Field(description="谱面等级，范围 1 到 21")
    score: str = Field(description="分数，可传完整分数如 9987654，也可传 puc")


async def vf_calc_tool_handler(
    args: dict[str, str],
    context: ToolExecutionContext,
) -> str:
    _ = context
    level = float(args["level"])
    score = str(args["score"])
    return calculate_vf_message(level, score)


register_tool(
    ToolSpec(
        name="vf_calc.calculate",
        description="\
            计算 SOUND VOLTEX 单曲 VF，返回不同通关状态下的 VF 结果,\
                PUC(perfect ultimate chain)代表满分通关，\
                UC(ultimate chain)代表没有miss，\
                MAXXIVE(别名：白灯、mc)、HARD(别名：紫灯、hc)、EASY(别名：绿灯、ec)分别代表不同类型的血条，\
                CRASH代表不通过。\
                10000000分肯定PUC，但是其他通关状态无法从分数直接判断。\
                1000以下的分数会自动乘以10000。",
        handler=vf_calc_tool_handler,
        args_schema=VfCalcToolArgs,
    )
)

try:
    vf_calc = on_command("vfc", priority=5, block=True)

    @vf_calc.handle()
    async def handle_vf(args: Message = CommandArg()):
        if vf_calc is None:
            return
        args_list = args.extract_plain_text().strip().split()

        if len(args_list) != 2:
            await vf_calc.finish("用法：/vfc [等级] [分数]")
            return

        try:
            level = float(args_list[0])
            result = calculate_vf_message(level, args_list[1])
        except ValueError as exception:
            message = str(exception).strip() or "看不懂捏"
            await vf_calc.finish(message)
            return

        await vf_calc.finish(result)
except ValueError:
    vf_calc = None
