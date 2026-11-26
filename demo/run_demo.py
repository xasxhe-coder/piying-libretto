# -*- coding: utf-8 -*-
"""
run_demo.py — 唱词格律校验器的使用场景演示

每条场景都是真跑，不是示例文案。用于汇报现场或新人上手。

    python demo/run_demo.py          # 全部场景
    python demo/run_demo.py 3        # 只看第 3 个场景
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_lyrics import check, render  # noqa: E402

BAR = "=" * 72
THIN = "-" * 72


def head(no, title, story):
    print()
    print(BAR)
    print(f"场景 {no}｜{title}")
    print(THIN)
    print(story.strip())
    print()


def note(text):
    print()
    print("  ▸ " + text.replace("\n", "\n  ▸ "))


def by_type(res):
    agg = {}
    for i in res["issues"]:
        agg.setdefault((i["type"], i["severity"]), 0)
        agg[(i["type"], i["severity"])] += 1
    return agg


# ------------------------------------------------------------------ 场景 1
def s1():
    head(1, "现场质检：AI 写了一段唱词，能不能唱？", """
  最常用的场景。生成的唱词看着漂亮，但一句都合不上律。
  把稿子丢进来，要的是"第几段第几句第几个字、什么毛病、怎么改"。
""")
    text = """一笔写尽这千年事，
灯下英雄各争先。
锣鼓一响人如潮，
唱尽人间一段春。"""
    print("  输入：")
    for ln in text.split("\n"):
        print("    " + ln)
    r = check(text, preset="tangshan_qizi")
    print()
    print(render(r))
    note('它不是「像不像」，是有坐标的判定。这句话在汇报里可以直接说。')


# ------------------------------------------------------------------ 场景 2
def s2():
    head(2, "只说不对没用：要给出同辙的替代字", """
  第二句尾字"年"属言前辙，但本段韵脚是人辰辙。
  工具不只报错，还从同辙常用字里挑出能换的——编剧拿起来就能改。
""")
    text = """一年春尽一年春，
花开花谢又逢年。
光阴似箭催人老，
日月如梭不待人。"""
    print("  输入：")
    for ln in text.split("\n"):
        print("    " + ln)
    r = check(text, preset="tangshan_qizi")
    print()
    for i in r["issues"]:
        print(f"  [{i['type']}] {i['location']['phrase']}")
        print(f"    问题：{i['message']}")
        print(f"    建议：{i['suggestion']}")
    note("替代字来自每辙约 16 个常用字，只是候选，不改艺术判断。")


# ------------------------------------------------------------------ 场景 3
def s3():
    head(3, "改稿闭环：改完再审，直到过审", """
  把「年」换成「春」，韵脚统一到人辰辙，整段通过。
  这才是一个完整的审核流程：判错 → 给建议 → 复审 → 放行。
""")
    text = """一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，
日月如梭不待人。"""
    print("  输入：")
    for ln in text.split("\n"):
        print("    " + ln)
    r = check(text, preset="tangshan_qizi")
    print()
    print(render(r))
    note('通过不等于完美，只等于「这条规则下没硬伤」。这句话要提前说，防止被追问。')


# ------------------------------------------------------------------ 场景 4
def s4():
    head(4, "批量体检：整本稿子一次过，出分类型统计", """
  单句校验是手工活，批量校验才是工程活。
  一个剧本文件丢进去，按类型汇总，直接给主编看。
""")
    text = """一年春尽一年春光，
花开花谢又逢年。
光阴似箭催人老，
日月如梭不待人。

一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，
日月如梭又是春。"""
    r = check(text, preset="tangshan_qizi")
    s = r["summary"]
    print(f"  共 {s['stanzas']} 段 / {s['lines']} 句 / {s['chars']} 字 "
          f"→ {'通过' if r['passed'] else '未通过'}，得分 {r['score']}")
    print(f"  错误 {s['errors']}，警告 {s['warnings']}")
    print()
    print("  按类型汇总：")
    for (t, sev), n in sorted(by_type(r).items(), key=lambda kv: -kv[1]):
        print(f"    {t:<6}（{sev:<7}） × {n}")
    print()
    print("  明细：")
    sev_cn = {"error": "错误", "warning": "警告", "info": "提示"}
    for i in r["issues"]:
        print(f"    [{sev_cn.get(i['severity'], i['severity'])}] "
              f"{i['location']['phrase']:<14} {i['message']}")
    note('这一屏就是「批次质量报告」。汇报时讲「能批量」，讲的就是它。')


# ------------------------------------------------------------------ 场景 5
def s5():
    head(5, "换规则不换代码：同一段词，两套标准", """
  同一段唱词，用"只查骨架"的规则是通过的；换成"七字句+平仄定式"就被挑出平仄问题。
  这说明工具和格律是分离的——换流派只是换一个 JSON。
