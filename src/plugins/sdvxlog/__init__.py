from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.plugin import on_message, on_command
import httpx, ssl
import re

from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Event,
)

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="sdvxlog",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

async def get_file_from_url(url):
    SSL_CONTEXT = ssl.create_default_context()
    SSL_CONTEXT.set_ciphers('DEFAULT')
    User_Agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        "AppleWebKit/537.36 (KHTML, like Gecko)"
        "Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0"
    )
    async with httpx.AsyncClient(verify=SSL_CONTEXT) as client:
        messages = await client.get(url, headers={"User-Agent": User_Agent})
        content = messages.content
        return content
    return None

async def is_file(event):
    message = event.message[0]
    return message.type == 'file'

log = on_message(priority=5, block=False, rule=is_file)

@log.handle()
async def handle_log(bot: Bot, event: Event):
    if not isinstance(event, GroupMessageEvent):
        return
    message = event.message[0]
    if message.type != 'file':
        return
    if not ('log' in message.data['file'] and '.txt' in message.data['file']):
        return
    file_url = message.data['url']
    file_content = await get_file_from_url(file_url)
    log_str = file_content.decode(encoding='utf-8', errors="ignore")

    # 检查是否存在音频问题
    if ("W:dll_entry_init: Failed to boot Audio." in log_str):
        await bot.send(event=event, message=MessageSegment.text(f"log中出现了音频设备启动失败的报错\n可尝试的解决办法：在dll patcher中勾选Shared WASAPI相关选项"))
        return
    
    if ("Please check if soundvoltex.dll exists and the permissions are fine." in log_str):
        await bot.send(event=event, message=MessageSegment.text(f"log中出现了加载soundvoltex.dll失败的报错\n可尝试的解决办法：\n1.确认游戏目录下是否存在soundvoltex.dll文件\n2.安装VC和DirectX运行库"))
        return
    
# info = on_command("log", priority=5, block=True)

# @info.handle()
# async def handle_info(bot: Bot, event: Event):
#     bot_info = await bot.get_login_info()
#     if not isinstance(event, GroupMessageEvent):
#         return
#     if not event.reply:
#         await bot.send(event=event, message=MessageSegment.text("请回复log.txt文件消息"))
#         return
#     reply_message = None
#     for item in event.reply:
#         if item[0] == 'message':
#             reply_message = item[1][0]
#     if not reply_message or reply_message.type != 'file':
#         await bot.send(event=event, message=MessageSegment.text("请回复log.txt文件消息"))
#         return
#     if not ('log' in reply_message.data['file'] and '.txt' in reply_message.data['file']):
#         await bot.send(event=event, message=MessageSegment.text("请回复log.txt文件消息"))
#         return
#     if not 'url' in reply_message.data or not reply_message.data['url']:
#         await bot.send(event=event, message=MessageSegment.text("文件似乎过期了，请重新发送log.txt文件"))
#         return
#     file_url = reply_message.data['url']
#     file_content = await get_file_from_url(file_url)
#     log_str = file_content.decode(encoding='utf-8', errors="ignore")
    
#     # 检查是否是SDVX的log
#     if not "Sound Voltex" in log_str and not "soundvoltex.dll" in log_str:
#         await bot.send(event=event, message=MessageSegment.text("暂时不支持非SDVX的log分析"))
#         return

#     messages = []

#     # 输出启动参数信息
#     pattern = r'arguments:\s*(.*?)(?=\n\[|$)'
#     match = re.search(pattern, log_str, re.DOTALL)
#     if match:
#         arguments = match.group(1)
#         arguments = '\n'.join(line.strip() for line in arguments.split('\n'))
#         messages.append(Message(
#             "spice启动参数：\n"+arguments
#         ))

#     # 输出patch信息
#     pattern = r'(I:patchmanager: patches file info:.*?\[.*?\] I:patchmanager: loaded total of \d+ patches)'
#     match = re.search(pattern, log_str, re.DOTALL)
#     if match:
#         patch_info = match.group(1)
#         patch_info = re.sub(r'\[\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\] ', '', patch_info)
#         patch_info = re.sub(r'I:patchmanager: ', '', patch_info)
#         patch_info = re.sub(r'auto apply: ', '', patch_info)
#         messages.append(Message(
#             "patch信息：\n"+patch_info
#         ))
#     else:
#         messages.append(Message(
#             "没有找到patch信息"
#         ))

#     # 输出网络信息
#     message = ''
#     pattern_ea3 = r'M:ea3-config: network/services\s*:\s*"([^"]+)"'
#     match_ea3 = re.search(pattern_ea3, log_str)
#     if match_ea3:
#         ea3_url = match_ea3.group(1)
#         message += "ea3内设定的地址："+ea3_url+"\n"
    
#     pattern_spice = r'-url\s+([^\s]+)'
#     match_spice = re.search(pattern_spice, log_str)
#     if match_spice:
#         spice_url = match_spice.group(1)
#         message += "spice启动参数设定的地址："+spice_url+"\n"

#     pattern_xrpc = r'xrpc: connect\((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+),'
#     match_xrpc = re.search(pattern_xrpc, log_str)
#     if match_xrpc:
#         ip_port = match_xrpc.group(1)
#         message += "实际网络请求IP地址："+ip_port

#     if message:
#         messages.append(Message(message))
#     else:
#         messages.append(Message("没有找到网络相关信息"))
    
#     # 输出卡号信息
#     pattern = r'Inserted card0\.txt:\s*([A-F0-9]{16})'
#     cards = re.findall(pattern, log_str)
#     message = '刷过的卡号：\n'
#     for card in cards:
#         message += card + '\n'
#     if cards:
#         messages.append(Message(message))

#     response = []

#     for msg in messages:
#         response.append({
#             "type": "node",
#             "data": {
#                 "uin": int(bot_info['user_id']),
#                 "name": bot_info['nickname'],
#                 "content": msg
#             }
#         })
    
#     await bot.send_group_forward_msg(group_id=event.group_id, messages=response)