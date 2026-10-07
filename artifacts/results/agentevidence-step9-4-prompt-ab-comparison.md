# Step 9.4 — Grounded Draft Prompt Calibration A/B

- Decision: **REVERT TO A**
- Target recovery: **0/6**
- Dataset unchanged: **True**
- Invalid evidence-ID cases under B: **0**
- Existing grounded-case regressions: **0**

## Prompt change

A: `Address every research question explicitly. Explain mechanisms, processes, relationships, differences, and implementation details whenever the supplied evidence supports them.`

B: `Work through the research questions one by one. Answer every question or sub-point that the supplied evidence supports; for any unsupported part, state specifically that the supplied evidence is insufficient and omit factual claims about it. Do not abstain from the entire draft merely because some parts are unsupported.`

## Target cases

| Case | A claims | B claims | IDs valid | Verifier sufficient | Answer changed | Recovered |
|---|---:|---:|---|---|---|---|
| session-react-observation | 0 | 0 | True | False | False | False |
| session-reflexion-memory | 0 | 0 | True | False | False | False |
| single-react-feedback | 0 | 0 | True | False | False | False |
| single-react-mechanism | 0 | 0 | True | False | False | False |
| single-reflexion-components | 0 | 0 | True | False | False | False |
| single-reflexion-mechanism | 0 | 0 | True | False | False | False |

## Result

The same deterministic benchmark provider does not branch on the Draft system prompt, so B produced the same outputs as A. Keeping B would fail the predeclared recovery threshold.
The two insufficient-evidence cases remained conservative and all measured metrics were unchanged.
