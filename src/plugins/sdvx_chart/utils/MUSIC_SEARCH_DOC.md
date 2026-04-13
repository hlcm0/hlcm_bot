# MusicSearcher 使用文档

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install rapidfuzz pykakasi opencc-python-reimplemented
```

## 快速开始

```python
from music_search import MusicSearcher, ALIASES

searcher = MusicSearcher(
    xml_path="data/others/music_db.xml",
    gaiji_path="gaiji_map.json",
    aliases=ALIASES,
)

results = searcher.search("nanairo", limit=10)

for r in results:
    print(f"{r['song']['title_name']}  score={r['score']}  {r['matched_by']}")
```

## 构造函数参数

```python
MusicSearcher(xml_path, encoding="cp932", aliases=None, gaiji_path=None)
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `xml_path` | `str` | 是 | `music_db.xml` 文件路径 |
| `encoding` | `str` | 否 | XML 文件编码，默认 `"cp932"` |
| `aliases` | `dict[str, list[str]]` | 否 | 别名表，key 为歌曲 `id`，value 为别名列表 |
| `gaiji_path` | `str` | 否 | `gaiji_map.json` 路径，用于替换 CP932 外字（如 `闃`→`Ā`） |

## 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `song_count` | `int` | 曲库总歌曲数 |
| `songs` | `list[dict]` | 原始歌曲列表 |
| `indexed` | `list[IndexedSong]` | 预构建的搜索索引 |

## search() 方法

```python
searcher.search(query: str, limit: int = 10) -> list[dict]
```

### 返回值

每条结果是一个 dict，字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `song` | `dict` | 歌曲原始信息（含 `id`, `title_name`, `title_yomigana`, `ascii`, `artist_name`, `artist_yomigana`） |
| `score` | `float` | 综合评分（0~100） |
| `matched_by` | `str` | 命中原因，格式为 `"{字段} {匹配类型}"`，如 `"title_romaji prefix"` |
| `matched_field` | `str` | 命中的字段名 |
| `matched_value` | `str` | 命中字段的原始值（归一化前） |
| `matched_normalized` | `str` | 命中字段的归一化值 |
| `query_variant` | `str` | 实际命中的查询变体（`raw` / `hira` / `romaji`） |

### 返回示例

```python
[
    {
        "song": {
            "id": "780",
            "title_name": "ナナイロ",
            "title_yomigana": "ﾅﾅｲﾛ",
            "ascii": "nanairo",
            "artist_name": "Ryu☆",
            "artist_yomigana": "ﾘｭｳ"
        },
        "score": 95.0,
        "matched_by": "alias exact",
        "matched_field": "alias",
        "matched_value": "nanairo",
        "matched_normalized": "nanairo",
        "query_variant": "raw"
    }
]
```

## 归一化规则

对查询字符串和曲库字段都做以下处理：

1. **NFKC 归一化** — 全角→半角，兼容字符统一（`Ａ`→`A`，`ｶ`→`カ`）
2. **去变音符号** — `Ā`→`A`，`é`→`e`，`ü`→`u`
3. **CJK 繁简统一** — `蝕`→`蚀`，`體`→`体`（opencc t2s）
4. **转小写** — `PULSE`→`pulse`
5. **去空格** — `PULSE LASER`→`pulselaser`
6. **去符号** — `:`, `!`, `-`, `_` 等全部去除

示例：
```
"  PULSE  LASER "     → "pulselaser"
"ｶﾞｯﾃﾝだ!!"           → "がってんだ"
"DEUX EX MĀXHINĀ"     → "deuxexmaxhina"
"侵蝕コード：666"       → "侵蚀コード666"  (繁→简,去符号)
```

## 搜索索引字段

每首歌自动生成以下可搜索字段：

| 字段名 | 来源 | 权重 | 说明 |
|--------|------|------|------|
| `title` | `title_name` | 1.0 | 标题归一化 |
| `title_hira` | `title_name` | 0.9 | 标题片假名→平假名 |
| `title_romaji` | `title_name` | 0.8 | 标题→罗马字 (pykakasi) |
| `yomi` | `title_yomigana` | 0.85 | 读音归一化 |
| `yomi_hira` | `title_yomigana` | 0.85 | 读音→平假名 |
| `yomi_romaji` | `title_yomigana` | 0.75 | 读音→罗马字 |
| `ascii` | `ascii` | 0.7 | ASCII 检索名 |
| `artist` | `artist_name` | 0.5 | 作曲者 |
| `artist_romaji` | `artist_name` | 0.4 | 作曲者→罗马字 |
| `alias` | 别名表 | 0.95 | 用户定义的别名 |

