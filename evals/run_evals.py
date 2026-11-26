# -*- coding: utf-8 -*-
"""
run_evals.py — 跑验收用例并出成绩单

用法：
    python evals/run_evals.py            # 跑全部，打印成绩单
    python evals/run_evals.py -v         # 附带每条用例的问题码
    python evals/run_evals.py --json     # 机器可读
退出码：全过 0，有不过 1。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_lyrics import check  # noqa: E402

CASES = ROOT / "evals" / "cases.json"


def _supports(ch):
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        ch.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_FANCY = _supports("✓")
MARK_OK, MARK_BAD = ("✓", "✗") if _FANCY else ("OK", "XX")
BAR_ON, BAR_OFF = ("█", "░") if _FANCY else ("#", "-")


def run_one(case):
    res = check(case.get("text", ""),
                rules=case.get("rules"),
                preset=case.get("preset"))
    got = {i["code"] for i in res["issues"]}
    fails = []

    if res["passed"] != case.get("expect_pass"):
        fails.append(f"passed 期望 {case.get('expect_pass')}，实际 {res['passed']}")
    for c in case.get("expect_codes", []):
        if c not in got:
            fails.append(f"缺少问题码 {c}")
    for c in case.get("forbid_codes", []):
        if c in got:
            fails.append(f"不应出现 {c}")

    return {
        "id": case["id"],
        "name": case["name"],
        "ok": not fails,
        "fails": fails,
        "passed": res["passed"],
        "score": res["score"],
        "codes": sorted(got),
        "errors": res["summary"].get("errors", 0),
        "warnings": res["summary"].get("warnings", 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = data["cases"]
    results = [run_one(c) for c in cases]

    ok = sum(1 for r in results if r["ok"])
    total = len(results)

    if args.json:
        print(json.dumps({"total": total, "passed": ok, "results": results},
                         ensure_ascii=False, indent=2))
        return 0 if ok == total else 1

    print(f"{data['meta']['name']}  v{data['meta']['version']}")
    print("=" * 68)
    for r in results:
        mark = MARK_OK if r["ok"] else MARK_BAD
        line = (f"{mark} {r['id']}  {r['name']:<22} "
                f"结果={'通过' if r['passed'] else '不通过':<4} 得分={r['score']:>3}")
        if args.verbose and r["codes"]:
            line += "  [" + ",".join(r["codes"]) + "]"
        print(line)
        for f in r["fails"]:
            print(f"      ! {f}")
    print("=" * 68)
    bar = BAR_ON * ok + BAR_OFF * (total - ok)
    print(f"{bar}  {ok}/{total} 通过  ({ok / total:.0%})")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
