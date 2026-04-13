"""
乐曲模糊搜索模块 (Music Fuzzy Search)

支持功能:
  - Unicode NFKC 归一化、全角半角统一、去符号、去空格
  - 片假名 <-> 平假名互转
  - 日文 -> 罗马字转换 (pykakasi)
  - 多字段索引 (title_name / title_yomigana / ascii / artist_name)
  - 别名表
  - 多路召回 + 打分排序 (精确 / 前缀 / 子串 / fuzzy)
  - 命中原因输出

依赖:
  pip install rapidfuzz pykakasi opencc-python-reimplemented
"""

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import opencc
from pykakasi import kakasi
from rapidfuzz import fuzz

# ============================================================
# 全局单例 (只初始化一次)
# ============================================================
_kakasi = kakasi()
_t2s = opencc.OpenCC("t2s")  # 繁体/日本旧字体 -> 简体

# ============================================================
# 1. 归一化工具函数
# ============================================================

# 日文新字体 -> 简体中文 映射表
# 来源: OpenCC JPVariants.txt (繁体->新字体) 反转后, 再经 t2s 转简体
# 只收录新字体 != 简体的条目
_JP_SHINJITAI_TO_SC: dict[str, str] = {}

def _init_jp_to_sc():
    """从 opencc t2s 和 JPVariants 数据构建 新字体->简体 映射"""
    # JPVariants: 繁体 -> 新字体 (一对一或一对多)
    # 格式: "繁体字\t新字体" 每行一条
    _JP_VARIANTS_DATA = (
        "乘\t乗\n亂\t乱\n亙\t亘\n亞\t亜\n佛\t仏\n來\t来\n假\t仮\n傳\t伝\n"
        "僞\t偽\n價\t価\n儉\t倹\n兒\t児\n兔\t兎\n內\t内\n兩\t両\n冰\t氷\n"
        "剎\t刹\n剩\t剰\n劍\t剣\n劑\t剤\n勞\t労\n勳\t勲\n勵\t励\n勸\t勧\n"
        "區\t区\n卷\t巻\n卻\t却\n參\t参\n吳\t呉\n咒\t呪\n啞\t唖\n單\t単\n"
        "噓\t嘘\n嚙\t噛\n嚴\t厳\n囑\t嘱\n圈\t圏\n國\t国\n圍\t囲\n圓\t円\n"
        "圖\t図\n團\t団\n增\t増\n墮\t堕\n壓\t圧\n壘\t塁\n壞\t壊\n壤\t壌\n"
        "壯\t壮\n壹\t壱\n壽\t寿\n奧\t奥\n妝\t粧\n孃\t嬢\n學\t学\n寢\t寝\n"
        "實\t実\n寫\t写\n寬\t寛\n寶\t宝\n將\t将\n專\t専\n對\t対\n屆\t届\n"
        "屬\t属\n峯\t峰\n峽\t峡\n嶽\t岳\n巖\t巌\n巢\t巣\n帶\t帯\n廁\t厠\n"
        "廢\t廃\n廣\t広\n廳\t庁\n彈\t弾\n彌\t弥\n彎\t弯\n彥\t彦\n徑\t径\n"
        "從\t従\n徵\t徴\n德\t徳\n恆\t恒\n悅\t悦\n惠\t恵\n惡\t悪\n惱\t悩\n"
        "慘\t惨\n應\t応\n懷\t懐\n戀\t恋\n戰\t戦\n戲\t戯\n戶\t戸\n戾\t戻\n"
        "拂\t払\n拔\t抜\n拜\t拝\n挾\t挟\n插\t挿\n揭\t掲\n搔\t掻\n搖\t揺\n"
        "搜\t捜\n摑\t掴\n擇\t択\n擊\t撃\n擔\t担\n據\t拠\n擴\t拡\n攝\t摂\n"
        "攪\t撹\n收\t収\n效\t効\n敕\t勅\n敘\t叙\n數\t数\n斷\t断\n晉\t晋\n"
        "晚\t晩\n晝\t昼\n暨\t曁\n曆\t暦\n曉\t暁\n曾\t曽\n會\t会\n枡\t桝\n"
        "查\t査\n條\t条\n棧\t桟\n榆\t楡\n榮\t栄\n樂\t楽\n樓\t楼\n樞\t枢\n"
        "樣\t様\n橫\t横\n檢\t検\n櫻\t桜\n權\t権\n歐\t欧\n歡\t歓\n步\t歩\n"
        "歲\t歳\n歷\t歴\n歸\t帰\n殘\t残\n殼\t殻\n毆\t殴\n每\t毎\n氣\t気\n"
        "污\t汚\n沒\t没\n涉\t渉\n淚\t涙\n淨\t浄\n淺\t浅\n渴\t渇\n溪\t渓\n"
        "溫\t温\n溼\t湿\n滯\t滞\n滿\t満\n潑\t溌\n潛\t潜\n澀\t渋\n澤\t沢\n"
        "濟\t済\n濤\t涛\n濱\t浜\n濾\t沪\n瀧\t滝\n瀨\t瀬\n灣\t湾\n焰\t焔\n"
        "燈\t灯\n燒\t焼\n營\t営\n爐\t炉\n爭\t争\n爲\t為\n牀\t床\n犧\t犠\n"
        "狀\t状\n狹\t狭\n獎\t奨\n獨\t独\n獵\t猟\n獸\t獣\n獻\t献\n產\t産\n"
        "畫\t画\n當\t当\n疊\t畳\n疎\t疏\n痹\t痺\n瘦\t痩\n癡\t痴\n發\t発\n"
        "皋\t皐\n盜\t盗\n盡\t尽\n碎\t砕\n礪\t砺\n祕\t秘\n祿\t禄\n禦\t御\n"
        "禪\t禅\n禮\t礼\n禱\t祷\n稅\t税\n稱\t称\n稻\t稲\n穎\t頴\n穗\t穂\n"
        "穩\t穏\n穰\t穣\n竈\t竃\n竊\t窃\n粹\t粋\n糉\t粽\n絕\t絶\n絲\t糸\n"
        "經\t経\n綠\t緑\n緖\t緒\n緣\t縁\n縣\t県\n縱\t縦\n總\t総\n繡\t繍\n"
        "繩\t縄\n繪\t絵\n繫\t繋\n繼\t継\n續\t続\n纔\t才\n纖\t繊\n缺\t欠\n"
        "罐\t缶\n羣\t群\n聯\t連\n聰\t聡\n聲\t声\n聽\t聴\n肅\t粛\n脣\t唇\n"
        "脫\t脱\n腦\t脳\n腳\t脚\n膽\t胆\n臟\t臓\n臺\t台\n與\t与\n舉\t挙\n"
        "舊\t旧\n舍\t舎\n荔\t茘\n莊\t荘\n莖\t茎\n菸\t煙\n萊\t莱\n萬\t万\n"
        "蔣\t蒋\n蔥\t葱\n薰\t薫\n藏\t蔵\n藝\t芸\n藥\t薬\n蘆\t芦\n處\t処\n"
        "虛\t虚\n號\t号\n螢\t蛍\n蟲\t虫\n蠟\t蝋\n蠶\t蚕\n蠻\t蛮\n裝\t装\n"
        "覺\t覚\n覽\t覧\n觀\t観\n觸\t触\n說\t説\n謠\t謡\n證\t証\n譯\t訳\n"
        "譽\t誉\n讀\t読\n變\t変\n讓\t譲\n豐\t豊\n豫\t予\n貓\t猫\n貳\t弐\n"
        "賣\t売\n賴\t頼\n贊\t賛\n贗\t贋\n踐\t践\n輕\t軽\n輛\t輌\n轉\t転\n"
        "辭\t辞\n遞\t逓\n遲\t遅\n邊\t辺\n鄉\t郷\n酢\t醋\n醉\t酔\n醫\t医\n"
        "醬\t醤\n醱\t醗\n釀\t醸\n釋\t釈\n鋪\t舗\n錄\t録\n錢\t銭\n鍊\t錬\n"
        "鐵\t鉄\n鑄\t鋳\n鑛\t鉱\n閱\t閲\n關\t関\n陷\t陥\n隨\t随\n險\t険\n"
        "隱\t隠\n雙\t双\n雜\t雑\n雞\t鶏\n霸\t覇\n靈\t霊\n靜\t静\n顏\t顔\n"
        "顯\t顕\n餘\t余\n騷\t騒\n驅\t駆\n驗\t験\n驛\t駅\n髓\t髄\n體\t体\n"
        "髮\t髪\n鬥\t闘\n鱉\t鼈\n鷗\t鴎\n鹼\t鹸\n鹽\t塩\n麥\t麦\n麪\t麺\n"
        "麴\t麹\n黃\t黄\n黑\t黒\n默\t黙\n點\t点\n黨\t党\n齊\t斉\n齋\t斎\n"
        "齒\t歯\n齡\t齢\n龍\t竜\n龜\t亀\n"
    )
    # 反转: 新字体 -> 繁体
    jp_to_trad: dict[str, str] = {}
    for line in _JP_VARIANTS_DATA.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 2:
            trad, shinjitai = parts[0], parts[1]
            for sj in shinjitai.split():
                if sj != trad:
                    jp_to_trad[sj] = trad

    # 繁体 -> 简体
    for jp_char, trad_char in jp_to_trad.items():
        sc_char = _t2s.convert(trad_char)
        if sc_char != jp_char:
            _JP_SHINJITAI_TO_SC[jp_char] = sc_char

