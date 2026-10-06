"""Health checks. Each check takes a Vault and yields Issues."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterator, List, Optional

from .vault import Vault


@dataclass
class Issue:
    check: str
    path: str
    line: Optional[int]
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def check_broken_links(vault: Vault) -> Iterator[Issue]:
    for note in vault.notes:
        for link in note.links:
            if not vault.resolves(link.target):
                yield Issue("broken-link", note.path, link.line, f"找不到目标：{link.raw}")


def check_no_frontmatter(vault: Vault) -> Iterator[Issue]:
    for note in vault.notes:
        if note.frontmatter is None:
            yield Issue("no-frontmatter", note.path, None, "没有 frontmatter（--- 包住的元数据块）")


def check_empty_note(vault: Vault) -> Iterator[Issue]:
    for note in vault.notes:
        if not note.body.strip():
            yield Issue("empty-note", note.path, None, "正文为空")


def check_bom(vault: Vault) -> Iterator[Issue]:
    for note in vault.notes:
        if note.has_bom:
            yield Issue("bom", note.path, 1, "文件以 UTF-8 BOM 开头，部分工具会读不到 frontmatter")


# Order here is the order of the report.
CHECKS: Dict[str, Callable[[Vault], Iterator[Issue]]] = {
    "broken-link": check_broken_links,
    "no-frontmatter": check_no_frontmatter,
    "empty-note": check_empty_note,
    "bom": check_bom,
}

TITLES = {
    "broken-link": "断链",
    "no-frontmatter": "缺 frontmatter",
    "empty-note": "空笔记",
    "bom": "UTF-8 BOM",
}


def run_checks(vault: Vault, only: Optional[List[str]] = None) -> List[Issue]:
    names = only or list(CHECKS)
    issues: List[Issue] = []
    for name in names:
        issues.extend(CHECKS[name](vault))
    return issues
