# 规则字段详解

一份规则就是一个 JSON。里面所有字段都可以省略，省略的会落回默认值（`scripts/check_lyrics.py` 的 `DEFAULT_RULES`）。

```json
{
  "meta":      { "name": "", "description": "", "source": "", "confidence": "custom", "warning": "" },
  "structure": { "line_chars": {...}, "clause_chars": null, "couplet_required": true, ... },
  "rhyme":     { "enabled": true, "on": "lower", ... },
  "tone":      { "enabled": false, "patterns": null, ... },
  "repeat":    { "max_identical_lines": 1, ... },
  "punctuation": { "require_end": false, ... },
  "overrides": {}
}
```

---

## meta

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 规则名，会出现在报告里 |
| `description` | str | 一句话说明这套规则管什么 |
| `source` | str | **出处**。文献名/项目页/口述人/田野记录时间 |
| `confidence` | `documented` \| `inferred` \| `custom` | 见下 |
| `warning` | str | 报告开头会原样打印。**写清这套规则不覆盖什么** |

`confidence` 三档的含义，务必如实填写：

- **documented** —— 有明确文献依据，能指到具体出处
- **inferred** —— 据名称或间接材料推定（例如"七字句"推定为每句七字）
- **custom** —— 自定义/示例，不对应任何史料

> 这一栏是给用户看的，也是给未来的自己看的。填高了会在答辩或评审时被问穿。

---

## structure

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `line_chars` | `{"min": int\|null, "max": int\|null}` | 都不限 | 整句字数区间。`min==max` 时为定长 |
| `clause_chars` | `[int, ...]` \| `null` | null | 按分句指定字数，如 `[3,4]` 表示"三字逗+四字句" |
| `couplet_required` | bool | true | 段内句数须为偶数（上下句成对） |
| `min_lines_per_stanza` | int | 2 | 每段最少句数 |
| `max_lines_per_stanza` | int \| null | null | 每段最多句数 |
| `max_chars_per_line` | int | 200 | 超过则报 `W_LONG_LINE`（疑似漏换行） |

**`line_chars` 与 `clause_chars` 的关系**：两者独立检查。同时给了，就是"整句要 7 字，且分句要 3+4"。

**`couplet_required` 与 `min_lines_per_stanza` 也独立**。设 `couplet_required:false` 不会自动把最少句数降到 1，要自己改。

---

## rhyme

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | true | 关掉则完全不查押韵 |
| `on` | `upper`\|`lower`\|`both`\|`every` | `lower` | 哪些位置押韵 |
| `strict` | bool | true | 段内各韵脚是否必须同辙 |
| `change_allowed_per_stanza` | bool | true | 允许段与段之间换辙 |
| `ban_same_char` | bool | true | 禁止连续两句用同一个韵脚字 |
| `unknown` | `warn`\|`error`\|`ignore` | `warn` | 韵表里没有的字怎么处理 |

**`on` 的含义**（段内句序号从 1 开始）：

- `upper` —— 第 1、3、5…句押韵
- `lower` —— 第 2、4、6…句押韵（**上下句体例的常规做法**）
- `every` —— 每句都押
- `both` —— 与 `every` 等价，保留作别名

> 注意：只有两句话时，`on:"lower"` 只产生**一个**韵脚点，段内无法判出"不一致"。真正的换辙问题要靠 `change_allowed_per_stanza` 在**段间**发现。这是设计上的必然，不是漏检。

---

## tone

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | **false** | 开启前必须给定式 |
| `pattern` | str \| null | null | 统一的平仄序列，如 `"平平仄仄平平仄"` |
| `patterns` | `{"upper":..., "lower":...}` \| null | null | 按上下句分别定式，**优先于 `pattern`** |
| `strictness` | `warn` \| `error` | `warn` | 不符时算警告还是错误 |
| `free_rhyme_position` | bool | true | 韵脚那一字不校验平仄（唱腔上通常放宽） |

序列只能用 `平` / `仄` / `中` 三个字符。`中` = 可平可仄，不校验。

`patterns.upper` 用于段内第 1、3、5…句，`lower` 用于第 2、4、6…句。
某一句缺对应定式时，回落到 `pattern`；两个都没有就跳过该句。

**平仄怎么算**：普通话第 1、2 声为平，第 3、4 声为仄；轻声（第 5 声）记 0，无法判定，报 `W_TONE_UNKNOWN`。

---

## repeat

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `max_identical_lines` | int | 1 | 同一句最多出现几次。`1` = 不许重复 |
| `max_identical_clauses` | int | 2 | 同一分句最多出现几次 |
| `max_same_rhyme_char_consecutive` | int | 1 | 连续几个韵脚可以用同一个字 |

要写**叠句**（有意重复），把 `max_identical_lines` 调到 2 或更高。

---

## punctuation

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `require_end` | bool | false | 是否要求句末有标点 |
| `allowed_end` | str | `，。；！？,.;!?` | 允许的句末字符集合 |

---

## overrides

逐字覆盖读音，格式 `"辙名|声调"`，也接受 `"声调"`、`"平"`、`"仄"`、`"辙名"` 单独使用。

```json
"overrides": {
  "年": "言前|2",     // 指定辙和调
  "得": "仄",         // 只强制平仄（入声作仄）
  "长": "江阳|2"      // 多音字取唱词里的实际读法
}
```

**什么时候必须用**：

- 多音字在唱词里读的不是常用音
- 方言押韵与普通话不同
- 古入声字要按仄处理
- 韵表里没有的字

---

## 一个完整例子

```json
{
  "meta": {
    "name": "唐山皮影·七字句",
    "source": "格律名称见河北省文化和旅游厅「唐山皮影戏」项目页",
    "confidence": "inferred",
    "warning": "平仄定式未开启；板式与腔格细则未收录"
  },
  "structure": {
    "line_chars": { "min": 7, "max": 7 },
    "couplet_required": true,
    "min_lines_per_stanza": 2,
    "max_lines_per_stanza": 16,
    "max_chars_per_line": 40
  },
  "rhyme": {
    "enabled": true,
    "on": "lower",
    "strict": true,
    "change_allowed_per_stanza": true,
    "ban_same_char": true
  },
  "tone": { "enabled": false },
  "repeat": { "max_identical_lines": 1 },
  "punctuation": { "require_end": true },
  "overrides": {}
}
```
