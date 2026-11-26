# -*- coding: utf-8 -*-
"""
build_rhyme_table.py — 生成 data/rhyme_table.json

数据来源：pypinyin（MIT）+ 十三辙归韵规则。
只做一次性构建，运行时不需要 pypinyin（表内已覆盖 GB2312 全部 6763 个汉字）。

用法：
    python scripts/build_rhyme_table.py            # 重建 data/rhyme_table.json
    python scripts/build_rhyme_table.py --check    # 只检查现有表
"""
import json
import sys
from pathlib import Path

SCHEMES = ["发花", "梭波", "乜斜", "一七", "姑苏", "怀来",
           "灰堆", "遥条", "由求", "言前", "人辰", "江阳", "中东"]

# 韵母 → 辙。pypinyin 的 FINALS 会给出 uen / iou / ve 这类完整拼写，
# 这里把长短两套写法都收进来，避免漏配。
FINAL_TO_SCHEME = {
    # 发花
    "a": 0, "ia": 0, "ua": 0,
    # 梭波
    "o": 1, "e": 1, "uo": 1, "ê": 1,
    # 乜斜
    "ie": 2, "ve": 2, "üe": 2,
    # 一七
    "i": 3, "v": 3, "ü": 3, "er": 3, "-i": 3,
    # 姑苏
    "u": 4,
    # 怀来
    "ai": 5, "uai": 5,
    # 灰堆
    "ei": 6, "uei": 6, "ui": 6,
    # 遥条
    "ao": 7, "iao": 7,
    # 由求
    "ou": 8, "iou": 8, "iu": 8,
    # 言前
    "an": 9, "ian": 9, "uan": 9, "van": 9, "üan": 9,
    # 人辰
    "en": 10, "in": 10, "uen": 10, "un": 10, "vn": 10, "ün": 10,
    # 江阳
    "ang": 11, "iang": 11, "uang": 11,
    # 中东
    "eng": 12, "ing": 12, "ong": 12, "iong": 12, "ueng": 12,
}


def gb2312_hanzi():
    """GB2312 一级 + 二级汉字，共 6763 个。"""
    out = []
    for b1 in range(0xB0, 0xF8):
        for b2 in range(0xA1, 0xFF):
            try:
                ch = bytes([b1, b2]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            if "\u4e00" <= ch <= "\u9fff":
                out.append(ch)
    return out


def build():
    try:
        from pypinyin import pinyin, Style
    except ImportError:
        sys.exit("需要 pypinyin 才能重建表：pip install pypinyin")

    chars = gb2312_hanzi()
    table, unknown = {}, []

    for ch in chars:
        try:
            final = pinyin(ch, style=Style.FINALS, heteronym=False)[0][0]
            tone_s = pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True,
                            heteronym=False)[0][0]
            tone = int(tone_s[-1]) if tone_s and tone_s[-1].isdigit() else 0
        except Exception:
            unknown.append(ch)
            continue
        idx = FINAL_TO_SCHEME.get(final)
        if idx is None:
            unknown.append(ch)
            continue
        # 轻声（5）记为 0，表示「无法判定平仄」
        if tone == 5:
            tone = 0
        table[ch] = f"{idx}|{tone}"

    data = {
        "meta": {
            "version": "1.0",
            "description": "汉字 → 十三辙 + 普通话声调的查表数据，供唱词格律校验器使用",
            "source": "pypinyin (MIT) 生成；辙名采用十三辙通行分法",
            "schemes": SCHEMES,
            "tone_note": "声调 1-4 为普通话四声，0 为轻声或未定；平仄按 1/2=平、3/4=仄 推导",
            "coverage": len(table),
            "generated_charset": "GB2312 一二级汉字",
        },
        "map": table,
    }

    out = Path(__file__).resolve().parent.parent / "data" / "rhyme_table.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")

    print(f"写入 {out}")
    print(f"  收录 {len(table)} / {len(chars)} 字，未归类 {len(unknown)}")
    if unknown:
        print("  前 30 个未归类字：" + "".join(unknown[:30]))
    per = {}
    for v in table.values():
        per[int(v.split("|")[0])] = per.get(int(v.split("|")[0]), 0) + 1
    for i, name in enumerate(SCHEMES):
        print(f"  {name}辙：{per.get(i, 0)} 字")


def check():
    out = Path(__file__).resolve().parent.parent / "data" / "rhyme_table.json"
    if not out.exists():
        sys.exit("表不存在，请先运行 build")
    d = json.loads(out.read_text(encoding="utf-8"))
    print(f"OK {out.name}: {len(d['map'])} 字, 辙数 {len(d['meta']['schemes'])}")


if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
