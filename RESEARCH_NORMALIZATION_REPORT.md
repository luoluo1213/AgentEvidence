# Research Corpus Normalization Report

Generated: 2026-10-01

## Summary

| source | raw length | Step 4.5 processed length | normalized length | sections detected | references removed | appendix handling |
|---|---:|---:|---:|---:|---|---|
| `research:react` | 633,805 PDF bytes | 110,479 characters | 48,089 characters | 17 | yes | Kept additional results, experiment details, and failure-mode analysis; excluded prompt and repetitive trajectory appendices. |
| `research:reflexion` | 591,097 PDF bytes | 59,630 characters | 41,295 characters | 22 | yes | Kept additional-model evaluation, decision-making details, programming instructions, and ablations; excluded repetitive reasoning trajectories. |
| `research:mini_swe_agent` | 11,106 README bytes | 11,078 characters | 5,208 characters | 4 | n/a | README only; no repository source expansion. |

Byte lengths of the saved normalized UTF-8 files are 48,578, 41,584, and 5,300 respectively.

## Removed Noise Types

- PDF page markers, standalone page numbers, repeated conference/preprint headers, arXiv footer lines, control-character fragments, and clearly corrupted figure-extraction tokens.
- References sections from both papers.
- ReAct prompt/trajectory appendices and Reflexion repetitive reasoning trajectories, while retaining method and ablation appendices.
- README badges, announcement links, decorative HTML/images/tables, installation commands, navigation lists, and attribution/project-logo material.

No source sentence was factually rewritten and no model-authored method summary was inserted. Heading normalization is limited to restoring source section labels and fixing extraction spacing.

## Provenance

Each normalized document resolves through `source.json` as:

`data/research_normalized/<source>/document.md` → `data/research_corpus/<source>/content.md` → `data/research_raw/<source>/...` → canonical URL.

All sources remain `verified: false`. Raw files were not modified.

## Chunk Rebuild

| source | old fixed-window chunks | normalized section-aware chunks |
|---|---:|---:|
| `research:react` | 247 | 124 |
| `research:reflexion` | 133 | 103 |
| `research:mini_swe_agent` | 25 | 13 |
| **Total** | **405** | **240** |

Every normalized chunk begins with its real section heading. Chunk creation never combines content from different sections. Search results and `EvidenceItem.section` expose this heading. Research-only context expansion is also constrained to the selected section.

## Retrieval Before / After

### ReAct query

`ReAct 是如何利用环境 observation 调整后续 reasoning 和 action 的？`

- Before top sections: unavailable (`None`) for all eight results because fixed-window chunks carried no section metadata. Top score: 0.6703; all sources were ReAct, but results included raw extraction fragments.
- After top sections: `3.3 Results and Observations`, `2 ReAct: Synergizing Reasoning + Acting`, `E.1 Success and Failure Modes Analysis`, `2 ReAct: Synergizing Reasoning + Acting`, `2 ReAct: Synergizing Reasoning + Acting`, `E.1 Success and Failure Modes Analysis`, `3.2 Methods`, and Reflexion section `3 Reflexion: reinforcement via verbal reflection`. Top score: 0.6672.
- Assessment: chunk relevance improved materially: method/thought-action-observation sections are now explicit, with no page markers or references.

### Reflexion query

`Reflexion 如何利用执行反馈进行 self-reflection 并影响后续 trial？`

- Before top sections: unavailable (`None`) for all eight results. Top score: 0.6585.
- After top sections: `4.1 Sequential decision making: ALFWorld`, four results from `3 Reflexion: reinforcement via verbal reflection`, `C.4 ... no Self-Reflection ablation`, `C.3 ... Self-reflection instruction`, and `4.2 Reasoning: HotpotQA`. Top score: 0.6549.
- Assessment: method, memory/subsequent-trial, feedback, and self-reflection evidence is concentrated in the top results; one relevant ablation/example remains high-ranked.

### mini-SWE-agent query

`mini-SWE-agent 的核心 Agent loop 是什么？`

- Before top sections: unavailable (`None`) for all eight results. Top score: 0.7058; top chunks contained HTML, image/navigation, and installation fragments.
- After top sections: the project title section, `More motivation (for research)`, `More motivation (as a tool)`, and `Should I use SWE-agent or mini-SWE-agent?`. Top score: approximately 0.70.
- Assessment: badges, images, decorative table, navigation and installation-only chunks were removed. Agent class, bash-only actions, linear history, and `subprocess.run` text remains. Ranking improvement is structural/noise-oriented rather than a higher score.

### Comparison query

`比较 ReAct 和 Reflexion 如何利用执行反馈`

The merged pool contains 12 evidence items and retains both `research:react` and `research:reflexion`, with section metadata populated.

## Warnings

- PDF extraction is imperfect; readable captions are retained, while clearly corrupted fragments are removed mechanically.
- The current environment has no running MySQL and no available Chroma backend. Rebuild and retrieval validation used SQLite plus the existing BM25/reranker path; no production MySQL/Chroma indexing is claimed.
- mini-SWE-agent README normalization remains unchanged; Step 4.5.2 now augments it with pinned repository code as described below.

## Bilingual Evidence Layer

### Status

