from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class RepositoryCodeChunk:
    content: str
    file_path: str
    symbol: str
    content_type: str
    commit: str
    repository_url: str
    structural_tokens: str = ""
    source_title: str = ""

    @property
    def metadata(self) -> dict[str, str]:
        symbol_tokens = self.symbol.replace(".", " ").replace("_", " ")
        identifier_tokens = f"{symbol_tokens} {self.structural_tokens}".lower().split()
        return {
            "chunk_id": _logical_chunk_id(self.commit, self.file_path, self.symbol, self.content),
            "file_path": self.file_path,
            "symbol": self.symbol,
            "qualified_symbol": self.symbol,
            "content_type": self.content_type,
            "language": "python",
            "source_type": "repository",
            "commit": self.commit,
            "repository_url": self.repository_url,
            "source_title": self.source_title,
            "symbol_tokens": symbol_tokens,
            "structural_tokens": self.structural_tokens,
            "identifier_aliases_zh": _identifier_aliases_zh(identifier_tokens),
        }


def _logical_chunk_id(commit: str, file_path: str, symbol: str, content: str) -> str:
    digest = hashlib.sha256(f"{commit}\0{file_path}\0{symbol}\0{content}".encode("utf-8")).hexdigest()[:20]
    return f"repo:{digest}"


def code_aware_chunks(
    content: str,
    *,
    file_path: str,
    commit: str,
    repository_url: str,
    source_title: str = "",
) -> list[RepositoryCodeChunk]:
    """Return exact source slices at module, class-header, function, and method boundaries."""
    tree = ast.parse(content, filename=file_path)
    lines = content.splitlines(keepends=True)
    chunks: list[RepositoryCodeChunk] = []

    first_definition = min((node.lineno for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))), default=len(lines) + 1)
    preamble = "".join(lines[: first_definition - 1]).strip()
    if preamble:
        chunks.append(_chunk(preamble, file_path, "<module>", commit, repository_url, source_title=source_title))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            header_end = min((item.lineno for item in methods), default=(node.end_lineno or node.lineno) + 1) - 1
            header = "".join(lines[node.lineno - 1:header_end]).strip()
            if header and header != f"class {node.name}:":
                chunks.append(_chunk(header, file_path, node.name, commit, repository_url, source_title=source_title))
            for method in methods:
                start = min([method.lineno, *[decorator.lineno for decorator in method.decorator_list]])
                source = "".join(lines[start - 1:method.end_lineno]).strip()
                chunks.append(_chunk(source, file_path, f"{node.name}.{method.name}", commit, repository_url, method, source_title))
                for index, loop in enumerate(
                    (child for child in ast.walk(method) if isinstance(child, (ast.While, ast.For, ast.AsyncFor))),
                    start=1,
                ):
                    loop_source = "".join(lines[loop.lineno - 1:loop.end_lineno]).rstrip()
                    loop_kind = "while_loop" if isinstance(loop, ast.While) else "for_loop"
                    chunks.append(_chunk(
                        loop_source,
                        file_path,
                        f"{node.name}.{method.name}.{loop_kind}_{index}",
                        commit,
                        repository_url,
                        loop,
                        source_title,
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno, *[decorator.lineno for decorator in node.decorator_list]])
            source = "".join(lines[start - 1:node.end_lineno]).strip()
            chunks.append(_chunk(source, file_path, node.name, commit, repository_url, node, source_title))
    return chunks


def load_repository_chunks(project_root: Path, source) -> list[RepositoryCodeChunk]:
    chunks: list[RepositoryCodeChunk] = []
    for record in source.repository_files:
        raw_path = project_root / record.raw_file
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing pinned repository source: {raw_path}")
        chunks.extend(code_aware_chunks(
            raw_path.read_text(encoding="utf-8"),
            file_path=record.file_path,
            commit=record.commit,
            repository_url=str(record.repository_url),
            source_title=source.title,
        ))
    return chunks


def _chunk(
    content: str,
    file_path: str,
    symbol: str,
    commit: str,
    repository_url: str,
    node: ast.AST | None = None,
    source_title: str = "",
) -> RepositoryCodeChunk:
    return RepositoryCodeChunk(
        content,
        file_path,
        symbol,
        "source_code",
        commit,
        repository_url,
        _structural_tokens(node),
        source_title,
    )


def _structural_tokens(node: ast.AST | None) -> str:
    """Expose only mechanically derived identifiers and syntax names for retrieval."""
    if node is None:
        return ""
    tokens: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            tokens.add(child.id)
        elif isinstance(child, ast.Attribute):
            tokens.add(child.attr)
        elif isinstance(child, ast.While):
            tokens.update(("while", "loop", "while_loop"))
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            tokens.update(("for", "loop", "for_loop"))
    expanded = set(tokens)
    for token in tokens:
        expanded.update(part for part in token.replace(".", "_").split("_") if part)
        if token.endswith("s") and len(token) > 3:
            expanded.add(token[:-1])
    return " ".join(sorted(expanded))


def _identifier_aliases_zh(tokens: list[str]) -> str:
    """Map identifier tokens through a fixed glossary; canonical code stays untouched."""
    glossary = {
        "run": "执行",
        "execute": "执行",
        "result": "结果",
        "output": "输出",
        "add": "加入",
        "append": "追加",
        "message": "消息",
        "messages": "消息",
        "history": "历史",
        "loop": "循环",
        "step": "步骤",
        "action": "动作",
        "actions": "动作",
        "query": "查询",
    }
    return " ".join(sorted({glossary[token] for token in tokens if token in glossary}))
