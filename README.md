# 皮影戏唱词格律校验器

> A rule-driven prosody checker for Chinese shadow-puppetry lyrics (皮影戏唱词):
> line length, couplet pairing, rhyme (十三辙), tone pattern, repetition and stanza structure.
> Engine and rules are separated — swap a JSON to switch genres, no code changes.

把「唱词合不合律」拆成两半：**引擎负责判，规则负责定义什么叫合律**。
规则可替换、可追溯出处、可标明可信度；引擎不臆造格律。

```bash
python scripts/check_lyrics.py --text "一年春尽一年春，\n花开花谢又逢春。" --preset tangshan_qizi
```

```
【通过 ✓】得分 100　规则：唐山皮影·七字句（可信度：inferred）
  共 1 段 / 2 句 / 14 字　错误 0，警告 0
  各段韵脚：第1段 人辰
```

出错时给到「第几段第几句第几字 + 什么毛病 + 怎么改」：

```
【未通过 ✗】得分 88　规则：唐山皮影·七字句
  ✗ [句式字数] 第1段第1句第8字：本句 8 字，要求 7 字，超出 1 字
      建议：可删去一个虚词（的/了/就/便/也），或在该句分句处断开
```

---

## 目录

```
piying-libretto/
├─ SKILL.md                  # 作为 Agent Skill 的入口说明
├─ README.md
├─ LICENSE                   # MIT（含 pypinyin 第三方声明）
├─ scripts/
│  ├─ check_lyrics.py        # 校验引擎（库 + CLI，单文件，无第三方依赖）
│  └─ build_rhyme_table.py   # 重建韵表（一次性，需 pypinyin）
├─ data/
│  └─ rhyme_table.json       # 6762 字 → 十三辙 + 普通话声调
├─ rules/
│  ├─ tangshan_qizi.json     # 唐山皮影·七字句
│  ├─ tangshan_shizi.json    # 唐山皮影·十字锦
│  ├─ generic_couplet.json   # 通用上下句（不限字数）
│  └─ seven_char_pingze_demo.json  # 平仄校验示例（非史料）
├─ references/
│  ├─ rules.md               # 规则字段详解
│  └─ rhyme_schemes.md       # 十三辙对照与扩展方法
├─ demo/
│  └─ run_demo.py            # 7 个真实使用场景
├─ tests/
│  ├─ __init__.py
│  └─ test_check_lyrics.py   # 50 个单元测试
├─ evals/
│  ├─ cases.json             # 24 条验收用例
│  └─ run_evals.py
└─ .github/workflows/test.yml  # CI：Python 3.9–3.12 × 单测 + 验收 + 演示
```

## 安装

```bash
# 运行时零依赖，Python 3.9+ 即可
python scripts/check_lyrics.py --list

# 只有重建韵表才需要
pip install pypinyin
python scripts/build_rhyme_table.py
```

## 用法

### 命令行

```bash
python scripts/check_lyrics.py --file 唱词.txt --preset tangshan_qizi
python scripts/check_lyrics.py --text "……" --rules rules/tangshan_qizi.json
python scripts/check_lyrics.py --file 唱词.txt --json        # 结构化输出
python scripts/check_lyrics.py --list                        # 列出预设
cat 唱词.txt | python scripts/check_lyrics.py --preset generic_couplet
```

退出码：通过 `0`，不通过 `1`，参数错误 `2`。适合接 CI。

### 作为库

```python
import sys; sys.path.insert(0, "scripts")
from check_lyrics import check, resolve_char, available_presets

r = check(唱词, preset="tangshan_qizi")   # 或 rules=字典 / 规则文件路径
r["passed"]        # bool
r["score"]         # int
r["issues"]        # [{code, severity, type, location, message, detail, suggestion}]
r["lines"]         # 每句的字数、韵脚字、所属辙、声调
r["rule_used"]     # 用了哪份规则、可信度、注意事项
```

### 文本格式约定

- **换行 = 分句**（一句一行）
- **空行 = 分段**
- 行内标点（`，、；：。！？`）用于切分句（分句）
- 中文字符才计入字数；英文、数字、标点、空白都不计

```
一年春尽一年春，
花开花谢又逢春。

光阴似箭催人老，
日月如梭不待人。
```

### 场景演示

7 个真实使用场景，全部是实际运行结果，可直接用于汇报或新人上手：

```bash
python demo/run_demo.py        # 全部
python demo/run_demo.py 3      # 只看第 3 个场景
```

| # | 场景 | 谁在用 |
|---|---|---|
| 1 | 现场质检：AI 写的唱词能不能唱 | 编辑 |
| 2 | 给同辙替代字，不只说"错了" | 编剧 |
| 3 | 改稿闭环：判错→建议→复审→放行 | 编辑 |
| 4 | 批量体检：整本稿子出分类型统计 | 主编 |
| 5 | 换规则不换代码：同一段词两套标准 | 研究者 |
| 6 | 多音字/方言判错了用 overrides 修正 | 领域专家 |
| 7 | 接进 AI 生成流程，把校验当闸门 | AI 岗 |

