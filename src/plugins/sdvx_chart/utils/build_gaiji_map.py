"""
通过比对 sdvxindex.com 的歌曲 JSON 与 music_db.xml 中的 CP932 原始标题,
自动推导出游戏使用的外字 (gaiji) 映射表。

用法:
  python3 build_gaiji_map.py

输入:
  - /tmp/sdvxindex_songs.json  (从 https://sdvxindex.com/songsv1.3.3.json 下载)
  - data/others/music_db.xml   (CP932 编码的游戏数据)

输出:
  - gaiji_map.json  (CP932 字节 -> 实际 Unicode 字符的映射表)
"""

import json
import re
import sys
from collections import defaultdict


def load_xml_titles(xml_path: str) -> dict[str, bytes]:
    """从 music_db.xml 中提取 music id -> title_name 的原始字节映射"""
    with open(xml_path, "rb") as f:
        data = f.read()

    titles = {}
    # 匹配 <music id="XXXX"> ... <title_name>YYY</title_name>
    for m in re.finditer(
        rb'<music\s+id="(\d+)".*?<title_name>(.*?)</title_name>', data, re.DOTALL
    ):
        music_id = m.group(1).decode("ascii")
        title_raw = m.group(2)
        titles[music_id] = title_raw
    return titles


def load_json_titles(json_path: str) -> dict[str, str]:
    """从 sdvxindex JSON 中提取 songid -> title 映射"""
    with open(json_path) as f:
        songs = json.load(f)

    titles = {}
    for song in songs:
        # songid 在 JSON 中是零填充的 4 位字符串，如 "0001"
        sid = song["songid"].lstrip("0") or "0"
        titles[sid] = song["title"]
    return titles


def find_gaiji_bytes(raw: bytes) -> list[tuple[int, bytes]]:
    """找出原始字节中所有可能是外字的双字节序列。
    CP932 的双字节范围: 第一字节 0x81-0x9F 或 0xE0-0xFC"""
    results = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
            if i + 1 < len(raw):
                pair = raw[i : i + 2]
                results.append((i, pair))
                i += 2
                continue
        i += 1
    return results


def align_and_extract(raw: bytes, correct: str) -> dict[str, str]:
    """对齐 CP932 原始字节与正确的 Unicode 标题,提取外字映射。

    策略: 将 raw 按 CP932 解码（替换模式），然后将解码结果与 correct 进行
    字符级对齐，找出不匹配的位置，反推对应的原始字节。
    """
    mappings = {}

    # 逐个 token 解码 raw
    tokens = []  # (decoded_char, raw_bytes)
    i = 0
    while i < len(raw):
        b = raw[i]
        if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
            if i + 1 < len(raw):
                pair = raw[i : i + 2]
                try:
                    ch = pair.decode("cp932")
                except UnicodeDecodeError:
                    ch = "\ufffd"
                tokens.append((ch, pair))
                i += 2
                continue
        # 单字节
        try:
            ch = bytes([b]).decode("cp932")
        except UnicodeDecodeError:
            ch = "\ufffd"
        tokens.append((ch, bytes([b])))
        i += 1

    decoded_chars = [t[0] for t in tokens]
    decoded_str = "".join(decoded_chars)

    # 如果解码后长度与 correct 不同，尝试简单对齐
    if len(decoded_chars) != len(correct):
        # 长度不匹配，跳过
        return mappings

    # 逐字符比对
    for idx, (dec_ch, (tok_ch, tok_bytes)) in enumerate(zip(correct, tokens)):
        if dec_ch != tok_ch and len(tok_bytes) == 2:
            hex_key = tok_bytes.hex().upper()
            mappings[hex_key] = dec_ch

    return mappings


def main():
    xml_path = "data/others/music_db.xml"
    json_path = "/tmp/sdvxindex_songs.json"

    print("加载 music_db.xml ...")
    xml_titles = load_xml_titles(xml_path)
    print(f"  找到 {len(xml_titles)} 首歌曲")

    print("加载 sdvxindex JSON ...")
    json_titles = load_json_titles(json_path)
    print(f"  找到 {len(json_titles)} 首歌曲")

    # 找出共同的歌曲 ID
    common_ids = set(xml_titles.keys()) & set(json_titles.keys())
    print(f"  共同 ID: {len(common_ids)}")

    # 比对提取映射
    gaiji_map = {}  # hex_bytes -> unicode_char
    gaiji_sources = defaultdict(list)  # hex_bytes -> [(xml_title, json_title)]

    for sid in sorted(common_ids, key=int):
        raw = xml_titles[sid]
        correct = json_titles[sid]

        # 只处理包含高字节的标题
        has_high = any(b >= 0x80 for b in raw)
        if not has_high:
            continue

        found = align_and_extract(raw, correct)
        for hex_key, unicode_char in found.items():
            if hex_key not in gaiji_map:
                gaiji_map[hex_key] = unicode_char
            elif gaiji_map[hex_key] != unicode_char:
                # 冲突！记录但不覆盖
                print(
                    f"  ⚠ 冲突: 0x{hex_key} -> "
                    f"已有 '{gaiji_map[hex_key]}' vs 新 '{unicode_char}' "
                    f"(song {sid})"
                )
            gaiji_sources[hex_key].append(
                (raw.decode("cp932", errors="replace"), correct)
            )

    # 收录所有不一致的序列（跳过完全相同的）
    filtered = {}
    for hex_key, unicode_char in sorted(gaiji_map.items()):
        raw_bytes = bytes.fromhex(hex_key)
        try:
            cp932_char = raw_bytes.decode("cp932")
        except UnicodeDecodeError:
            filtered[hex_key] = unicode_char
            continue

        if cp932_char == unicode_char:
            continue

        filtered[hex_key] = unicode_char

    print(f"\n找到 {len(filtered)} 个不一致映射:")
    print("-" * 60)
    for hex_key in sorted(filtered.keys()):
        unicode_char = filtered[hex_key]
        raw_bytes = bytes.fromhex(hex_key)
        try:
            cp932_char = raw_bytes.decode("cp932")
        except UnicodeDecodeError:
            cp932_char = "?"
        sources = gaiji_sources[hex_key]
        print(
            f"  0x{hex_key} | CP932: {cp932_char} (U+{ord(cp932_char):04X}) "
            f"-> '{unicode_char}' (U+{ord(unicode_char):04X})"
        )
        for src_xml, src_json in sources[:2]:
            print(f"         来源: {src_json}")

    # 输出 JSON
    output = {}
    for hex_key in sorted(filtered.keys()):
        unicode_char = filtered[hex_key]
        raw_bytes = bytes.fromhex(hex_key)
        try:
            cp932_char = raw_bytes.decode("cp932")
        except UnicodeDecodeError:
            cp932_char = "?"
        output[hex_key] = {
            "char": unicode_char,
            "unicode": f"U+{ord(unicode_char):04X}",
            "cp932_char": cp932_char,
            "cp932_unicode": f"U+{ord(cp932_char):04X}",
        }

    output_path = "gaiji_map.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n映射表已保存到 {output_path}")


if __name__ == "__main__":
    main()
