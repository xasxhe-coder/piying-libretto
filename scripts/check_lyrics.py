#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_lyrics.py — 皮影戏唱词格律校验器

设计原则
--------
1. 引擎与规则分离：本文件只提供"可判定的检查"，格律本身来自 rules/*.json。
2. 能自动判的（字数、押韵、韵脚重复、上下句配对、段落结构）默认开启；
   需要专家给定的（平仄定式、腔格）默认关闭，等规则注入后才生效。
3. 所有结果结构化返回，含位置、类型、原因、修改建议，可直接驱动高亮。

作为库使用
----------
    from check_lyrics import check
    r = check(唱词文本, preset="tangshan_qizi")
    r["passed"], r["issues"], r["summary"]

命令行
------
    python check_lyrics.py --text "一字千金……" --preset tangshan_qizi
    python check_lyrics.py --file demo.txt --rules rules/tangshan_qizi.json --json
    python check_lyrics.py --list
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "rhyme_table.json"
RULES_DIR = ROOT / "rules"


def _supports(ch: str) -> bool:
    """当前终端编码能否输出该字符（中文 Windows 常见 GBK 控制台）。"""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        ch.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_FANCY = _supports("✓")

# ---------------------------------------------------------------- 常量
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3007]")
CLAUSE_DELIMS = "，,、；;：:。.！!？?…—"
END_PUNCT = "，,。.！!？?；;…"

SCHEMES = ["发花", "梭波", "乜斜", "一七", "姑苏", "怀来",
           "灰堆", "遥条", "由求", "言前", "人辰", "江阳", "中东"]

# 给「换一个同辙的字」这类建议用的常用字，仅作提示，不参与判定
COMMON_RHYME = {
    0: "花家华沙茶麻大下马话答怕佳涯霞",
    1: "波河歌多说过我何破落火坐活客车得",
    2: "别月雪夜些写接切节铁血解姐烈灭绝",
    3: "里时知事起意地子期死思之士日理齐西宜笔",
    4: "书处路苦古都无出木主独入如哭图数",
    5: "来开在爱海白台改外才买卖快代盖赛",
    6: "谁归水泪对会飞贵回岁美醉退追备累",
    7: "少道高好老了笑到朝保报草小桥消妙巧",
    8: "有手口头走后留酒秋愁厚友州流求受",
    9: "天年前山间边看难见面关还传缘言远",
    10: "人心真春深门身亲恩尘分根神新今民林",
    11: "江长光上方望浪唱忘乡香堂扬强当伤",
    12: "中声生风名情明成行同空灯城清星听",
}

# 虚词：给「删字」建议时优先指出
FUNCTION_WORDS = set("的了着过就便也又还倒却把被将向在和与跟同从对为以之其而则乃且但只是不没很太更最都总")

DEFAULT_RULES = {
    "meta": {
        "name": "自定义规则",
        "confidence": "custom",
        "warning": "",
        "source": "",
    },
    "structure": {
        "line_chars": {"min": None, "max": None},
        "clause_chars": None,           # 如 [3, 4] 表示按分句字数
        "couplet_required": True,
        "min_lines_per_stanza": 2,
        "max_lines_per_stanza": None,
        "max_chars_per_line": 200,
    },
    "rhyme": {
        "enabled": True,
        "on": "lower",                  # upper | lower | both | every
        "strict": True,
        "change_allowed_per_stanza": True,
        "ban_same_char": True,
        "unknown": "warn",              # warn | error | ignore
    },
    "tone": {
        "enabled": False,
        "pattern": None,                # 如 "平平仄仄平平仄"，对所有句生效
        "patterns": None,               # 或 {"upper": "...", "lower": "..."} 按上下句分别定式
        "strictness": "warn",           # warn | error
        "free_rhyme_position": True,
    },
    "repeat": {
        "max_identical_lines": 1,
        "max_identical_clauses": 2,
        "max_same_rhyme_char_consecutive": 1,
    },
    "punctuation": {
        "require_end": False,
        "allowed_end": END_PUNCT,
    },
    "overrides": {},
}


# ---------------------------------------------------------------- 数据结构
@dataclass
class Clause:
    text: str
    start: int                      # 原文绝对偏移
    chars: list = field(default_factory=list)   # [(ch, abs_off)]

    @property
    def body(self) -> str:
        return self.text.rstrip(CLAUSE_DELIMS + " \t\u3000")


@dataclass
class Line:
    index: int                      # 段内序号，从 1 开始
    start: int
    raw: str
    clauses: list = field(default_factory=list)
    chars: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(c for c, _ in self.chars)


@dataclass
class Stanza:
    index: int
    lines: list = field(default_factory=list)


# ---------------------------------------------------------------- 词表
_TABLE = None


def load_table() -> dict:
    global _TABLE
    if _TABLE is None:
        if not TABLE_PATH.exists():
            _TABLE = {"meta": {"schemes": SCHEMES}, "map": {}}
        else:
            _TABLE = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLE


def resolve_char(ch: str, overrides: dict) -> tuple:
    """
    返回 (辙序号 | None, 声调 | None, '平'/'仄'/None)
    overrides 支持 "江阳|2" / "2" / "平" / "江阳" 四种写法。
    """
    scheme = tone = pz = None
    raw = overrides.get(ch)
    if raw:
        for part in str(raw).split("|"):
            part = part.strip()
            if part in SCHEMES:
                scheme = SCHEMES.index(part)
            elif part in ("平", "仄"):
                pz = part
            elif part.isdigit():
                tone = int(part)
    if scheme is None or tone is None or pz is None:
        cell = load_table()["map"].get(ch)
        if cell:
            s, t = cell.split("|")
            if scheme is None:
                scheme = int(s)
            if tone is None:
                tone = int(t)
    if pz is None and tone is not None:
        if tone in (1, 2):
            pz = "平"
        elif tone in (3, 4):
            pz = "仄"
    return scheme, tone, pz


# ---------------------------------------------------------------- 规则
def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def available_presets() -> list:
    if not RULES_DIR.exists():
        return []
    return sorted(p.stem for p in RULES_DIR.glob("*.json") if p.stem != "schema")


def load_rules(rules=None, preset=None) -> tuple:
    """返回 (rules_dict, 错误信息 | None)"""
    if preset:
        p = RULES_DIR / f"{preset}.json"
        if not p.exists():
            return None, f"找不到预设规则「{preset}」，可用：{', '.join(available_presets()) or '（无）'}"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return None, f"预设「{preset}」JSON 解析失败：{e}"
        return _deep_merge(DEFAULT_RULES, data), None

    if rules is None:
        return _deep_merge(DEFAULT_RULES, {}), None

    if isinstance(rules, (str, Path)):
        p = Path(rules)
        if not p.exists():
            return None, f"规则文件不存在：{p}"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return None, f"规则文件 JSON 解析失败：{e}"
        return _deep_merge(DEFAULT_RULES, data), None

    if isinstance(rules, dict):
        return _deep_merge(DEFAULT_RULES, rules), None

    return None, f"rules 参数类型不支持：{type(rules).__name__}，应为 dict / 路径 / None"


def validate_rules(rules: dict) -> list:
    """返回规则自身的问题列表 [(code, message)]"""
    bad = []
    st = rules.get("structure", {})
    lc = st.get("line_chars") or {}
    lo, hi = lc.get("min"), lc.get("max")
    if lo is not None and hi is not None and lo > hi:
        bad.append(("RULE_CHAR_RANGE", f"line_chars.min={lo} 大于 max={hi}，无法判定"))
    for k in ("min_lines_per_stanza", "max_lines_per_stanza", "max_chars_per_line"):
        v = st.get(k)
        if v is not None and (not isinstance(v, int) or v < 0):
            bad.append(("RULE_BAD_VALUE", f"structure.{k} 应为非负整数，实际是 {v!r}"))

    rh = rules.get("rhyme", {})
    if rh.get("on") not in ("upper", "lower", "both", "every"):
        bad.append(("RULE_BAD_VALUE",
                    f"rhyme.on 只能是 upper/lower/both/every，实际是 {rh.get('on')!r}"))
    if rh.get("unknown") not in ("warn", "error", "ignore"):
        bad.append(("RULE_BAD_VALUE",
                    f"rhyme.unknown 只能是 warn/error/ignore，实际是 {rh.get('unknown')!r}"))

    tn = rules.get("tone", {})
    if tn.get("enabled"):
        pt = tn.get("pattern")
        pats = tn.get("patterns")
        if not pt and not pats:
            bad.append(("RULE_TONE_NO_PATTERN",
                        "tone.enabled=true 但没有给 tone.pattern 或 tone.patterns，无法校验平仄"))
        for label, val in [("tone.pattern", pt)] + \
                          [(f"tone.patterns.{k}", v) for k, v in (pats or {}).items()]:
            if val is None:
                continue
            if not isinstance(val, str) or set(val) - set("平仄中"):
                bad.append(("RULE_TONE_BAD_PATTERN",
                            f"{label} 只能由「平/仄/中」组成，实际是 {val!r}"))
        if pats is not None and not isinstance(pats, dict):
            bad.append(("RULE_TONE_BAD_PATTERN", "tone.patterns 应为对象，如 {\"upper\": \"…\", \"lower\": \"…\"}"))
        elif isinstance(pats, dict) and set(pats) - {"upper", "lower"}:
            bad.append(("RULE_TONE_BAD_PATTERN",
                        f"tone.patterns 只支持 upper / lower 两个键，实际是 {list(pats)}"))
    return bad


# ---------------------------------------------------------------- 解析
def _iter_cjk(s: str, base: int):
    for i, ch in enumerate(s):
        if CJK_RE.match(ch):
            yield ch, base + i


def _parse_clauses(raw: str, base: int) -> list:
    out, buf, buf_start = [], "", 0
    for i, ch in enumerate(raw):
        if not buf:
            buf_start = i
        buf += ch
        if ch in CLAUSE_DELIMS:
            out.append(Clause(buf, base + buf_start))
            buf = ""
    if buf.strip():
        out.append(Clause(buf, base + buf_start))
    for c in out:
        c.chars = list(_iter_cjk(c.text, c.start))
    return [c for c in out if c.chars or c.text.strip()]


def parse(text: str) -> list:
    """文本 → [Stanza(lines=[Line(clauses=[])])]，保留原文绝对偏移。"""
    stanzas, cur = [], []
    off = 0
    for part in text.split("\n"):
        if part.strip() == "":
            if cur:
                stanzas.append(cur)
                cur = []
        else:
            cur.append((part, off))
        off += len(part) + 1
    if cur:
        stanzas.append(cur)

    result = []
    for si, raw_lines in enumerate(stanzas, 1):
        st = Stanza(index=si)
        for li, (raw, start) in enumerate(raw_lines, 1):
            line = Line(index=li, start=start, raw=raw)
            line.clauses = _parse_clauses(raw, start)
            for c in line.clauses:
                line.chars.extend(c.chars)
            if line.chars:
                st.lines.append(line)
        if st.lines:
            result.append(st)
    return result


# ---------------------------------------------------------------- 问题构造
def _issue(code, severity, type_, message, *, stanza=None, line=None, clause=None,
           char=None, offset=None, raw=None, suggestion="", detail=""):
    loc = {}
    if stanza is not None:
        loc["stanza"] = stanza
    if line is not None:
        loc["line"] = line
    if clause is not None:
        loc["clause"] = clause
    if char is not None:
        loc["char"] = char
    if offset is not None:
        loc["offset"] = offset
    if raw:
        loc["text"] = raw

    parts = []
    if stanza is not None:
        parts.append(f"第{stanza}段")
    if line is not None:
        parts.append(f"第{line}句")
    if clause is not None:
        parts.append(f"第{clause}分句")
    if char is not None:
        parts.append(f"第{char}字")
    loc["phrase"] = "".join(parts) or "全文"

    return {
        "code": code,
        "severity": severity,
        "type": type_,
        "location": loc,
        "message": message,
        "detail": detail,
        "suggestion": suggestion,
    }


def _rhyme_hint(scheme_idx, exclude_chars=""):
    """从同辙常用字里挑几个不是已经用过的，作为换韵建议。"""
    if scheme_idx is None or scheme_idx not in COMMON_RHYME:
        return ""
    pool = [c for c in COMMON_RHYME[scheme_idx] if c not in exclude_chars]
    return "、".join(pool[:8])


# ---------------------------------------------------------------- 检查项
def check_char_count(rules, stanzas, issues):
    st = rules["structure"]
    lc = st.get("line_chars") or {}
    lo, hi = lc.get("min"), lc.get("max")
    clause_chars = st.get("clause_chars")
    max_line = st.get("max_chars_per_line")

    for s in stanzas:
        for ln in s.lines:
            n = len(ln.chars)
            if max_line and n > max_line:
                issues.append(_issue(
                    "W_LONG_LINE", "warning", "句式字数",
                    f"{n} 字，超过单句上限 {max_line} 字，疑似未分行",
                    stanza=s.index, line=ln.index, raw=ln.text[:30],
                    suggestion="检查是否漏了换行；唱词通常一句一行。"))
                continue

            if lo is None and hi is None:
                # 行级字数不限，仍要检查分句字数
                if clause_chars:
                    _check_clauses(s, ln, clause_chars, issues)
                continue

            want = (f"要求 {lo} 字" if lo == hi and lo is not None
                    else f"要求 {lo or '不限'}–{hi or '不限'} 字")
            if (lo is not None and n < lo) or (hi is not None and n > hi):
                delta = (n - hi) if (hi is not None and n > hi) else (lo - n)
                word = "超出" if (hi is not None and n > hi) else "缺少"
                sug = _count_suggestion(ln, delta, direction=("over" if word == "超出" else "under"))
                issues.append(_issue(
                    "E_CHAR_COUNT", "error", "句式字数",
                    f"本句 {n} 字，{want}，{word} {abs(delta)} 字",
                    stanza=s.index, line=ln.index, char=n, offset=ln.chars[-1][1],
                    raw=ln.text, suggestion=sug))

            if clause_chars:
                _check_clauses(s, ln, clause_chars, issues)


def _check_clauses(s, ln, clause_chars, issues):
    for ci, c in enumerate(ln.clauses, 1):
        if ci - 1 >= len(clause_chars):
            break
        want_n = clause_chars[ci - 1]
        got = len(c.chars)
        if got != want_n:
            issues.append(_issue(
                "E_CLAUSE_CHARS", "error", "句式字数",
                f"本分句 {got} 字，规则要求 {want_n} 字",
                stanza=s.index, line=ln.index, clause=ci,
                raw=c.body, suggestion=f"调整到 {want_n} 字，或修改 clause_chars 规则"))


def _count_suggestion(ln: Line, delta: int, direction: str) -> str:
    if direction == "over":
        for i, (ch, _) in enumerate(ln.chars, 1):
            if ch in FUNCTION_WORDS:
                return f"第 {i} 字「{ch}」是虚词，删去后即可减 1 字"
        return f"可删去一个虚词（的/了/就/便/也），或在该句分句处断开"
    return "可补一个衬字（又/就/便/也/还），或与相邻句合并后重新断句"


def check_structure(rules, stanzas, issues):
    st = rules["structure"]
    need_couplet = st.get("couplet_required", True)
    mn, mx = st.get("min_lines_per_stanza"), st.get("max_lines_per_stanza")

    for s in stanzas:
        n = len(s.lines)
        if mn and n < mn:
            issues.append(_issue(
                "E_STANZA_TOO_SHORT", "error", "段落格式",
                f"本段只有 {n} 句，规则要求至少 {mn} 句",
                stanza=s.index, suggestion=f"补足到 {mn} 句以上，或与上一段合并"))
        if mx and n > mx:
            issues.append(_issue(
                "E_STANZA_TOO_LONG", "error", "段落格式",
                f"本段有 {n} 句，超过规则上限 {mx} 句",
                stanza=s.index, suggestion=f"建议在语义转折处断开为两段，每段不超过 {mx} 句"))
        if need_couplet and n % 2 == 1:
            issues.append(_issue(
                "E_COUPLET_ODD", "error", "上下句配对",
                f"本段 {n} 句为奇数，上下句须成对",
                stanza=s.index, line=n,
                suggestion="补一句下句，或删去末句使其成对"))


def _rhyme_positions(n_lines: int, mode: str) -> list:
    if mode == "upper":
        return [i for i in range(1, n_lines + 1) if i % 2 == 1]
    if mode == "lower":
        return [i for i in range(1, n_lines + 1) if i % 2 == 0]
    if mode == "both":
        return list(range(1, n_lines + 1))
    return list(range(1, n_lines + 1))


def check_rhyme(rules, stanzas, issues):
    rh = rules["rhyme"]
    if not rh.get("enabled"):
        return None
    overrides = rules.get("overrides") or {}
    mode = rh.get("on", "lower")
    unknown_policy = rh.get("unknown", "warn")

    stanza_scheme = {}
    tail_info = {}

    for s in stanzas:
        positions = _rhyme_positions(len(s.lines), mode)
        used = []
        for pos in positions:
            ln = s.lines[pos - 1]
            ch, off = ln.chars[-1]
            scheme, tone, pz = resolve_char(ch, overrides)
            tail_info[(s.index, pos)] = (ch, scheme, off)
            if scheme is None:
                if unknown_policy != "ignore":
                    issues.append(_issue(
                        "W_RHYME_UNKNOWN",
                        "error" if unknown_policy == "error" else "warning",
                        "押韵",
                        f"句尾「{ch}」未收录于韵表，无法判断所属辙口",
                        stanza=s.index, line=pos, char=len(ln.chars), offset=off, raw=ch,
                        suggestion="把该字补充到 rules.overrides，例如 {\"%s\": \"江阳|2\"}" % ch))
                continue
            used.append((scheme, ch, pos))

        if used:
            counts = {}
            for sc, _, _ in used:
                counts[sc] = counts.get(sc, 0) + 1
            best = max(counts.items(), key=lambda kv: (kv[1], [u[2] for u in used if u[0] == kv[0]][-1]))
            stanza_scheme[s.index] = best[0]

    # 段内是否同辙
    for s in stanzas:
        sch = stanza_scheme.get(s.index)
        if sch is None:
            continue
        for pos in _rhyme_positions(len(s.lines), mode):
            info = tail_info.get((s.index, pos))
            if not info or info[1] is None:
                continue
            ch, sc, off = info
            if rh.get("strict", True) and sc != sch:
                issues.append(_issue(
                    "E_RHYME_MISMATCH", "error", "押韵",
                    f"句尾「{ch}」属{SCHEMES[sc]}辙，与本段韵脚{SCHEMES[sch]}辙不一致",
                    stanza=s.index, line=pos, char=len(s.lines[pos - 1].chars),
                    offset=off, raw=ch,
                    suggestion=f"换成{SCHEMES[sch]}辙的字，例如：{_rhyme_hint(sch, ch)}"))

    # 段间是否允许换辙
    if not rh.get("change_allowed_per_stanza", True):
        seen = None
        for s in stanzas:
            sch = stanza_scheme.get(s.index)
            if sch is None:
                continue
            if seen is None:
                seen = (sch, s.index)
            elif sch != seen[0]:
                issues.append(_issue(
                    "E_RHYME_SCHEME_CHANGE", "error", "押韵",
                    f"本段用{SCHEMES[sch]}辙，但第{seen[1]}段已用{SCHEMES[seen[0]]}辙；"
                    f"规则不允许段间换辙",
                    stanza=s.index, raw=SCHEMES[sch],
                    suggestion=f"统一为{SCHEMES[seen[0]]}辙，或开启 rhyme.change_allowed_per_stanza"))

    # 韵脚重字
    if rh.get("ban_same_char", True):
        limit = rules["repeat"].get("max_same_rhyme_char_consecutive", 1)
        for s in stanzas:
            seq = [_ for _ in (_rhyme_seq(s, mode, tail_info)) if _]
            run, prev = 0, None
            for ch, pos in seq:
                if ch == prev:
                    run += 1
                    if run >= limit:
                        issues.append(_issue(
                            "W_RHYME_SAME_CHAR", "warning", "韵脚重复",
                            f"连续押同一个字「{ch}」（第{pos}句），行内一般避免同字相押",
                            stanza=s.index, line=pos, raw=ch,
                            suggestion=f"保留一处，另一处换成同辙字：{_rhyme_hint(stanza_scheme.get(s.index), ch)}"))
                else:
                    run = 0
                prev = ch
    return stanza_scheme


def _rhyme_seq(stanza, mode, tail_info):
    for pos in _rhyme_positions(len(stanza.lines), mode):
        info = tail_info.get((stanza.index, pos))
        if info:
            yield info[0], pos


def check_tone(rules, stanzas, issues):
    tn = rules["tone"]
    if not tn.get("enabled"):
        return
    pattern = tn.get("pattern") or ""
    patterns = tn.get("patterns") or {}
    sev = tn.get("strictness", "warn")
    severity = "error" if sev == "error" else "warning"
    free_rhyme = tn.get("free_rhyme_position", True)
    overrides = rules.get("overrides") or {}
    rhyme_mode = rules["rhyme"].get("on", "lower")

    for s in stanzas:
        rhyme_pos = set(_rhyme_positions(len(s.lines), rhyme_mode))
        for ln in s.lines:
            # 上句（奇数）用 upper 定式，下句（偶数）用 lower，缺省回落到通用 pattern
            pat = patterns.get("upper" if ln.index % 2 == 1 else "lower") or pattern
            if not pat:
                continue
            limit = min(len(pat), len(ln.chars))
            for i in range(limit):
                want = pat[i]
                if want == "中":
                    continue
                if free_rhyme and ln.index in rhyme_pos and i == len(ln.chars) - 1:
                    continue
                ch, off = ln.chars[i]
                _, tone, pz = resolve_char(ch, overrides)
                if pz is None:
                    issues.append(_issue(
                        "W_TONE_UNKNOWN", "warning", "平仄",
                        f"「{ch}」为轻声或无法判定声调，平仄待定",
                        stanza=s.index, line=ln.index, char=i + 1, offset=off, raw=ch,
                        suggestion="该字为轻声，建议换用有固定声调的字，或在 overrides 中指定"))
                    continue
                if pz != want:
                    issues.append(_issue(
                        "TONE_MISMATCH", severity, "平仄",
                        f"「{ch}」为{pz}声（第{tone}声），格律要求{want}声",
                        stanza=s.index, line=ln.index, char=i + 1, offset=off, raw=ch,
                        suggestion=f"调整用字使其为{want}声，或放宽该字的规则（pattern 写作「中」）"))


def check_repeat(rules, stanzas, issues):
    rp = rules["repeat"]
    max_lines = rp.get("max_identical_lines", 1)
    max_clauses = rp.get("max_identical_clauses", 2)

    line_seen = {}
    clause_seen = {}
    for s in stanzas:
        for ln in s.lines:
            key = ln.text
            line_seen.setdefault(key, []).append((s.index, ln))
            for c in ln.clauses:
                ck = c.body
                if ck:
                    clause_seen.setdefault(ck, []).append((s.index, ln, c))

    for key, occ in line_seen.items():
        if len(occ) > max_lines:
            for s_idx, ln in occ[max_lines:]:
                issues.append(_issue(
                    "W_REPEAT_LINE", "warning", "重复",
                    f"本句与前文完全相同（共出现 {len(occ)} 次）：{key[:24]}",
                    stanza=s_idx, line=ln.index, raw=key,
                    suggestion="若是有意叠句，请把 repeat.max_identical_lines 调大；否则改写其中一处"))

    for key, occ in clause_seen.items():
        if len(occ) > max_clauses:
            for s_idx, ln, c in occ[max_clauses:]:
                issues.append(_issue(
                    "W_REPEAT_CLAUSE", "warning", "重复",
                    f"本分句与前文重复（共 {len(occ)} 次）：{key[:20]}",
                    stanza=s_idx, line=ln.index, raw=key,
                    suggestion="确认是否为衬词叠用；若非有意，改写其中一处"))


def check_punctuation(rules, stanzas, issues):
    pu = rules["punctuation"]
    if not pu.get("require_end"):
        return
    allowed = pu.get("allowed_end") or END_PUNCT
    for s in stanzas:
        for ln in s.lines:
            stripped = ln.raw.rstrip()
            if not stripped:
                continue
            if stripped[-1] not in allowed:
                issues.append(_issue(
                    "W_NO_END_PUNCT", "warning", "标点",
                    f"句末缺少标点，当前以「{stripped[-1]}」结尾",
                    stanza=s.index, line=ln.index, raw=stripped[-12:],
                    suggestion=f"句末补上 {allowed} 之一"))


# ---------------------------------------------------------------- 主入口
def _empty_summary(errors=0, warnings=0, infos=0):
    return {"errors": errors, "warnings": warnings, "infos": infos,
            "stanzas": 0, "lines": 0, "clauses": 0, "chars": 0, "rhyme_schemes": {}}


def check(text, rules=None, preset=None) -> dict:
    """
    校验唱词。

    text   : str            唱词文本，用换行分句、空行分段
    rules  : dict|str|Path  规则字典，或规则 JSON 文件路径
    preset : str            rules/ 下的预设名（与 rules 二选一，preset 优先）

    返回结构化结果，见 README。
    """
    result = {
        "passed": False,
        "score": 0,
        "summary": _empty_summary(),
        "issues": [],
        "lines": [],
        "rule_used": {},
    }

    # --- 规则
    rs, err = load_rules(rules, preset)
    if rs is None:
        result["issues"].append(_issue("E_RULE_NOT_FOUND", "error", "规则", err or "规则无效",
                                       suggestion="用 --list 查看可用预设"))
        result["summary"] = _empty_summary(errors=1)
        return result

    bad = validate_rules(rs)
    if bad:
        for code, msg in bad:
            result["issues"].append(_issue(code, "error", "规则", msg,
                                           suggestion="修正规则文件后重试"))
        result["summary"] = _empty_summary(errors=len(bad))
        result["rule_used"] = _rule_meta(rs)
        return result

    result["rule_used"] = _rule_meta(rs)

    # --- 输入
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)

    if not text.strip():
        result["issues"].append(_issue(
            "E_EMPTY_INPUT", "error", "输入",
            "唱词为空或只有空白字符",
            suggestion="请提供用换行分句、空行分段的唱词文本"))
        result["summary"] = _empty_summary(errors=1)
        return result

    stanzas = parse(text)
    if not stanzas:
        result["issues"].append(_issue(
            "E_NO_CJK", "error", "输入",
            "未检测到中文唱词（只有标点、空白或非中文字符）",
            suggestion="确认输入为中文唱词；标点单独成行会被忽略"))
        result["summary"] = _empty_summary(errors=1)
        return result

    # --- 各项检查
    issues = []
    check_char_count(rs, stanzas, issues)
    check_structure(rs, stanzas, issues)
    scheme = check_rhyme(rs, stanzas, issues)
    check_tone(rs, stanzas, issues)
    check_repeat(rs, stanzas, issues)
    check_punctuation(rs, stanzas, issues)

    issues.sort(key=lambda i: (i["location"].get("stanza", 0),
                               i["location"].get("line", 0),
                               i["location"].get("char", 0)))

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    infos = sum(1 for i in issues if i["severity"] == "info")

    overrides = rs.get("overrides") or {}
    for s in stanzas:
        for ln in s.lines:
            ch, off = ln.chars[-1] if ln.chars else ("", None)
            sc, tone, pz = resolve_char(ch, overrides) if ch else (None, None, None)
            result["lines"].append({
                "stanza": s.index,
                "line": ln.index,
                "chars": len(ln.chars),
                "text": ln.text,
                "rhyme_char": ch,
                "rhyme_scheme": SCHEMES[sc] if sc is not None else None,
                "rhyme_tone": tone,
            })

    result["issues"] = issues
    result["summary"] = {
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "stanzas": len(stanzas),
        "lines": sum(len(s.lines) for s in stanzas),
        "clauses": sum(len(ln.clauses) for s in stanzas for ln in s.lines),
        "chars": sum(len(ln.chars) for s in stanzas for ln in s.lines),
        "rhyme_schemes": {str(k): SCHEMES[v] for k, v in (scheme or {}).items()},
    }
    result["passed"] = errors == 0
    result["score"] = max(0, 100 - 12 * errors - 3 * warnings)
    return result


def _rule_meta(rs):
    m = rs.get("meta", {})
    return {
        "name": m.get("name", ""),
        "confidence": m.get("confidence", "custom"),
        "source": m.get("source", ""),
        "warning": m.get("warning", ""),
    }


# ---------------------------------------------------------------- 人类可读输出
ICON = ({"error": "✗", "warning": "⚠", "info": "·"} if _FANCY
        else {"error": "[X]", "warning": "[!]", "info": "[i]"})
_PASS_TXT, _FAIL_TXT = ("通过 ✓", "未通过 ✗") if _FANCY else ("[通过]", "[未通过]")


def render(result) -> str:
    out = []
    s = result["summary"]
    meta = result.get("rule_used") or {}

    head = _PASS_TXT if result["passed"] else _FAIL_TXT
    out.append(f"【{head}】得分 {result['score']}　规则：{meta.get('name','')}"
               f"（可信度：{meta.get('confidence','')}）")
    if meta.get("warning"):
        out.append(f"  注意：{meta['warning']}")
    out.append(f"  共 {s.get('stanzas',0)} 段 / {s.get('lines',0)} 句 / "
               f"{s.get('chars',0)} 字　错误 {s.get('errors',0)}，警告 {s.get('warnings',0)}")
    if s.get("rhyme_schemes"):
        out.append("  各段韵脚：" + "，".join(
            f"第{k}段 {v}" for k, v in s["rhyme_schemes"].items()))

    if result["issues"]:
        out.append("")
        for i in result["issues"]:
            icon = ICON.get(i["severity"], "·")
            out.append(f"  {icon} [{i['type']}] {i['location']['phrase']}：{i['message']}")
            if i.get("suggestion"):
                out.append(f"      建议：{i['suggestion']}")
    return "\n".join(out)


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="皮影戏唱词格律校验器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python check_lyrics.py --file demo.txt --preset tangshan_qizi\n"
               "  python check_lyrics.py --text \"一年春尽一年春\\n花开花谢又逢春\" --preset generic_couplet\n")
    ap.add_argument("--text", help="直接传入唱词文本")
    ap.add_argument("--file", help="从文件读取唱词（UTF-8）")
    ap.add_argument("--preset", help="预设规则名")
    ap.add_argument("--rules", help="自定义规则 JSON 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--list", action="store_true", help="列出可用预设")
    args = ap.parse_args(argv)

    if args.list:
        presets = available_presets()
        if not presets:
            print("（rules/ 下没有预设）")
        for name in presets:
            p = RULES_DIR / f"{name}.json"
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                m = d.get("meta", {})
                print(f"{name:24s} {m.get('name','')}　[{m.get('confidence','')}]")
            except Exception:
                print(f"{name:24s} （解析失败）")
        return 0

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"错误：文件不存在 {p}", file=sys.stderr)
            return 2
        text = p.read_text(encoding="utf-8")
    elif args.text:
        text = args.text.replace("\\n", "\n")
    else:
        text = sys.stdin.read()

    res = check(text, rules=args.rules, preset=args.preset)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