## 检查项

| 类型 | 依据 | 默认 |
|---|---|---|
| 句式字数（整句 / 分句） | 规则 `line_chars` / `clause_chars` | 开 |
| 上下句配对（偶数句） | 规则 `couplet_required` | 开 |
| 押韵（段内同辙 / 段间是否换辙） | 韵表 + 规则 `rhyme` | 开 |
| 韵脚同字相押 | 规则 `ban_same_char` | 开 |
| 平仄 | **规则必须显式给出定式** | **关** |
| 整句 / 分句重复 | 规则 `repeat` | 开 |
| 段落句数上下限 | 规则 `min/max_lines_per_stanza` | 开 |
| 句末标点 | 规则 `punctuation` | 视预设 |
| 超长单行（疑似漏换行） | 规则 `max_chars_per_line` | 开 |

## 问题码

| 码 | 级别 | 含义 |
|---|---|---|
| `E_CHAR_COUNT` | error | 整句字数不符 |
| `E_CLAUSE_CHARS` | error | 分句字数不符（逗位错） |
| `E_COUPLET_ODD` | error | 段内句数为奇数，上下句不成对 |
| `E_RHYME_MISMATCH` | error | 句尾辙口与本段韵脚不同 |
| `E_RHYME_SCHEME_CHANGE` | error | 段间换了辙，而规则不允许 |
| `E_STANZA_TOO_SHORT` / `E_STANZA_TOO_LONG` | error | 段落句数越界 |
| `TONE_MISMATCH` | error/warn | 平仄与定式不符（级别由 `tone.strictness` 决定） |
| `W_RHYME_SAME_CHAR` | warning | 连续押同一个字 |
| `W_RHYME_UNKNOWN` | warning | 该字不在韵表中，不猜 |
| `W_TONE_UNKNOWN` | warning | 轻声字，平仄无法判定 |
| `W_REPEAT_LINE` / `W_REPEAT_CLAUSE` | warning | 整句 / 分句重复 |
| `W_NO_END_PUNCT` | warning | 句末缺标点 |
| `W_LONG_LINE` | warning | 单行过长，疑似漏分行 |
| `E_EMPTY_INPUT` | error | 空输入或全空白 |
| `E_NO_CJK` | error | 没有中文字符 |
| `E_RULE_NOT_FOUND` | error | 预设/规则文件不存在或类型不对 |
| `RULE_CHAR_RANGE` / `RULE_BAD_VALUE` | error | 规则自相矛盾 |
| `RULE_TONE_NO_PATTERN` / `RULE_TONE_BAD_PATTERN` | error | 开了平仄却没给定式 |

完整定义见 `references/rules.md`。

## 边界与已知限制

1. **平仄默认关闭。** 公开资料里没有皮影各流派的平仄定式，本工具不猜。要用必须在 `tone.patterns` 里写明；只给 `enabled:true` 会被规则校验判为非法。
2. **押韵按普通话 + 十三辙判。** 方言押韵（如用唐山话、关中话）与普通话可能不同，需用 `overrides` 逐字指定，或替换韵表。
3. **不含入声。** 古韵入声字在现代普通话里可能派入阴平/阳平，会被判成「平」。需要古韵请用 `overrides` 标成 `仄`。
4. **多音字取常用读音。** 唱词里的特殊读法要用 `overrides` 覆盖，否则可能误判韵部。
5. **不做板式/腔格校验。** 这需要曲谱和旋律，不在文本层面可判。
6. **`score` 只是相对指标**，不是行业评分标准。
7. **韵表覆盖 GB2312 一二级汉字（6762 字）**，生僻字、异体字、繁体字可能落在表外，会报 `W_RHYME_UNKNOWN` 而不是瞎猜。

## 自检

```bash
python -m unittest discover -s tests -t .    # 50 个单元测试
python evals/run_evals.py                    # 24 条验收用例，打印成绩单
python evals/run_evals.py --json             # 机器可读
```

当前状态：单元测试 **50/50**，验收用例 **24/24**。
CI 在 Python 3.9 / 3.10 / 3.11 / 3.12 上跑同一套检查（`.github/workflows/test.yml`）。

## 扩展

**加一个流派的规则**：复制 `rules/generic_couplet.json`，改 `line_chars` 等字段，**务必填写**：

```json
"meta": {
  "name": "某流派·某句式",
  "source": "出自哪份文献/哪位传承人口述/哪次田野记录",
  "confidence": "documented | inferred | custom",
  "warning": "这套规则覆盖什么、不覆盖什么"
}
```

**修韵表**：把 `overrides` 写在规则里，不要改 `data/rhyme_table.json`（它是自动生成的）。若确实要扩充基础表，改 `scripts/build_rhyme_table.py` 的 `FINAL_TO_SCHEME` 后重跑。

## 许可

代码 MIT。`data/rhyme_table.json` 由 [pypinyin](https://github.com/mozillazg/python-pinyin)（MIT）生成，辙名采用十三辙通行分法。
