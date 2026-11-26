---
name: piying-libretto
description: 校验皮影戏（及同类戏曲曲艺）唱词的格律——句式字数、分句逗位、上下句配对、押韵与韵脚、平仄、重复、段落格式。当用户要检查一段唱词是否合律、问"这几句字数和韵对不对"、需要指出第几段第几句第几字出错并给出改法、或要把某流派的格律写成可复用的规则时使用。不适用于：判断唱腔板式、旋律、身段表演，或没有规则依据时凭空断言某流派格律。
---

# 唱词格律校验

**一个把「格律」当规则、把「检查」当引擎的工具。**
引擎只管能不能判、怎么判；格律本身写在 `rules/*.json` 里，可替换、可扩展、可追溯出处。

## 什么时候用

- 用户给了一段唱词（或 AI 生成的唱词），问合不合律、哪里不对
- 需要给出**可定位**的结论：第几段、第几句、第几字、什么毛病、怎么改
- 要批量过一遍稿子，出结构化报告给下游高亮或入库
- 要把某位传承人/某份文献的格律要求固化成规则

**不要用它做的事**（会答错，且会误导用户）：

- 判断**板式**（大板/二性板/三性板）——本工具不读工尺谱，也不做旋律分析
- 判断**唱腔是否地道**——这需要听觉判断
- 在没有规则依据时断言"某流派就该这么写"——规则里 `meta.confidence` 会标明是文献记载、据名称推定、还是自定义

## 怎么用

命令行（最快）：

```bash
python scripts/check_lyrics.py --file 唱词.txt --preset tangshan_qizi
python scripts/check_lyrics.py --text "一年春尽一年春，\n花开花谢又逢春。" --preset tangshan_qizi
python scripts/check_lyrics.py --list              # 看有哪些规则
python scripts/check_lyrics.py --file x.txt --json # 机器可读
```

作为库：

```python
import sys; sys.path.insert(0, "scripts")
from check_lyrics import check

r = check(唱词, preset="tangshan_qizi")      # 或用 rules=自定义字典 / 规则文件路径
if not r["passed"]:
    for i in r["issues"]:
        print(i["location"]["phrase"], i["type"], i["message"], "→", i["suggestion"])
```

## 工作流程

1. **先问格律**：这份稿子按哪个流派、哪种句式？没有明确规则就用 `generic_couplet`（只查骨架，不查字数），并告诉用户这只是结构体检。
2. **跑校验**，拿到 `passed` / `score` / `issues`。
3. **转述要带位置**：直接用 `location.phrase`（如「第1段第2句第7字」），不要自己编号。
4. **给建议时区分可改与不可改**：`suggestion` 里给的是候选，不是命令。涉及艺术判断的（换韵、改字）要把决定权交回用户。
5. **报告规则的可信度**：`rule_used.confidence` 为 `inferred` 或 `custom` 时必须一并说明，别让用户以为是史料定论。

## 输出的读法

```json
{
  "passed": false,
  "score": 88,
  "summary": { "errors": 1, "warnings": 0, "stanzas": 1, "lines": 4,
               "chars": 29, "rhyme_schemes": {"1": "人辰"} },
  "issues": [{
    "code": "E_CHAR_COUNT", "severity": "error", "type": "句式字数",
    "location": { "stanza": 1, "line": 1, "char": 8, "offset": 7,
                  "text": "一年春尽一年春光", "phrase": "第1段第1句第8字" },
    "message": "本句 8 字，要求 7 字，超出 1 字",
    "suggestion": "可删去一个虚词（的/了/就/便/也），或在该句分句处断开"
  }]
}
```

- `passed` 只看 **error**，警告不影响通过
- `score = 100 − 12×errors − 3×warnings`（下限 0），只用于横向比较，不是评分标准
- `location.offset` 是**原文绝对字符偏移**，可直接喂给编辑器高亮
- `lines[]` 每句的韵脚字、所属辙、声调都在里面，适合做可视化

## 规则怎么挑

| 预设 | 用途 | 可信度 |
|---|---|---|
| `tangshan_qizi` | 唐山皮影·七字句 | inferred（据名称推定） |
| `tangshan_shizi` | 唐山皮影·十字锦 | inferred |
| `generic_couplet` | 只查上下句/押韵/重复，不限字数 | custom（安全默认） |
| `seven_char_pingze_demo` | 七字句 + 平仄定式**示例** | custom（不是史料） |

要新增流派：复制一份 `rules/*.json` 改字段，**必须在 `meta` 里写清 `source` 和 `confidence`**。字段说明见 `references/rules.md`。

## 两条硬边界

1. **平仄默认关闭**。因为公开资料里没有皮影各流派的平仄定式。要用，就在 `tone.patterns` 里显式给出，并在 `meta.warning` 里注明出处；否则本工具拒绝校验平仄（规则校验会直接报 `RULE_TONE_NO_PATTERN`）。
2. **押韵依赖韵表**。内置 6762 个 GB2312 汉字的「十三辙 + 普通话声调」表。表外字（生僻字、异体字、方言专用字）会报 `W_RHYME_UNKNOWN` 而不是猜——觉得判错了，用 `overrides` 指定读音：
   ```json
   { "overrides": { "年": "言前|2" } }
   ```

## 自检

```bash
python -m unittest discover -s tests -t .   # 50 个单元测试
python evals/run_evals.py                   # 24 条验收用例
python demo/run_demo.py                     # 7 个真实使用场景
```
