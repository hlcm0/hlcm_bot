# hlcm_bot

QQ机器人。

## 概览

- 框架：NoneBot 2
- 适配器：OneBot V11
- Bot协议端：Napcat
- 功能：
    - `@机器人` 触发的 LangGraph AI Agent
    - SDVX 曲目和谱面查询
    - 定时推送指定账号的 Twitter 推文
    - 解析 Twitter 视频链接并发送视频
    - 氧无插件更新推送
    - SDVX 私网存档导出(推荐使用[hlcm.top](https://hlcm.top)，机器人侧功能停止维护)
    - SDVX VF 计算

## 目录结构

```text
hlcm_bot/
├── pyproject.toml
├── README.md
├── .env
└── src/
    └── plugins/
        ├── ai_agent/
        ├── github_release_downloader/
        ├── hlcm_response/
        ├── nitter_news/
        ├── sdvx_chart/
        ├── sdvx_score_export/
        ├── sdvxlog/
        ├── twitter_video_downloader/
        └── vf_calc/
```

## 部署方式

### 1. 准备 `nb` 命令

根据官方文档-[快速上手](https://nonebot.dev/docs/quick-start)，安装pipx并通过它安装 `nb-cli`

### 2. 创建项目运行环境

项目当前代码已经使用了 Python 3.10 语法，推荐使用 3.10 以上的版本。

```bash
conda create -n nonebot python=3.10
conda activate nonebot
```

### 3. 安装项目依赖

在项目目录中安装依赖：

```bash
cd /path/to/hlcm_bot
pip install -e .
```

如果你还需要开发辅助依赖：

```bash
pip install -e ".[dev]"
```

### 4. 配置环境变量

复制 `.env.example` 并重命名为 `.env`，然后编辑所需的配置项，

请看下文的配置项说明部分。

### 5. 迁移数据库

需要使用 `nb orm` 命令来迁移数据库，使其包含插件所需的表结构：

```bash
nb orm revision -m "Initial migration"
nb orm upgrade
```

相关数据库迁移操作请参考[NoneBot 2 数据库最佳实践](https://nonebot.dev/docs/best-practice/database/developer/)

### 6. 启动机器人

```bash
conda activate nonebot
cd /path/to/hlcm_bot
nb run
```

### 7. 部署NapCat机器人

```bash
docker run -d \
  --name napcat \
  --restart=always \
  -e NAPCAT_UID=$(id -u) \
  -e NAPCAT_GID=$(id -g) \
  -p 3000:3000 \
  -p 3001:3001 \
  -p 6099:6099 \
  --mount type=bind,src=/path/to/hlcm-bot-localstore,dst=/app/napcat-shared \
  mlikiowa/napcat-docker:latest
```

这会下载并启动NapCat的Docker镜像，并将本地的 `hlcm-bot-localstore` 文件夹挂载到容器内的 `/app/napcat-shared` 目录。

之后请按照[NapCat文档-接入框架](https://napneko.github.io/use/integration)的说明将NapCat连接到NoneBot。

## AI Agent

`ai_agent` 插件基于 LangGraph

- 触发方式：在群聊或私聊里 `@机器人` 并附带自然语言问题，如果需要上下文记忆，则需使用回复消息
- 当前限制：插件暂时只接入了vf_calc
- 备注：目前ChatDeepSeek使用的是langchain-deepseek-v4包而不是官方的langchain-deepseek包，因为官方的版本暂不支持最新的DeepSeek-V4.

后续其他插件如需接入 Agent，请显式依赖 `src/plugins/ai_agent/registry.py` 中暴露的注册接口，先把业务逻辑抽成普通 async service，再通过 `ToolSpec` 注册到 registry。

## 相关依赖

### 1.外部资源

一部分资源需要手动放在 `hlcm-bot-resources` 文件夹中，并通过 `.env` 中的路径配置项指向它们的位置。

谱面图片是提前生成的，与 `.vox` 文件存放在同一位置且文件名相同。

```text
/path/to/hlcm-bot-resources/
├── sdvx_chart/
    ├── others/
    │   └── music_db.xml
    ├── music/
    │   └── ...
    ├── gaiji_map.json
    └── aliases.json
```

可使用 [vox_visualizer](https://github.com/hlcm0/vox_visualizer) 工具生成谱面图片。

### 2. 部署 Nitter 实例

`nitter_news` 和 `twitter_video_downloader` 这两个插件都依赖一个 fork 版的 Nitter 实例来获取推文数据，请参考 [hlcm0/nitter_with_api](https://github.com/hlcm0/nitter_with_api) 的部署说明进行部署，然后在机器人的 `.env` 文件中配置相应的地址。

推荐使用 Docker Compose 来部署这个服务。
- 根据 `docker-compose.yml` 文件中的注释，将 dockerfile 和 image 字段替换为你的平台(arm64 或 amd64)对应的版本
- 运行
    ```bash
    docker-compose up -d --build
    ```

## 配置项说明

### 全局配置

| 配置项 | 说明 |
| --- | --- |
| `ENVIRONMENT` | 环境名，通常为 `prod` 或 `dev` |
| `DRIVER` | NoneBot 驱动配置，当前项目使用 `~fastapi+~httpx+~websockets` |
| `SUPERUSERS` | 机器人管理员 QQ 号列表 |
| `ONEBOT_ACCESS_TOKEN` | OneBot 连接令牌 |

### `ai_agent`

说明：LangGraph AI Agent 插件相关配置

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `AI_AGENT__ENABLED` | 否 | 是否启用 AI Agent，默认 `false` |
| `AI_AGENT__API_KEY` | 是 | 模型服务 API Key |
| `AI_AGENT__PROVIDER` | 否 | 模型服务提供方，支持 `openrouter` 和 `deepseek`，默认 `openrouter` |
| `AI_AGENT__MODEL` | 是 | 主对话模型名 |
| `AI_AGENT__SAFEGUARD_MODEL` | 是 | 用于内容安全检测的模型名，建议使用小模型以节省资源和加快响应 |
| `AI_AGENT__BASE_URL` | 否 | OpenRouter 兼容接口地址，默认 `https://openrouter.ai/api/v1`；`provider` 为 `deepseek` 时不使用 |
| `AI_AGENT__TEMPERATURE` | 否 | 主对话模型采样温度，默认 `1.0` |
| `AI_AGENT__SAFEGUARD_TEMPERATURE` | 否 | 内容安全检测模型采样温度，默认 `1.0` |
| `AI_AGENT__MAX_TOKENS` | 否 | 主对话模型最大输出 token 数，默认 `1024`；内容安全检测固定最多输出 100 token |
| `AI_AGENT__SYSTEM_PROMPT` | 否 | Agent 的系统提示词，默认 `你是一个 AI 助手，你的名字叫草莓。` |
| `AI_AGENT__FIRST_AI_MESSAGE` | 否 | Agent 在没有上下文时的第一条消息内容，默认 `你好呀，我是草莓。有什么可以帮你的吗？` |
| `AI_AGENT__MAXIMUM_CONTEXT_WINDOW` | 否 | 回复消息最大回溯条数，默认 20 条 |

### `sdvx_chart`

Todo: 这一部分用到的部分资源文件之后会补充，或者 QQ 问我要（？）

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `SDVX_CHART__RESOURCE_ROOT` | 否 | SDVX 资源根目录 |
| `SDVX_CHART__MUSIC_DB_PATH` | 否 | `music_db.xml` 的绝对路径 |
| `SDVX_CHART__CHART_ROOT` | 否 | 谱面图片根目录 |
| `SDVX_CHART__GAIJI_MAP_PATH` | 否 | `gaiji_map.json` 路径 |
| `SDVX_CHART__ALIASES_PATH` | 否 | 别名文件路径 |

### `nitter_news`

需要自行申请翻译模型(我用的是火山引擎的 DeepSeek)的 API Key，并部署 `nitter_with_api`，

国内用户需要配置代理，才能从 Twitter 服务器下载图片、视频等资源。

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `NITTER_NEWS__DS_API_URL` | 是 | 翻译模型 API 地址 |
| `NITTER_NEWS__DS_API_KEY` | 是 | 翻译模型 API Key |
| `NITTER_NEWS__DS_MODEL_NAME` | 是 | 翻译模型名称 |
| `NITTER_NEWS__PROXY` | 否 | 访问外部资源时使用的代理 |
| `NITTER_NEWS__NITTER_BASE_URL` | 是 | 本地 `nitter_with_api` 服务地址 |

### `twitter_video_downloader`

说明：解析 `x.com/.../status/...` 链接，发送视频或 GIF。

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `TWITTER_VIDEO_DOWNLOADER__WHITELIST` | 是 | 允许使用该功能的用户 QQ 号列表（防止有人乱发一些爆的东西） |
| `TWITTER_VIDEO_DOWNLOADER__PROXY` | 否 | 下载视频时使用的代理 |
| `TWITTER_VIDEO_DOWNLOADER__NITTER_API_BASE_URL` | 是 | 本地 `nitter_with_api` API 地址 |

### `github_release_downloader`

说明：获取指定 GitHub 仓库的最新 release，并向群推送压缩包。

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `GITHUB_RELEASE_DOWNLOADER__REPO` | 否 | 仓库名，默认 `22vv0/asphyxia_plugins` |
| `GITHUB_RELEASE_DOWNLOADER__PUSH_GROUP` | 否 | 自动推送更新的群号列表 |
| `GITHUB_RELEASE_DOWNLOADER__PROXY` | 否 | 访问 GitHub 的代理 |
| `GITHUB_RELEASE_DOWNLOADER__TIMEOUT` | 否 | GitHub API 请求超时时间 |

## Todo
- 完善部署说明
- 补充资源文件

## 参考

- [NoneBot 2 文档](https://nonebot.dev/)
- [Napcat 文档](https://napneko.github.io)
- [hlcm0/nitter_with_api](https://github.com/hlcm0/nitter_with_api)
- [zedeus/nitter](https://github.com/zedeus/nitter)
- [hlcm0/langchain_deepseek_v4](https://github.com/hlcm0/langchain_deepseek_v4)