_init_jp_to_sc()


def cjk_simplify(s: str) -> str:
    """CJK 繁体/异体字/日文新字体 -> 简体统一 (蝕->蚀, 変->变, 広->广 等)"""
    if not s:
        return ""
    # 先做 opencc t2s (处理繁体)
    s = _t2s.convert(s)
    # 再做日文新字体 -> 简体 (opencc t2s 不覆盖的部分)
    if _JP_SHINJITAI_TO_SC:
        s = s.translate(str.maketrans(_JP_SHINJITAI_TO_SC))
    return s


def normalize_basic(s: str) -> str:
    """基础归一化: NFKC -> 去变音 -> 繁简统一 -> 小写 -> 去空格 -> 去符号"""
    if not s:
        return ""
    # NFKC 归一化 (统一全角半角、兼容字符等)
    s = unicodedata.normalize("NFKC", s)
    # 去除变音符号: Ā->A, é->e, ü->u 等
    # NFD 分解后去掉 combining marks (Mn), 再 NFC 合回
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = unicodedata.normalize("NFC", s)
    # CJK 繁体/异体字 -> 简体 (蝕->蚀 等)
    s = cjk_simplify(s)
    # 小写
    s = s.lower()
    # 去掉所有空白字符
    s = re.sub(r"\s+", "", s)
    # 去掉大多数 ASCII 符号, 保留字母/数字/日文/中文等
    # 保留: 字母、数字、CJK 统一表意文字、平假名、片假名
    s = re.sub(r"[^\w]", "", s, flags=re.UNICODE)
    # Python \w 会保留下划线, 也去掉
    s = s.replace("_", "")
    return s