- Total logical chunks: 240
- Chinese translations available: 229
- Stable success entries reusable from cache: 229
- Failed after three preparation passes: 11
- Canonical language: English
- Auxiliary retrieval/display language: Chinese
- Translation provider: `openai`
- Translation model: `deepseek-v4-pro`
- Translation method: `ai_client_faithful_technical_translation`
- Translation verified: `false`
- Duplicate Evidence introduced: NO (0 in comparison validation)

Every cache entry binds one Chinese translation to the same logical chunk using `source_id + source_index + SHA256(content_en)`. English normalized text remains unchanged in `content_en` and in the backward-compatible `content` field. Chinese text is used only for research BM25 candidate text and display. Failed translations retain English evidence and explicit `failed` provenance.

Cache files are stored under `data/research_translations/<source>/chunks.json` and are replaced atomically. Unchanged successful entries are not sent to the provider again.

### Retrieval Before / After Bilingual

#### Query A

`ReAct 如何利用环境观察调整后续推理和行动？`

- Before bilingual top sources: Reflexion, Reflexion, Reflexion, ReAct, ReAct, ReAct, ReAct, ReAct.
- Before top sections: `B.1 WebShop Limitation`, two `4.1 Sequential decision making: ALFWorld` chunks, followed by ReAct results/observations and methods.
- After bilingual top sources: ReAct, Reflexion, ReAct, ReAct, ReAct, ReAct, ReAct, ReAct.
- After top sections: `1 Introduction`, Reflexion method, two `3.3 Results and Observations`, two `2 ReAct: Synergizing Reasoning + Acting`, then two ReAct introduction chunks.
- Result: ReAct improved from 5/8 to 7/8 raw results and its direct method section moved into the leading group.

#### Query B

`Reflexion 如何利用执行反馈进行自我反思，并影响后续尝试？`

- Before bilingual: all eight sources were Reflexion; leading sections were `4.2 Reasoning: HotpotQA` and appendix instruction/example sections. The core method section appeared eighth.
- After bilingual: all eight sources remained Reflexion; sections were `Abstract`, `4.1 Sequential decision making: ALFWorld`, four results from `3 Reflexion: reinforcement via verbal reflection`, `Abstract`, and `C.3 ... Self-reflection instruction`.
- Result: the core feedback/reflection/memory/subsequent-trial method section moved from eighth to the leading group without changing ranking weights.

#### Query C

`比较 ReAct 和 Reflexion 如何利用执行反馈`

- Before and after final EvidencePool both retained `research:react` and `research:reflexion`.
- After bilingual the first decomposed query returned both sources in its first four results; the Reflexion-specific query returned Reflexion method evidence.
- Final evidence count: 12.
- Duplicate logical chunk count: 0.
- A broad source-neutral Chinese comparison subquery also retrieved unrelated research chunks; no ranking adjustment was made in this phase.

#### English Regression

`How does ReAct use observations to guide subsequent reasoning and actions?`

After bilingual retrieval, all top eight results were `research:react`. English behavior did not regress.

#### mini-SWE-agent Chinese Query

`mini-SWE-agent 的线性 history 和 action 执行机制是什么？`

Seven of the top eight results were `research:mini_swe_agent`; the top sections were `More motivation (as a tool)`, `More motivation (for research)`, and project comparison/design sections containing linear history, bash-only actions, and `subprocess.run`.

## Step 4.5.2 Repository Code Evidence

- Pinned commit: `04d809ceab9df28f9adaed044884180159172930`
- Raw files: `src/minisweagent/agents/default.py` and the directly required `src/minisweagent/environments/local.py`
- Code chunking: exact AST-aligned module/class/method/function slices plus the exact `DefaultAgent.run` while-loop block
- Code chunks: 22 (14 from `default.py`, 8 from `local.py`)
- README chunks retained: 13
- Total `research:mini_swe_agent` chunks: 35
- Canonical code language: Python source exactly as pinned
- Chinese source-code translations: 0; source-code results use `translation_status=skipped_source_code`
- Retrieval metadata: commit, repository URL, file path, symbol, content type, mechanically extracted identifiers/control-flow tokens, and fixed identifier aliases for bilingual recall
- Namespace: README and code both remain under `research:mini_swe_agent`
- Duplicate logical evidence in acceptance demos: 0

Acceptance query `mini-SWE-agent 的核心 Agent loop 是如何执行的？` retrieves `src/minisweagent/agents/default.py` / `DefaultAgent.run.while_loop_1` in the top eight, together with `DefaultAgent.step`. Acceptance query `mini-SWE-agent 如何执行 action，并把执行结果加入 history？` ranks `DefaultAgent.execute_actions` first, `LocalEnvironment.execute` second, and also returns `DefaultAgent.run`, `DefaultAgent.step`, and `DefaultAgent.add_messages`.

README/source discrepancy preserved: the pinned README describes action execution as `subprocess.run`, while pinned `LocalEnvironment._run` uses `subprocess.Popen(...).communicate(...)` and returns `subprocess.CompletedProcess`. Neither source was rewritten to reconcile the difference.

No BM25 formula, fusion weight, candidate count, `top_k`, psychology corpus, chat/coordinator/runtime behavior, or agent orchestration policy was changed. Existing reranking now consumes the same bilingual/provenance retrieval text as BM25; the reranking formula and weights are unchanged.
