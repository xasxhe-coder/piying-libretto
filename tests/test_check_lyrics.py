# -*- coding: utf-8 -*-
"""
test_check_lyrics.py — 唱词格律校验器的单元测试

运行：
    python -m unittest discover -s tests -v
或：
    python tests/test_check_lyrics.py
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_lyrics import check, resolve_char, parse, available_presets, SCHEMES  # noqa: E402

# ---------------------------------------------------------------- 样本
GOOD = """一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，
日月如梭不待人。"""

SAME_CHAR = """一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，
日月如梭又是春。"""

RHYME_MIX = """一年春尽一年春，
花开花谢又逢年。
光阴似箭催人老，
日月如梭不待人。"""

EIGHT_CHARS = """一年春尽一年春光，
花开花谢又逢春。
光阴似箭催人老，
日月如梭不待人。"""

ODD_LINES = """一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，"""

NO_PUNCT = """一年春尽一年春
花开花谢又逢春
光阴似箭催人老
日月如梭不待人"""

REPEAT = """一年春尽一年春，
花开花谢又逢春。
一年春尽一年春，
日月如梭不待人。"""


def codes(res):
    return [i["code"] for i in res["issues"]]


class TestBasics(unittest.TestCase):
    def test_good_passes(self):
        r = check(GOOD, preset="tangshan_qizi")
        self.assertTrue(r["passed"], codes(r))
        self.assertEqual(r["summary"]["errors"], 0)
        self.assertEqual(r["summary"]["lines"], 4)
        self.assertEqual(r["summary"]["chars"], 28)
        self.assertIn("1", r["summary"]["rhyme_schemes"])
        self.assertEqual(r["summary"]["rhyme_schemes"]["1"], "人辰")

    def test_result_schema(self):
        r = check(GOOD, preset="tangshan_qizi")
        for k in ("passed", "score", "summary", "issues", "lines", "rule_used"):
            self.assertIn(k, r)
        for k in ("errors", "warnings", "infos", "stanzas", "lines",
                  "clauses", "chars", "rhyme_schemes"):
            self.assertIn(k, r["summary"])
        # 必须能 JSON 序列化
        json.dumps(r, ensure_ascii=False)

    def test_line_detail(self):
        r = check(GOOD, preset="tangshan_qizi")
        self.assertEqual(len(r["lines"]), 4)
        first = r["lines"][0]
        self.assertEqual(first["chars"], 7)
        self.assertEqual(first["rhyme_char"], "春")
        self.assertEqual(first["rhyme_scheme"], "人辰")
        self.assertEqual(first["rhyme_tone"], 1)


class TestCharCount(unittest.TestCase):
    def test_over_length(self):
        r = check(EIGHT_CHARS, preset="tangshan_qizi")
        self.assertFalse(r["passed"])
        self.assertIn("E_CHAR_COUNT", codes(r))
        msg = next(i for i in r["issues"] if i["code"] == "E_CHAR_COUNT")
        self.assertIn("8 字", msg["message"])
        self.assertIn("要求 7 字", msg["message"])
        self.assertTrue(msg["suggestion"])

    def test_under_length(self):
        text = "一年春尽一年，\n花开花谢又逢春。"
        r = check(text, preset="tangshan_qizi")
        self.assertIn("E_CHAR_COUNT", codes(r))
        msg = next(i for i in r["issues"] if i["code"] == "E_CHAR_COUNT")
        self.assertIn("6 字", msg["message"])

    def test_variable_rule(self):
        rules = {"structure": {"line_chars": {"min": 5, "max": 9}},
                 "rhyme": {"enabled": False}}
        r = check(EIGHT_CHARS, rules=rules)
        self.assertTrue(r["passed"], codes(r))

    def test_clause_chars(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None},
                               "clause_chars": [3, 4], "couplet_required": False,
                               "min_lines_per_stanza": 1},
                 "rhyme": {"enabled": False}}
        r = check("一年春，尽一年春。", rules=rules)
        self.assertTrue(r["passed"], codes(r))
        r2 = check("一年，春尽一年春。", rules=rules)
        self.assertIn("E_CLAUSE_CHARS", codes(r2))


class TestStructure(unittest.TestCase):
    def test_odd_lines(self):
        r = check(ODD_LINES, preset="tangshan_qizi")
        self.assertIn("E_COUPLET_ODD", codes(r))
        self.assertFalse(r["passed"])

    def test_stanza_split(self):
        text = GOOD + "\n\n" + GOOD
        r = check(text, preset="tangshan_qizi")
        self.assertEqual(r["summary"]["stanzas"], 2)
        self.assertTrue(r["passed"], codes(r))

    def test_stanza_too_short(self):
        rules = {"structure": {"min_lines_per_stanza": 4, "line_chars": {"min": 7, "max": 7}},
                 "rhyme": {"enabled": False}}
        r = check("一年春尽一年春，\n花开花谢又逢春。", rules=rules)
        self.assertIn("E_STANZA_TOO_SHORT", codes(r))


class TestRhyme(unittest.TestCase):
    def test_mismatch_within_stanza(self):
        r = check(RHYME_MIX, preset="tangshan_qizi")
        self.assertIn("E_RHYME_MISMATCH", codes(r))
        m = next(i for i in r["issues"] if i["code"] == "E_RHYME_MISMATCH")
        self.assertIn("言前", m["message"])
        self.assertIn("人辰", m["message"])
        self.assertIn("辙", m["suggestion"])

    def test_same_rhyme_char(self):
        r = check(SAME_CHAR, preset="tangshan_qizi")
        self.assertIn("W_RHYME_SAME_CHAR", codes(r))

    def test_scheme_change_between_stanzas(self):
        other = """天边明月照高楼，
  江水东流不复回。"""  # 尾字 楼(由求) / 回(灰堆)
        rules = {
            "structure": {"line_chars": {"min": None, "max": None}},
            "rhyme": {"enabled": True, "on": "lower",
                      "change_allowed_per_stanza": False},
        }
        r = check(GOOD + "\n\n" + other, rules=rules)
        self.assertIn("E_RHYME_SCHEME_CHANGE", codes(r))

    def test_change_allowed(self):
        other = "天边明月照高楼，\n江水东流不复回。"
        rules = {"structure": {"line_chars": {"min": None, "max": None}},
                 "rhyme": {"enabled": True, "on": "lower"}}
        r = check(GOOD + "\n\n" + other, rules=rules)
        self.assertNotIn("E_RHYME_SCHEME_CHANGE", codes(r))

    def test_rhyme_disabled(self):
        r = check(RHYME_MIX, rules={"rhyme": {"enabled": False},
                                    "structure": {"line_chars": {"min": None, "max": None}}})
        self.assertNotIn("E_RHYME_MISMATCH", codes(r))


class TestTone(unittest.TestCase):
    def test_tone_mismatch_reported(self):
        r = check(GOOD, preset="seven_char_pingze_demo")
        self.assertIn("TONE_MISMATCH", codes(r))
        m = next(i for i in r["issues"] if i["code"] == "TONE_MISMATCH")
        self.assertIn("平声", m["message"] + m["detail"] + "")
        self.assertTrue(m["location"]["char"] >= 1)

    def test_tone_neutral_unknown(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None}},
                 "rhyme": {"enabled": False},
                 "tone": {"enabled": True, "pattern": "平平平平平平平"}}
        r = check("一年春尽了人间，\n花开花谢又逢春。", rules=rules)
        self.assertIn("W_TONE_UNKNOWN", codes(r))

    def test_tone_error_mode(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None}},
                 "rhyme": {"enabled": False},
                 "tone": {"enabled": True, "pattern": "仄仄仄仄仄仄仄",
                          "strictness": "error"}}
        r = check("一年春尽一年春，", rules=rules)
        self.assertFalse(r["passed"])
        self.assertTrue(any(i["severity"] == "error" for i in r["issues"]))

    def test_tone_patterns_per_parity(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None}},
                 "rhyme": {"enabled": False},
                 "tone": {"enabled": True,
                          "patterns": {"upper": "中中中中中中中",
                                       "lower": "中中中中中中中"}}}
        r = check("一年春尽一年春，\n花开花谢又逢春。", rules=rules)
        self.assertEqual([i for i in r["issues"] if i["type"] == "平仄"], [])


class TestRepeat(unittest.TestCase):
    def test_identical_line(self):
        r = check(REPEAT, preset="tangshan_qizi")
        self.assertIn("W_REPEAT_LINE", codes(r))

    def test_identical_clause_allowed_by_rule(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None}},
                 "rhyme": {"enabled": False},
                 "repeat": {"max_identical_clauses": 5}}
        r = check("一年春，一年春。\n一年春，一年春。", rules=rules)
        self.assertNotIn("W_REPEAT_CLAUSE", codes(r))


class TestPunctuation(unittest.TestCase):
    def test_missing_end_punct(self):
        r = check(NO_PUNCT, preset="tangshan_qizi")
        self.assertIn("W_NO_END_PUNCT", codes(r))

    def test_punct_not_required(self):
        r = check(NO_PUNCT, preset="generic_couplet")
        self.assertNotIn("W_NO_END_PUNCT", codes(r))


class TestEdgeInputs(unittest.TestCase):
    def test_empty(self):
        r = check("", preset="tangshan_qizi")
        self.assertFalse(r["passed"])
        self.assertEqual(codes(r), ["E_EMPTY_INPUT"])

    def test_whitespace_only(self):
        r = check("   \n\n\t  \n", preset="tangshan_qizi")
        self.assertIn("E_EMPTY_INPUT", codes(r))
        self.assertEqual(r["summary"]["stanzas"], 0)

    def test_punctuation_only(self):
        r = check("，。；！？\n\n。。。", preset="tangshan_qizi")
        self.assertIn("E_NO_CJK", codes(r))

    def test_english_only(self):
        r = check("Hello world\nthis is not lyrics", preset="tangshan_qizi")
        self.assertIn("E_NO_CJK", codes(r))

    def test_none_and_non_str(self):
        r = check(None, preset="tangshan_qizi")
        self.assertIn("E_EMPTY_INPUT", codes(r))
        r2 = check(12345, preset="tangshan_qizi")
        self.assertIn("E_NO_CJK", codes(r2))

    def test_crlf_and_bom(self):
        text = "\ufeff" + GOOD.replace("\n", "\r\n")
        r = check(text, preset="tangshan_qizi")
        self.assertTrue(r["passed"], codes(r))
        self.assertEqual(r["summary"]["lines"], 4)

    def test_zero_width(self):
        text = GOOD.replace("春", "春\u200b")
        r = check(text, preset="tangshan_qizi")
        self.assertTrue(r["passed"], codes(r))

    def test_very_long_line(self):
        rules = {"structure": {"line_chars": {"min": None, "max": None},
                               "max_chars_per_line": 20},
                 "rhyme": {"enabled": False}}
        r = check("一" * 30, rules=rules)
        self.assertIn("W_LONG_LINE", codes(r))

    def test_mixed_latin_inside(self):
        text = "一年春尽ABC春，\n花开花谢又逢春。"
        r = check(text, preset="tangshan_qizi")
        # 英文不计入字数，本句 6 字
        self.assertIn("E_CHAR_COUNT", codes(r))


class TestRules(unittest.TestCase):
    def test_unknown_preset(self):
        r = check(GOOD, preset="不存在的规则")
        self.assertIn("E_RULE_NOT_FOUND", codes(r))
        self.assertIn("tangshan_qizi", r["issues"][0]["message"])
        self.assertFalse(r["passed"])

    def test_bad_char_range(self):
        r = check(GOOD, rules={"structure": {"line_chars": {"min": 9, "max": 5}}})
        self.assertIn("RULE_CHAR_RANGE", codes(r))
        self.assertFalse(r["passed"])

    def test_bad_rhyme_mode(self):
        r = check(GOOD, rules={"rhyme": {"on": "middle"}})
        self.assertIn("RULE_BAD_VALUE", codes(r))

    def test_tone_without_pattern(self):
        r = check(GOOD, rules={"tone": {"enabled": True}})
        self.assertIn("RULE_TONE_NO_PATTERN", codes(r))

    def test_tone_bad_pattern(self):
        r = check(GOOD, rules={"tone": {"enabled": True, "pattern": "平仄甲乙"}})
        self.assertIn("RULE_TONE_BAD_PATTERN", codes(r))

    def test_rules_path(self):
        p = ROOT / "rules" / "tangshan_qizi.json"
        r = check(GOOD, rules=str(p))
        self.assertTrue(r["passed"], codes(r))

    def test_rules_missing_file(self):
        r = check(GOOD, rules="rules/不存在.json")
        self.assertIn("E_RULE_NOT_FOUND", codes(r))

    def test_rules_wrong_type(self):
        r = check(GOOD, rules=123)
        self.assertIn("E_RULE_NOT_FOUND", codes(r))


class TestOverrides(unittest.TestCase):
    def test_override_rhyme(self):
        sc_before, _, _ = resolve_char("春", {})
        self.assertEqual(SCHEMES[sc_before], "人辰")
        sc_after, _, _ = resolve_char("春", {"春": "言前|2"})
        self.assertEqual(SCHEMES[sc_after], "言前")

    def test_override_fixes_mismatch(self):
        rules = json.loads((ROOT / "rules" / "tangshan_qizi.json").read_text(encoding="utf-8"))
        rules["overrides"] = {"年": "人辰|2"}
        r = check(RHYME_MIX, rules=rules)
        self.assertNotIn("E_RHYME_MISMATCH", codes(r))

    def test_override_pingze(self):
        _, _, pz = resolve_char("春", {"春": "仄"})
        self.assertEqual(pz, "仄")


class TestPositions(unittest.TestCase):
    def test_offset_points_to_char(self):
        text = EIGHT_CHARS
        r = check(text, preset="tangshan_qizi")
        m = next(i for i in r["issues"] if i["code"] == "E_CHAR_COUNT")
        off = m["location"]["offset"]
        self.assertEqual(text[off], "光")
        self.assertEqual(m["location"]["stanza"], 1)
        self.assertEqual(m["location"]["line"], 1)

    def test_phrase_text(self):
        r = check(GOOD, preset="seven_char_pingze_demo")
        m = next(i for i in r["issues"] if i["code"] == "TONE_MISMATCH")
        self.assertRegex(m["location"]["phrase"], r"^第1段第\d句第\d字$")

    def test_parse_offsets(self):
        st = parse("一年春尽一年春，\n花开花谢又逢春。")
        self.assertEqual(len(st), 1)
        self.assertEqual(len(st[0].lines), 2)
        self.assertEqual(st[0].lines[0].start, 0)
        self.assertEqual(st[0].lines[1].start, 9)  # 8 字 + 逗号 + 换行

    def test_sorted_by_position(self):
        r = check(EIGHT_CHARS.replace("日月如梭不待人。", "日月如梭不待。" +
                                      "人。", 1), preset="tangshan_qizi")
        keys = [(i["location"].get("stanza", 0), i["location"].get("line", 0),
                 i["location"].get("char", 0)) for i in r["issues"]]
        self.assertEqual(keys, sorted(keys))


class TestPresets(unittest.TestCase):
    def test_all_presets_load(self):
        names = available_presets()
        self.assertIn("tangshan_qizi", names)
        for n in names:
            r = check(GOOD, preset=n)
            self.assertNotIn("E_RULE_NOT_FOUND", codes(r), n)

    def test_preset_metadata_present(self):
        r = check(GOOD, preset="tangshan_qizi")
        m = r["rule_used"]
        self.assertEqual(m["confidence"], "inferred")
        self.assertTrue(m["warning"])

    def test_render_runs(self):
        from check_lyrics import render
        out = render(check(EIGHT_CHARS, preset="tangshan_qizi"))
        self.assertIn("未通过", out)
        self.assertIn("建议", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