## 匹配类型与评分

查询时自动生成三种变体：**原始归一化**、**平假名**、**罗马字**，对每首歌的所有字段逐一比对，取最高分。

### 匹配类型

| 匹配类型 | 基础分 | 说明 |
|----------|--------|------|
| `exact` | 100 | 归一化后完全相等 |
| `prefix` | 85~95 | 查询是字段值的前缀，覆盖率越高分越高 |
| `substring` | 70~80 | 查询是字段值的子串 |
| `scattered` | 75~87 | 查询拆段后所有段在字段值中都出现（如 `侵蚀666` 匹配 `侵蚀コード666今日ちょっと指略`） |
| `fuzzy` | 55~100 | rapidfuzz 模糊匹配 |

### 最终得分

```
最终得分 = 基础分 × 字段权重 × 修正系数
```

修正系数包括：
- **短查询惩罚**：查询≤2字符且非精确匹配时 ×0.6
- **romaji fuzzy 降权**：romaji 变体的 fuzzy 匹配 ×0.75
- **长度差异惩罚**：查询与字段长度比 <0.65 时按比例衰减

## 别名表

别名表是一个字典，key 为歌曲的 `id`（XML 中 `<music id="...">` 的值），value 为别名字符串列表：

```python
ALIASES = {
    "780": ["nanairo", "なないろ", "七色"],          # ナナイロ
    "390": ["rinhana", "凛花"],                      # 凛として咲く花の如く
    "237": ["flower", "フラワー"],                    # FLOWER
}
```

使用歌曲 ID 作为 key 可以精确绑定别名，避免同名歌曲的冲突。别名的匹配结果会在 `matched_by` 中体现为 `alias exact` / `alias prefix` / `alias fuzzy` 等。

## 外字映射 (gaiji_map.json)

部分歌曲标题含有 CP932 编码范围外的特殊字符（如 `Ā`, `é`, `♥`），在 CP932 解码时会变成错误的汉字。`gaiji_map.json` 提供了修正映射：

```json
{
    "EA99": {
        "char": "é",
        "cp932_char": "齷"
    }
}
```

加载后，所有文本中的 `齷` 会被替换为 `é`。此替换在 XML 解析前完成，影响所有字段。

## 搜索示例

| 输入 | 命中歌曲 | 命中原因 |
|------|----------|----------|
| `"nanairo"` | ナナイロ | alias exact (95.0) |
| `"なないろ"` | ナナイロ | alias exact (95.0) |
| `"ナナ"` | ナナイロ | alias prefix (86.2) |
| `"pulse laser"` | PULSE LASER | title exact (100.0) |
| `"ALBIDA"` | ALBIDA Powerless Mix | title prefix (88.3) |
| `"rinhana"` | 凛として咲く花の如く | alias exact (95.0) |
| `"アルビダ"` | ALBIDA Powerless Mix | yomi prefix (74.9) |
| `"flower"` | FLOWER | title exact (100.0) |
| `"侵蚀666"` | 侵蝕コード：666 -今日ちょっと指（略- | title scattered (78.8) |
| `"maxhina"` | DEUX EX MĀXHINĀ | title substring (75.4) |

## 底层函数（按需使用）

如果不想使用 `MusicSearcher` 封装，可以直接调用底层函数：

```python
from music_search import (
    parse_music_xml,
    build_index,
    search,
    normalize_basic,
    kata_to_hira,
    to_romaji,
    ALIASES,
)

# 1. 读取 XML
songs = parse_music_xml("data/others/music_db.xml", gaiji_path="gaiji_map.json")

# 2. 建索引（只需一次）
indexed = build_index(songs, aliases_map=ALIASES)

# 3. 搜索（可反复调用）
results = search("nanairo", indexed, limit=10)

# 工具函数
normalize_basic("PULSE  LASER")   # -> "pulselaser"
kata_to_hira("ナナイロ")            # -> "なないろ"
to_romaji("ナナイロ")              # -> "nanairo"
```
