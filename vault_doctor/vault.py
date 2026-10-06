"""Load an Obsidian vault: find notes, split frontmatter, extract wikilinks."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# Hidden folders (".git", ".obsidian", ...) are always skipped; see Vault._load.
DEFAULT_IGNORE = {"node_modules"}

# Code is stripped before link extraction: [[x]] inside code is not a link.
CODE_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[`~]*[ \t]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
FM_KEY_RE = re.compile(r"^([^\s:#-][^:]*?)\s*:(.*)$")


@dataclass
class Link:
    target: str  # note/file name, without #heading, ^block or |alias
    line: int
    raw: str     # the full [[...]] text, for reporting
    embed: bool


@dataclass
class Note:
    path: str                              # relative to vault root, "/" separated
    text: str
    has_bom: bool
    frontmatter: Optional[Dict[str, str]]  # top-level key -> raw value; None = no block
    body: str
    links: List[Link] = field(default_factory=list)


def split_frontmatter(text: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Return (top-level keys, body). Only the keys matter for v0.1 checks,
    so this is a deliberately small parser, not a full YAML reader."""
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ("---", "..."):
            keys = {}
            for line in lines[1:i]:
                m = FM_KEY_RE.match(line)
                if m:
                    keys[m.group(1)] = m.group(2).strip()
            return keys, "\n".join(lines[i + 1:])
    return None, text  # unclosed block: Obsidian treats it as body too


def _blank_keep_newlines(m: "re.Match[str]") -> str:
    return "\n" * m.group(0).count("\n")


def extract_links(text: str) -> List[Link]:
    # Blank out code but keep newlines, so line numbers stay correct.
    clean = CODE_FENCE_RE.sub(_blank_keep_newlines, text)
    clean = INLINE_CODE_RE.sub("", clean)
    links = []
    for m in WIKILINK_RE.finditer(clean):
        # "\|" is the escaped alias separator used inside Markdown tables.
        target = re.split(r"\\?\|", m.group(2), maxsplit=1)[0]
        target = re.split(r"[#^]", target, maxsplit=1)[0].strip()
        if not target:
            continue  # [[#heading]] points into the same note
        line = clean.count("\n", 0, m.start()) + 1
        links.append(Link(target, line, m.group(0), bool(m.group(1))))
    return links


def _lookup_keys(rel_path: str) -> List[str]:
    """Every name a link may use for this file: "a/b/c.md" -> c, b/c, a/b/c.
    Non-.md files keep their extension; .md notes are also reachable with it."""
    parts = rel_path.lower().split("/")
    keys = ["/".join(parts[i:]) for i in range(len(parts))]
    if rel_path.lower().endswith(".md"):
        keys += [k[:-3] for k in keys]
    return keys


def _normalize_target(target: str) -> str:
    t = target.replace("\\", "/").strip().lower()
    while t.startswith("./"):
        t = t[2:]
    return t.lstrip("/")


class Vault:
    def __init__(self, root: str, ignore: Optional[Set[str]] = None):
        self.root = os.path.abspath(root)
        self.ignore = set(DEFAULT_IGNORE) if ignore is None else set(ignore)
        self.notes: List[Note] = []
        self.file_count = 0
        self._keys: Set[str] = set()
        self._load()

    def _load(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Obsidian never indexes dot-folders, so links into them don't resolve either.
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in self.ignore and not d.startswith("."))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                self.file_count += 1
                self._keys.update(_lookup_keys(rel))
                if name.lower().endswith(".md"):
                    self.notes.append(self._read_note(full, rel))

    @staticmethod
    def _read_note(full: str, rel: str) -> Note:
        with open(full, "rb") as f:
            raw = f.read()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        fm, body = split_frontmatter(text)
        return Note(rel, text, has_bom, fm, body, extract_links(text))

    def resolves(self, target: str) -> bool:
        """Obsidian matches links case-insensitively, by name or path suffix."""
        return _normalize_target(target) in self._keys
