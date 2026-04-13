from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message, Event, GroupMessageEvent

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="vf_calc",
    description="单曲vf计算器",
    usage="/vf [等级] [分数] - 计算单曲vf",
    config=Config,
)

config = get_plugin_config(Config)

vf_calc = on_command("vfc", priority=5, block=True)

def get_grade_factor(score: int) -> float:
    if score >= 9900000:
        return 1.05
    elif score >= 9800000:
        return 1.02
    elif score >= 9700000:
        return 1.00
    elif score >= 9500000:
        return 0.97
    elif score >= 9300000:
        return 0.94
    elif score >= 9000000:
        return 0.91
    elif score >= 8700000:
        return 0.88
    elif score >= 7500000:
        return 0.85
    elif score >= 6500000:
        return 0.82
    else:
        return 0.80

def calc_vf(level: int, score: int, grade_factor: float, clear_factor: float) -> float:
    return int(level * (score / 10000000.0) * grade_factor * clear_factor * 20) / 20

@vf_calc.handle()
async def handle_vf(event: Event, args: Message = CommandArg()):
    # 获取参数
    args_list = args.extract_plain_text().strip().split()
    
    # 检查参数数量
    if len(args_list) != 2:
        await vf_calc.finish("用法：/vfc [等级] [分数]")
        return

    try:
        # 转换参数为数字并计算
        if args_list[1] == 'puc' or args_list[1] == 'PUC':
            score = 10000000
        else:
            score = int(args_list[1])
        level = float(args_list[0])
        
        if level < 1 or level > 21:
            await vf_calc.finish("等级应当在1-21之间")
        if score < 0 or score > 10000000:
            await vf_calc.finish("分数应当在0-10000000之间")
        if score <= 1000:
            score *= 10000
        
        grade_factor = get_grade_factor(score)
        
        puc_vf = calc_vf(level, score, grade_factor, 1.10)
        uc_vf = calc_vf(level, score, grade_factor, 1.06)
        mc_vf = calc_vf(level, score, grade_factor, 1.04)
        hc_vf = calc_vf(level, score, grade_factor, 1.02)
        ec_vf = calc_vf(level, score, grade_factor, 1.00)
        tc_vf = calc_vf(level, score, grade_factor, 0.50)

        if score == 10000000:
            await vf_calc.finish(f"PUC: {puc_vf}")
        elif score >= 5000000:
            await vf_calc.finish(f"UC: {uc_vf}\nMAXXIVE: {mc_vf}\nHARD: {hc_vf}\nEASY: {ec_vf}\nCRASH: {tc_vf}")
        else:
            await vf_calc.finish(f"MAXXIVE: {mc_vf}\nHARD: {hc_vf}\nEASY: {ec_vf}\nCRASH: {tc_vf}")

    except ValueError:
        await vf_calc.finish("看不懂捏")