def kata_to_hira(s: str) -> str:
    """片假名转平假名 (先 NFKC 归一化处理半角片假名)"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    # 片假名 Unicode 区间: U+30A1 ~ U+30F6
    # 对应平假名: U+3041 ~ U+3096 (偏移 -0x60)
    result = []
    for ch in s:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            result.append(chr(cp - 0x60))
        elif cp == 0x30F7:  # ヷ -> わ゙ (少见, 直接保留)
            result.append(ch)
        elif cp == 0x30FC:  # 长音符 ー 保留
            result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


def to_romaji(s: str) -> str:
    """日文 (平假名/片假名/汉字) -> 罗马字转换"""
    if not s:
        return ""
    items = _kakasi.convert(s)
    # pykakasi 返回 list of dict, 每个 dict 有 'hepburn' 键
    parts = [item["hepburn"] for item in items]
    return normalize_basic("".join(parts))


# ============================================================
# 2. XML 读取
# ============================================================

def _load_gaiji_map(gaiji_path: str | None) -> dict[str, str]:
    """
    加载外字映射表, 返回 { cp932解码后的错误字符 -> 正确字符 } 字典。
    gaiji_map.json 中每条记录的 cp932_char 是 CP932 解码产生的错误汉字,
    char 是实际应显示的正确字符。
    """
    if gaiji_path is None:
        return {}
    path = Path(gaiji_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw_map = json.load(f)
    return {entry["cp932_char"]: entry["char"] for entry in raw_map.values()}


def _apply_gaiji(text: str, gaiji_table: dict[str, str]) -> str:
    """将文本中的外字替换为正确字符"""
    if not gaiji_table:
        return text
    for wrong_char, correct_char in gaiji_table.items():
        text = text.replace(wrong_char, correct_char)
    return text


def parse_music_xml(path: str, encoding: str = "cp932",
                    gaiji_path: str | None = None) -> list[dict]:
    """
    读取 music_db.xml, 返回歌曲信息列表。
    每首歌至少包含: id, title_name, title_yomigana, ascii, artist_name, artist_yomigana

    gaiji_path: gaiji_map.json 路径, 用于替换 CP932 外字
    """
    gaiji_table = _load_gaiji_map(gaiji_path)

    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode(encoding, errors="replace")

    # 替换外字 (CP932 解码后的错误字符 -> 正确 Unicode 字符)
    text = _apply_gaiji(text, gaiji_table)

    # 去掉原始 XML 声明中的 encoding (已经是 unicode 字符串了)
    text = re.sub(r'<\?xml[^?]*\?>', '<?xml version="1.0"?>', text, count=1)

    root = ET.fromstring(text)
    songs = []

    for music_el in root.findall("music"):
        song_id = music_el.get("id", "")
        info = music_el.find("info")
        if info is None:
            continue

        def _text(tag: str) -> str:
            el = info.find(tag)
            return (el.text or "").strip() if el is not None else ""

        songs.append({
            "id": song_id,
            "title_name": _text("title_name"),
            "title_yomigana": _text("title_yomigana"),
            "ascii": _text("ascii"),
            "artist_name": _text("artist_name"),
            "artist_yomigana": _text("artist_yomigana"),
        })

    return songs


# ============================================================
# 3. 索引构建
# ============================================================

@dataclass
class SearchKey:
    """单个可搜索的键"""
    field_name: str   # 例如 "title", "title_hira", "title_romaji", "yomi", "ascii", "alias"
    original: str     # 归一化前的原始值
    normalized: str   # 归一化后的值
    weight: float     # 字段权重


@dataclass
class IndexedSong:
    """带索引的歌曲"""
    song: dict                          # 原始歌曲数据
    keys: list[SearchKey] = field(default_factory=list)


# ---------- 权重配置 ----------
# 方便调参, 所有权重集中在这里
FIELD_WEIGHTS = {
    "title":          1.0,    # title_name 归一化
    "title_hira":     0.9,    # title_name 平假名形式
    "title_romaji":   0.8,    # title_name 罗马字
    "yomi":           0.85,   # title_yomigana 归一化
    "yomi_hira":      0.85,   # title_yomigana 平假名形式
    "yomi_romaji":    0.75,   # title_yomigana 罗马字
    "ascii":          0.7,    # ascii 字段
    "alias":          0.95,   # 别名
}


def _add_key(keys: list[SearchKey], field_name: str, original: str, normalized: str):
    """添加一个 SearchKey, 跳过空值和重复值"""
    if not normalized:
        return
    weight = FIELD_WEIGHTS.get(field_name, 0.5)
    keys.append(SearchKey(field_name=field_name, original=original,
                          normalized=normalized, weight=weight))


def build_song_index(song: dict, aliases: list[str] | None = None) -> IndexedSong:
    """为单首歌生成搜索索引"""
    keys: list[SearchKey] = []
    title = song.get("title_name", "")
    yomi = song.get("title_yomigana", "")
    ascii_name = song.get("ascii", "")
    artist = song.get("artist_name", "")

    # --- title_name ---
    title_norm = normalize_basic(title)
    _add_key(keys, "title", title, title_norm)

    title_hira = normalize_basic(kata_to_hira(title))
    if title_hira != title_norm:
        _add_key(keys, "title_hira", title, title_hira)

    title_roma = to_romaji(title)
    if title_roma and title_roma != title_norm:
        _add_key(keys, "title_romaji", title, title_roma)

    # --- title_yomigana ---
    yomi_norm = normalize_basic(yomi)
    if yomi_norm and yomi_norm != title_norm:
        _add_key(keys, "yomi", yomi, yomi_norm)

    yomi_hira = normalize_basic(kata_to_hira(yomi))
    if yomi_hira and yomi_hira not in (title_norm, title_hira, yomi_norm):
        _add_key(keys, "yomi_hira", yomi, yomi_hira)

    yomi_roma = to_romaji(yomi)
    if yomi_roma and yomi_roma not in (title_norm, title_roma):
        _add_key(keys, "yomi_romaji", yomi, yomi_roma)

    # --- ascii ---
    ascii_norm = normalize_basic(ascii_name)
    if ascii_norm:
        _add_key(keys, "ascii", ascii_name, ascii_norm)

    # --- aliases ---
    if aliases:
        for alias in aliases:
            alias_norm = normalize_basic(alias)
            if alias_norm:
                _add_key(keys, "alias", alias, alias_norm)

    return IndexedSong(song=song, keys=keys)


def build_index(songs: list[dict], aliases_map: dict[str, list[str]] | None = None) -> list[IndexedSong]:
    """
    为整个曲库建立索引。

    aliases_map: { song_id -> [alias1, alias2, ...] }
    """
    aliases_map = aliases_map or {}
    indexed = []
    for song in songs:
        song_id = song.get("id", "")
        aliases = aliases_map.get(song_id)
        indexed.append(build_song_index(song, aliases))
    return indexed


# ============================================================
# 4. 打分逻辑
# ============================================================

# ---------- 匹配类型基础分 ----------
MATCH_BASE_SCORES = {
    "exact":     100.0,
    "prefix":     85.0,
    "substring":  70.0,
    "scattered":  65.0,   # 散列匹配 (所有段都出现但不连续)
    "fuzzy":       0.0,   # fuzzy 分由 rapidfuzz 提供, 直接用其 0~100 值
}

# fuzzy 匹配阈值: 低于此分数的 fuzzy 结果不采纳
FUZZY_THRESHOLD = 55.0

# query 过短惩罚: query 归一化后长度 <= 此值时, 降低非精确匹配的分数
SHORT_QUERY_LEN = 2
SHORT_QUERY_PENALTY = 0.6  # 乘以此系数


def _effective_len(s: str) -> int:
    """CJK 字符信息量更大, 每个计为 2; 用于短 query 惩罚判定。"""
    n = 0
    for ch in s:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            n += 2
        else:
            n += 1
    return n


def _split_query_tokens(s: str) -> list[str]:
    """
    将归一化后的 query 按字符类型边界拆分成段。

    拆分逻辑: 相邻字符若属于不同"类型组"则断开。
    类型组:
      - CJK (中文/日文汉字 + 平假名 + 片假名)
      - ASCII 字母
      - 数字

    例如:
      "侵蚀666"     -> ["侵蚀", "666"]
      "pulselaser"   -> ["pulselaser"]
      "flower123"    -> ["flower", "123"]
      "凛花spooky"   -> ["凛花", "spooky"]
    """
    if not s:
        return []

    def _char_group(ch: str) -> int:
        cp = ord(ch)
        # 数字
        if ch.isdigit():
            return 1
        # ASCII 字母
        if ch.isascii() and ch.isalpha():
            return 2
        # CJK / 日文 (汉字 + 假名)
        # CJK Unified Ideographs: U+4E00 ~ U+9FFF
        # CJK Extension A: U+3400 ~ U+4DBF
        # Hiragana: U+3040 ~ U+309F
        # Katakana: U+30A0 ~ U+30FF
        # 长音符、浊点等 Katakana Phonetic Extensions
        if (0x3040 <= cp <= 0x30FF or  # 假名
            0x4E00 <= cp <= 0x9FFF or  # CJK 基本
            0x3400 <= cp <= 0x4DBF or  # CJK 扩展A
            0xF900 <= cp <= 0xFAFF):   # CJK 兼容
            return 3
        # 其他 (韩文等) 归入独立组
        return 4

    tokens = []
    current_group = _char_group(s[0])
    current_start = 0

    for i in range(1, len(s)):
        g = _char_group(s[i])
        if g != current_group:
            tokens.append(s[current_start:i])
            current_start = i
            current_group = g

    tokens.append(s[current_start:])

    # 过滤太短的 token (单字符噪音)
    return [t for t in tokens if len(t) >= 1]


def _subsequence_match(query: str, key: str) -> tuple[int, int] | None:
    """
    检查 query 是否为 key 的子序列 (每个字符按顺序出现在 key 中)。

    返回 (匹配字符数, 跨度长度) 或 None。
    跨度 = 最后一个匹配位置 - 第一个匹配位置 + 1。

    例如:
      query="世界果", key="世界の果てに約束の凱歌を"
      -> 世(0) 界(1) 果(3), 跨度=4, 返回 (3, 4)
    """
    qi = 0
    first_pos = -1
    last_pos = -1
    for ki, ch in enumerate(key):
        if qi < len(query) and ch == query[qi]:
            if first_pos == -1:
                first_pos = ki
            last_pos = ki
            qi += 1
    if qi == len(query):
        span = last_pos - first_pos + 1
        return (len(query), span)
    return None


@dataclass
class MatchResult:
    """单次匹配的结果"""
    score: float
    match_type: str       # "exact" / "prefix" / "substring" / "fuzzy"
    field_name: str       # 命中的字段名
    field_original: str   # 字段的原始值
    field_normalized: str # 字段的归一化值
    query_variant: str    # 用到的 query 变体名称


def _score_one_pair(query_norm: str, key_norm: str) -> tuple[float, str]:
    """
    对比单个 query 和单个 key, 返回 (原始分数, 匹配类型)。
    原始分数尚未乘以字段权重。
    """
    if not query_norm or not key_norm:
        return 0.0, ""

    # 1) 精确相等
    if query_norm == key_norm:
        return MATCH_BASE_SCORES["exact"], "exact"

    # 2) 前缀匹配
    if key_norm.startswith(query_norm):
        # 根据覆盖率微调: query 越长占比越高, 分越高
        ratio = len(query_norm) / len(key_norm)
        score = MATCH_BASE_SCORES["prefix"] + ratio * 10  # 85 ~ 95
        return score, "prefix"

    # 3) 子串匹配
    if query_norm in key_norm:
        ratio = len(query_norm) / len(key_norm)
        score = MATCH_BASE_SCORES["substring"] + ratio * 10  # 70 ~ 80
        return score, "substring"

    # 3.5) 散列匹配: query 拆成多段, 检查是否所有段都出现在 key 中
    #      例如 "侵蚀666" -> ["侵蚀", "666"], 两段都在 key 中即命中
    tokens = _split_query_tokens(query_norm)
    if len(tokens) >= 2 and all(t in key_norm for t in tokens):
        # 覆盖率 = query 总长 / key 长
        coverage = len(query_norm) / len(key_norm)
        # 多段全命中是很强的信号, 基础分略高于 substring
        score = 75.0 + coverage * 12  # 75 ~ 87
        return score, "scattered"

    # 3.6) 子序列匹配: query 的每个字符按顺序出现在 key 中
    #      例如 "世界果" 匹配 "世界の果てに約束の凱歌を" (跳过 の)
    #      要求 query 至少 2 个字符, 且 key 足够长
    if len(query_norm) >= 2 and len(key_norm) >= len(query_norm) + 1:
        subseq_span = _subsequence_match(query_norm, key_norm)
        if subseq_span is not None:
            matched_len, span_len = subseq_span
            # 密度: 匹配字符占跨度的比例 (1.0 = 连续, 越低越松散)
            density = matched_len / span_len
            # 覆盖率: query 长度占 key 长度的比例
            coverage = matched_len / len(key_norm)
            # 密度高且覆盖率高时给更高的分
            # 密度 0.5~1.0 映射到 60~75
            score = 55.0 + density * 15 + coverage * 10
            return score, "subsequence"

    # 4) fuzzy 匹配
    # 跳过 key 过短的情况 (单字符标题等容易产生虚假高分)
    if len(key_norm) <= 2 or len(query_norm) <= 1:
        return 0.0, ""

    fuzz_score = fuzz.ratio(query_norm, key_norm)
    partial_score = fuzz.partial_ratio(query_norm, key_norm)

    # partial_ratio 对短 key 容易虚高, 按 key 长度衰减其权重
    # key 越短, partial_ratio 贡献越小
    partial_weight = min(1.0, len(key_norm) / max(len(query_norm), 8.0)) * 0.95

    # 如果 key 是 query 的子串, partial_ratio 会给满分, 但这不是好匹配
    # (应该是 query 在 key 里, 而不是 key 在 query 里)
    if key_norm in query_norm:
        partial_weight *= 0.5

    best_fuzz = max(fuzz_score, partial_score * partial_weight)

    # 长度差异惩罚: query 和 key 长度差距越大, fuzzy 结果越不可靠
    len_ratio = min(len(query_norm), len(key_norm)) / max(len(query_norm), len(key_norm))
    if len_ratio < 0.65:
        best_fuzz *= (0.35 + len_ratio)  # 0.35~1.0 的缩放

    if best_fuzz >= FUZZY_THRESHOLD:
        return best_fuzz, "fuzzy"

    return 0.0, ""


def score_candidate(
    query_variants: list[tuple[str, str]],
    indexed_song: IndexedSong,
    pure_hanzi: bool = False,
) -> Optional[MatchResult]:
    """
    对单首歌打分。

    query_variants: [(variant_name, normalized_value), ...]
        例如 [("raw", "nanairo"), ("hira", "なないろ"), ("romaji", "nanairo")]
    pure_hanzi: 若为 True, 跳过假名 / 罗马字相关字段

    返回该歌曲的最佳 MatchResult, 或 None (未命中)。
    """
    best: Optional[MatchResult] = None

    for qv_name, qv_norm in query_variants:
        if not qv_norm:
            continue
        for key in indexed_song.keys:
            # 纯汉字 query: 跳过假名 / 罗马字字段, 只匹配含汉字的字段
            if pure_hanzi and key.field_name in _KANA_FIELDS:
                continue
            raw_score, match_type = _score_one_pair(qv_norm, key.normalized)
            if raw_score <= 0:
                continue

            # 乘以字段权重
            weighted = raw_score * key.weight

            # romaji 变体的 fuzzy 匹配容易假阳性, 降权
            if qv_name == "romaji" and match_type == "fuzzy":
                weighted *= 0.75

            # romaji 变体丢失字符时 (如 pykakasi 不识别简体中文),
            # 按信息保留率降权, 避免短罗马字前缀匹配假阳性
            if qv_name == "romaji" and match_type != "exact":
                raw_norm = query_variants[0][1]  # 第一项始终是 raw
                expected = max(len(raw_norm) * 2, 1)
                retention = min(len(qv_norm) / expected, 1.0)
                if retention < 1.0:
                    weighted *= max(retention, 0.3)

            # 短 query 惩罚 (非精确匹配时)
            if _effective_len(qv_norm) <= SHORT_QUERY_LEN and match_type != "exact":
                weighted *= SHORT_QUERY_PENALTY

            if best is None or weighted > best.score:
                best = MatchResult(
                    score=round(weighted, 2),
                    match_type=match_type,
                    field_name=key.field_name,
                    field_original=key.original,
                    field_normalized=key.normalized,
                    query_variant=qv_name,
                )

    return best


# ============================================================
# 5. 搜索主函数
# ============================================================

# 纯汉字 query 时需要跳过的假名 / 罗马字相关字段
_KANA_FIELDS = frozenset({
    "title_hira", "title_romaji",
    "yomi", "yomi_hira", "yomi_romaji",
    "artist_romaji",
})


def _has_no_kana_or_alpha(s: str) -> bool:
    """判断归一化后的字符串是否不含平假名、片假名或英文字母。"""
    if not s:
        return False
    for ch in s:
        cp = ord(ch)
        # 平假名: U+3040 ~ U+309F
        if 0x3040 <= cp <= 0x309F:
            return False
        # 片假名: U+30A0 ~ U+30FF
        if 0x30A0 <= cp <= 0x30FF:
            return False
        # ASCII 字母
        if ch.isascii() and ch.isalpha():
            return False
    return True


def _make_query_variants(query: str) -> tuple[list[tuple[str, str]], bool]:
    """
    由用户输入生成多种 query 变体, 用于多路召回。
    返回: ([(variant_name, normalized_string), ...], pure_hanzi)
    """
    raw_norm = normalize_basic(query)
    pure_hanzi = _has_no_kana_or_alpha(raw_norm)

    variants = [("raw", raw_norm)]

    if pure_hanzi:
        # 纯汉字输入: 不生成假名 / 罗马字变体, 避免噪音
        return variants, True

    hira_norm = normalize_basic(kata_to_hira(query))
    roma_norm = to_romaji(query)

    # 避免重复
    seen = {raw_norm}
    if hira_norm and hira_norm not in seen:
        variants.append(("hira", hira_norm))
        seen.add(hira_norm)
    if roma_norm and roma_norm not in seen:
        variants.append(("romaji", roma_norm))
        seen.add(roma_norm)

    return variants, False


def search(
    query: str,
    indexed_songs: list[IndexedSong],
    limit: int = 10,
) -> list[dict]:
    """
    搜索入口。

    参数:
      query: 用户输入的搜索字符串
      indexed_songs: 预构建的索引列表
      limit: 最多返回结果数

    返回: 按分数降序排列的结果列表, 每条包含:
      - song: 原始歌曲信息
      - score: 综合评分
      - matched_by: 命中原因描述 (如 "title_romaji prefix")
      - matched_field: 命中的字段名
      - matched_value: 命中的字段原始值
    """
    if not query or not query.strip():
        return []

    query_variants, pure_hanzi = _make_query_variants(query)
    results = []

    for isong in indexed_songs:
        mr = score_candidate(query_variants, isong, pure_hanzi=pure_hanzi)
        if mr is not None:
            results.append({
                "song": isong.song,
                "score": mr.score,
                "matched_by": f"{mr.field_name} {mr.match_type}",
                "matched_field": mr.field_name,
                "matched_value": mr.field_original,
                "matched_normalized": mr.field_normalized,
                "query_variant": mr.query_variant,
            })

    # 按分数降序, 同分按 title_name 排序
    results.sort(key=lambda r: (-r["score"], r["song"].get("title_name", "")))
    return results[:limit]


# ============================================================
# 6. 便捷封装: MusicSearcher 类
# ============================================================

class MusicSearcher:
    """
    一体化搜索器: 读取 XML → 建索引 → 搜索。

    用法:
        searcher = MusicSearcher("data/others/music_db.xml", aliases=ALIASES)
        results = searcher.search("nanairo")
    """

    def __init__(
        self,
        xml_path: str,
        encoding: str = "cp932",
        aliases: dict[str, list[str]] | None = None,
        gaiji_path: str | None = None,
    ):
        self.songs = parse_music_xml(xml_path, encoding=encoding, gaiji_path=gaiji_path)
        self.indexed = build_index(self.songs, aliases_map=aliases)
        self.aliases = aliases or {}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        return search(query, self.indexed, limit=limit)

    @property
    def song_count(self) -> int:
        return len(self.songs)


# ============================================================
# 7. 示例别名表
# ============================================================

ALIASES: dict[str, list[str]] = {
    "780": ["nanairo", "なないろ", "七色"],          # ナナイロ
    "390": ["rinhana", "凛花", "凛として"],          # 凛として咲く花の如く
    "986": ["rinhana spooky", "凛花スプーキー"],      # 凛として咲く花の如く スプーキィテルミィンミックス
    "237": ["flower", "フラワー"],                    # FLOWER
}


# ============================================================
# 直接运行时的演示
# ============================================================

if __name__ == "__main__":
    import time

    XML_PATH = "data/others/music_db.xml"
    GAIJI_PATH = "gaiji_map.json"

    print("=" * 60)
    print("乐曲模糊搜索 演示")
    print("=" * 60)

    t0 = time.time()
    searcher = MusicSearcher(XML_PATH, aliases=ALIASES, gaiji_path=GAIJI_PATH)
    t1 = time.time()
    print(f"\n曲库加载完成: {searcher.song_count} 首歌, 索引耗时 {t1 - t0:.2f}s\n")

    # 演示查询
    test_queries = [
        "nanairo",
        "なないろ",
        "ナナ",
        "pulse laser",
        "ALBIDA",
        "rinhana",
        "アルビダ",
        "flower",
        "侵蚀666",
        "侵蝕666",
        "侵蝕コード",
    ]

    for q in test_queries:
        print("-" * 50)
        print(f"查询: \"{q}\"")
        t0 = time.time()
        results = searcher.search(q, limit=5)
        t1 = time.time()
        print(f"  耗时: {(t1 - t0) * 1000:.1f}ms, 命中 {len(results)} 条")

        for i, r in enumerate(results):
            song = r["song"]
            print(f"  [{i+1}] {song['title_name']}")
            print(f"       score={r['score']}  matched_by=\"{r['matched_by']}\"")
            print(f"       matched_value=\"{r['matched_value']}\"  query_variant={r['query_variant']}")
        if not results:
            print("  (无结果)")
        print()
