"""Health checks. Each check takes a Vault and yields Issues."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterator, List, Optional

from .config import Config
from .fixes import KIND_TITLES, Suggester
from .vault import Vault


@dataclass
class Issue:
    check: str
    path: str
    line: Optional[int]
    message: str
    suggestion: Optional[str] = None  # a fixed [[...]] for broken links
    fix_kind: Optional[str] = None    # alias / moved / prefix

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def check_broken_links(vault: Vault) -> Iterator[Issue]:
    suggester = Suggester(vault)
    for note in vault.notes:
        for link in note.links:
            if vault.resolves(link.target):
                continue
            s = suggester.suggest(note, link)
            msg = f"找不到目标：{link.raw}"
            if s:
                msg += f"  → 建议 {s.replacement}（{KIND_TITLES[s.kind]}）"
            yield Issue("broken-link", note.path, link.line, msg,
                        s.replacement if s else None, s.kind if s else None)


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


def enabled_checks(config: Optional[Config], only: Optional[List[str]] = None) -> List[str]:
    """--only wins over "enabled": false, so a disabled check can still be run on demand."""
    if only:
        return list(only)
    return [n for n in CHECKS if config is None or config.for_check(n).enabled]


def run_checks(vault: Vault, only: Optional[List[str]] = None,
               config: Optional[Config] = None) -> List[Issue]:
    issues: List[Issue] = []
    for name in enabled_checks(config, only):
        rule = config.for_check(name) if config else None
        issues.extend(i for i in CHECKS[name](vault) if not (rule and rule.excludes(i.path)))
    return issues