""")
    text = """一年春尽一年春，
花开花谢又逢春。
光阴似箭催人老，
日月如梭不待人。"""
    for preset, label in [("tangshan_qizi", "唐山皮影·七字句（只查骨架）"),
                          ("seven_char_pingze_demo", "七字句+平仄定式（示例，警告不阻断通过）")]:
        r = check(text, preset=preset)
        s = r["summary"]
        print(f"  【{label}】")
        print(f"    结果={'通过' if r['passed'] else '不通过'}　得分={r['score']}　"
              f"错误{s['errors']} 警告{s['warnings']}")
        tones = [i for i in r["issues"] if i["type"] == "平仄"]
        for i in tones[:3]:
            print(f"    · {i['location']['phrase']}：{i['message']}")
        if len(tones) > 3:
            print(f"    · ……另有 {len(tones) - 3} 条")
        print()
    note("平仄定式是示例，不是史料。汇报时必须带上这句，否则就是过度承诺。")


# ------------------------------------------------------------------ 场景 6
def s6():
    head(6, "边界：多音字与方言，判错了怎么办？", """
  工具优先查内置韵表，查不到不猜。遇到方言读法或多音字，
  用规则里的 overrides 逐字覆盖——把你的判断喂给它，而不是让它替你判断。
""")
    text = """一年春尽一年春，
花开花谢又逢年。
光阴似箭催人老，
日月如梭不待人。"""
    r1 = check(text, preset="tangshan_qizi")
    print(f"  默认判定：{'通过' if r1['passed'] else '未通过'}，"
          f"问题码 {[i['code'] for i in r1['issues']]}")
    print()
    rules = {
        "meta": {"name": "示例：把「年」按方言归入人辰辙", "confidence": "custom",
                 "warning": "仅演示 overrides 用法，不代表任何流派实际读法"},
        "structure": {"line_chars": {"min": 7, "max": 7}},
        "rhyme": {"enabled": True, "on": "lower"},
        "overrides": {"年": "人辰|2"},
    }
    r2 = check(text, rules=rules)
    print(f"  加 overrides 后：{'通过' if r2['passed'] else '未通过'}，"
          f"问题码 {[i['code'] for i in r2['issues']]}")
    note('这是「工具不越权」的证据：判不准就报出来，让人来定，而不是编一个答案。')


# ------------------------------------------------------------------ 场景 7
def s7():
    head(7, "接进 AI 生成流程：把校验当闸门", """
  AI 岗最该演示的一环。生成器出稿 → 校验器判定 → 不过就退回重写。
  这一屏是"可执行的规则"，不是"事后人工检查"。
""")
    drafts = [
        "一年春尽一年春，\n花开花谢又逢年。\n光阴似箭催人老，\n日月如梭不待人。",
        "一年春尽一年春，\n花开花谢又逢春。\n光阴似箭催人老，\n日月如梭不待人。",
    ]
    for n, draft in enumerate(drafts, 1):
        r = check(draft, preset="tangshan_qizi")
        gate = "放行" if r["passed"] else "退回"
        print(f"  第 {n} 稿 → {gate}（得分 {r['score']}）")
        if not r["passed"]:
            for i in r["issues"]:
                if i["severity"] == "error":
                    print(f"      ↳ {i['location']['phrase']}：{i['message']}")
                    print(f"        改法：{i['suggestion']}")
        print()
    print("  接入代码只有一个判断：")
    print("      if not check(draft, preset='tangshan_qizi')['passed']:")
    print("          draft = regenerate(带 issues 重新生成)")
    note('汇报落点：AI 负责快，人负责对；而「对」这一条，我们写成了可执行的代码。')


SCENES = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7}


def main():
    picks = [int(a) for a in sys.argv[1:] if a.isdigit()] or sorted(SCENES)
    print("唱词格律校验器 · 使用场景演示")
    print(f"（共 {len(picks)} 个场景，全部为真实运行结果）")
    for n in picks:
        SCENES[n]()
    print()
    print(BAR)
    print("演示结束。以上输出均由 scripts/check_lyrics.py 实际产生。")
    print(BAR)


if __name__ == "__main__":
    main()
