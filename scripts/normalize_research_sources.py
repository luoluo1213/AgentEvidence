from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = PROJECT_ROOT / "data" / "research_corpus"
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "research_normalized"

PAPER_TITLES = {
    "react": "ReAct: Synergizing Reasoning and Acting in Language Models",
    "reflexion": "Reflexion: Language Agents with Verbal Reinforcement Learning",
}


def _paper_heading(source_id: str, line: str) -> str | None:
    value = line.strip()
    if value.lower() == "abstract":
        return "Abstract"
    if source_id == "react":
        headings = {
            "1 I NTRODUCTION": "1 Introduction",
            "2 REAC T: S YNERGIZING REASONING + AC TING": "2 ReAct: Synergizing Reasoning + Acting",
            "3 K NOWLEDGE -INTENSIVE REASONING TASKS": "3 Knowledge-Intensive Reasoning Tasks",
            "3.1 S ETUP": "3.1 Setup", "3.2 M ETHODS": "3.2 Methods",
            "3.3 R ESULTS AND OBSERVATIONS": "3.3 Results and Observations",
            "4 D ECISION MAKING TASKS": "4 Decision Making Tasks",
            "5 R ELATED WORK": "5 Related Work", "6 C ONCLUSION": "6 Conclusion",
            "A A DDITIONAL RESULTS": "A Additional Results",
            "A.1 GPT-3 E XPERIMENTS": "A.1 GPT-3 Experiments",
            "A.2 REAC TOBTAINS UP -TO-DATE KNOWLEDGE ON HOTPOT QA": "A.2 ReAct Obtains Up-to-Date Knowledge on HotpotQA",
            "A.3 H UMAN -IN-THE -LOOP BEHAVIOR CORRECTION ON ALFWORLD": "A.3 Human-in-the-Loop Behavior Correction on ALFWorld",
            "B E XPERIMENT DETAILS": "B Experiment Details",
            "B.1 H OTPOT QA F INETUNING DETAILS": "B.1 HotpotQA Finetuning Details",
            "B.2 A LFWORLD IM-S TYLE DETAILS": "B.2 ALFWorld IM-Style Details",
            "C P ROMPTS": "C Prompts", "D T RAJECTORIES": "D Trajectories",
            "E M ORE ANALYSIS": "E More Analysis",
            "E.1 S UCCESS AND FAILURE MODES ANALYSIS": "E.1 Success and Failure Modes Analysis",
        }
        if value in headings:
            return headings[value]
        match = re.match(r"^([A-E]\.\d+)\s+(.+)$", value)
        return f"{match.group(1)} {match.group(2)}" if match else None
    reflexion_headings = {
        "1 Introduction", "2 Related work", "3 Reflexion: reinforcement via verbal reflection",
        "4 Experiments", "4.1 Sequential decision making: ALFWorld", "4.2 Reasoning: HotpotQA",
        "4.3 Programming", "5 Limitations", "6 Broader impact", "7 Conclusion", "8 Reproducibility",
        "A Evaluation with additional models", "B Decision-making", "B.1 WebShop Limitation",
        "C Programming", "C.1 Programming function implementation example (HumanEval Python)",
        "C.2 Reflexion Actor instruction", "C.3 Reflexion Self-reflection instruction and example",
        "C.4 Reflexion programming no Self-Reflection ablation example",
        "C.5 Reflexion programming no test generation ablation example", "D Reasoning",
        "D.1 Full example", "D.2 Chain-of-Thought + Reflexion",
        "D.3 HotPotQA Chain-of-Thought (GT) + Reflexion",
        "D.4 HotPotQA episodic memory (EPM) ablation prompts",
    }
    if value in reflexion_headings:
        return value
    return None


