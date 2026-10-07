from __future__ import annotations

import re


def markdown_section(content: str) -> str | None:
    match = re.match(r"^#{1,6}\s+(.+?)\s*(?:\n|$)", content.strip())
    return match.group(1).strip() if match else None
