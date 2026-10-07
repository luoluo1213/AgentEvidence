# AgentEvidence 100-case E2E Formal Evaluation Set

本文件是 `research-e2e-baseline.json` 的静态扩展数据集；原有 20 条 case 原样保留在前 20 项，本次新增 80 条。未包含任何运行指标。

## 数据分布

| Category | Cases |
|---|---:|
| `single_document` | 45 |
| `cross_document` | 25 |
| `insufficient` | 10 |
| `same_session` | 10 |
| `cross_session` | 10 |
| **Total** | **100** |

## Corpus sources

- `research:attention_pdf`
- `research:react_pdf`
- `research:reflexion_pdf`
- `research:geoseacher_pdf`
- `research:geovis_pdf`
- `research:rsgroundr1_pdf`

## Single-document coverage

| Source | Cases |
|---|---:|
| `research:attention_pdf` | 7 |
| `research:react_pdf` | 7 |
| `research:reflexion_pdf` | 7 |
| `research:geoseacher_pdf` | 8 |
| `research:geovis_pdf` | 8 |
| `research:rsgroundr1_pdf` | 8 |

## Cross-document combinations

- `research:attention_pdf vs research:react_pdf`: 2
- `research:geoseacher_pdf vs research:geovis_pdf`: 6
- `research:geoseacher_pdf vs research:rsgroundr1_pdf`: 5
- `research:geovis_pdf vs research:rsgroundr1_pdf`: 5
- `research:react_pdf vs research:reflexion_pdf`: 7

## 设计原则

- 问题以中文为主，覆盖直接事实、核心机制、方法流程、模块作用、实验设置和论文明确讨论的问题。
- `expected_concepts` 保持为 2–5 个可核验语义点，不要求回答使用完全相同措辞。
- `answerable=true` 表示当前六篇论文语料中存在直接支持；`answerable=false` 表示语料不足，预期系统保守拒答。
- Cross-document case 只比较具有共同维度的方法，并列出全部目标 source；新增比较 case 设置 `requires_multiple_sources=true`。
- Same-session 与 Cross-session case 使用代词、省略或“继续之前研究”等表达；脱离 `prior_turns` 后具有明显歧义。
- 新增 case 标记 `difficulty` 为 `easy`、`medium` 或 `hard`；原 20 条不增删字段，以保持逐对象原样。

## 静态校验

- JSON 可解析；case 数为 100；ID 全局唯一。
- Category 数量符合 45/25/10/10/10。
- 原 20 条与 baseline 源文件逐对象相等。
- Source ID 均属于允许的六篇论文；required fields 完整。

本说明不包含任何尚未运行得到的 benchmark 指标。