def _is_noise(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    if re.fullmatch(r"\[Page \d+\]", value) or re.fullmatch(r"\d+", value):
        return True
    if value in {"Published as a conference paper at ICLR 2023", "Preprint. Under review."}:
        return True
    if value.startswith("arXiv:"):
        return True
    if "\x03" in value or "Ҽ" in value:
        return True
    if any(ord(character) < 32 for character in value):
        return True
    if any(character.isdigit() for character in value) and not any(character.islower() for character in value) and len(value) > 4:
        return True
    if len(value.split()) == 1 and len(value) > 5 and value.upper() == value:
        return True
    letters = sum(character.isalpha() for character in value)
    symbols = sum(not character.isalnum() and not character.isspace() for character in value)
    return len(value) > 25 and letters < 8 and symbols > len(value) * 0.25


def _join_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if _is_noise(line):
            continue
        if current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        else:
            current = f"{current} {line}".strip()
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs)


def normalize_paper(source_id: str, text: str) -> tuple[str, list[str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Front Matter"
    current_lines: list[str] = []
    skipping = False
    excluded_appendix_roots = {"react": {"C", "D"}, "reflexion": {"D"}}[source_id]

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper() == "REFERENCES":
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading, current_lines, skipping = "References", [], True
            continue
        heading = _paper_heading(source_id, stripped)
        if heading:
            root = heading.split()[0].split(".")[0]
            if skipping and root not in {"A", "B", "C", "D", "E"}:
                continue
            skipping = root in excluded_appendix_roots
            if current_lines and current_heading != "References":
                sections.append((current_heading, current_lines))
            current_heading, current_lines = heading, []
            continue
        if not skipping:
            current_lines.append(line)
    if current_lines and current_heading != "References":
        sections.append((current_heading, current_lines))

    rendered = [f"# {PAPER_TITLES[source_id]}"]
    names = []
    for heading, lines in sections:
        body = _join_lines(lines)
        if not body:
            continue
        names.append(heading)
        rendered.extend(["", f"## {heading}", "", body])
    return "\n".join(rendered).strip() + "\n", names


def normalize_readme(text: str) -> tuple[str, list[str]]:
    output: list[str] = []
    sections: list[str] = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("<table"):
            in_table = True
            continue
        if in_table:
            if line.startswith("</table"):
                in_table = False
            continue
        if line.startswith("## Let's get started!"):
            break
        summary = re.match(r"<summary>(.+?)</summary>", line)
        if summary:
            heading = summary.group(1)
            output.extend(["", f"## {heading}", ""])
            sections.append(heading)
            continue
        if line.startswith(("<div", "</div", "<details", "</details", "<a ", "</a")):
            continue
        if re.match(r"^\[!\[", line) or re.match(r"^!\[", line):
            continue
        if line.startswith("📣"):
            continue
        if "img.shields.io" in line:
            continue
        if line.startswith("> [!WARNING]") or line.startswith("> This is **mini-swe-agent v2**"):
            continue
        if line.startswith("# "):
            sections.append(line[2:].strip())
        output.append(raw.rstrip())
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip() + "\n"
    return cleaned, sections


def main() -> int:
    NORMALIZED_ROOT.mkdir(parents=True, exist_ok=True)
    for metadata_path in sorted(CORPUS_ROOT.glob("*/source.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_id = metadata["source_id"]
        processed_path = metadata_path.parent / metadata.get("processed_file", "content.md")
        original = processed_path.read_text(encoding="utf-8")
        if source_id in PAPER_TITLES:
            normalized, sections = normalize_paper(source_id, original)
            references_excluded = True
        elif source_id == "mini_swe_agent":
            normalized, sections = normalize_readme(original)
            references_excluded = False
        else:
            raise ValueError(f"No deterministic normalizer registered for {source_id}")
        destination = NORMALIZED_ROOT / source_id / "document.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(normalized, encoding="utf-8")
        metadata.update({
            "normalized_file": f"data/research_normalized/{source_id}/document.md",
            "normalization_method": "structure_preserving_cleanup",
            "normalized_from": f"data/research_corpus/{source_id}/{processed_path.name}",
            "references_excluded_from_retrieval": references_excluded,
            "verified": False,
        })
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"NORMALIZED {source_id}: {len(original)} -> {len(normalized)} chars; {len(sections)} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
