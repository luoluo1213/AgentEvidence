# Research Sources

| source_id | title | source_type | canonical_url | raw_file | processed_file | retrieved_at | version/commit | verified | notes |
|---|---|---|---|---|---|---|---|---|---|
| `research:react` | ReAct: Synergizing Reasoning and Acting in Language Models | paper | https://arxiv.org/abs/2210.03629 | `data/research_raw/react/raw.pdf` | `data/research_corpus/react/content.md` | 2026-10-01 | arXiv 2210.03629 | false | PDF text extracted mechanically with page markers. |
| `research:reflexion` | Reflexion: Language Agents with Verbal Reinforcement Learning | paper | https://arxiv.org/abs/2303.11366 | `data/research_raw/reflexion/raw.pdf` | `data/research_corpus/reflexion/content.md` | 2026-10-01 | arXiv 2303.11366 | false | PDF text extracted mechanically with page markers. |
| `research:mini_swe_agent` | mini-SWE-agent | repository | https://github.com/SWE-agent/mini-swe-agent | `data/research_raw/mini_swe_agent/raw_README.md`; pinned source under `data/research_raw/mini_swe_agent/repository/` | `data/research_corpus/mini_swe_agent/content.md` | 2026-10-01 | `main` / `04d809ceab9df28f9adaed044884180159172930` | false | README plus exact `agents/default.py` and its direct execution dependency `environments/local.py`. |

Default retrieval now uses the normalized layer:

- `data/research_normalized/react/document.md`
- `data/research_normalized/reflexion/document.md`
- `data/research_normalized/mini_swe_agent/document.md`

Each `source.json` records `normalized_file`, `normalization_method`, `normalized_from`, and whether references were excluded. The original raw and Step 4.5 processed artifacts remain unchanged.

The mini-SWE-agent repository evidence is pinned to commit `04d809ceab9df28f9adaed044884180159172930`. Only `src/minisweagent/agents/default.py` and `src/minisweagent/environments/local.py` were added; no repository-wide scan was performed. Both files share the existing `research:mini_swe_agent` source namespace.

## Manual Verification Checklist

For each source:

- [ ] title matches source
- [ ] canonical URL correct
- [ ] content derived from source
- [ ] no generated/fabricated paragraphs
- [ ] key method section preserved
- [ ] version/commit recorded where applicable
