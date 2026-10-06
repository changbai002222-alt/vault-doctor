"""Suggest and apply repairs: broken links that have one obvious target, and BOMs.

Suggestion kinds, from most to least certain:
  alias  - [[x]] where exactly one note lists x in alias/aliases
  moved  - [[old/path/x]] where x itself exists exactly once elsewhere
  prefix - [[x]] where exactly one note is named "x——..." / "x--..." (renamed later)
Only alias and moved are applied by default; prefix needs --accept prefix.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .vault import NAME_SEPARATOR_RE, Link, Note, Vault, note_name

SAFE_KINDS = ("alias", "moved")
ALL_KINDS = ("alias", "moved", "prefix")
KIND_TITLES = {"alias": "别名", "moved": "路径已变", "prefix": "改过名"}


@dataclass
class Suggestion:
    kind: str
    new_target: str
    replacement: str  # the full new [[...]] text


def shortest_target(vault: Vault, rel: str) -> str:
    """Name Obsidian would write for this file: bare name if unique, else full path."""
    name = note_name(rel)
    if vault.lookup(name) == [rel]:
        return name
    return rel[:-3] if rel.lower().endswith(".md") else rel


def render(link: Link, new_target: str, keep_old_text: bool) -> str:
    """Rebuild a link with a new target, keeping #heading/^block, the display
    text, the table-safe "\\|" and the "!" of embeds."""
    display = link.display
    if display is None and keep_old_text and not link.embed:
        display = link.target  # keep what the reader saw before
    sep = "\\|" if link.escaped_pipe else "|"
    ref = new_target + link.subpath
    inner = ref if display is None or display == ref else ref + sep + display
    return ("!" if link.embed else "") + "[[" + inner + "]]"


class Suggester:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.alias_index: Dict[str, List[str]] = {}
        self.names: List[Tuple[str, str]] = []  # (lowercase note name, path)
        for note in vault.notes:
            self.names.append((note_name(note.path).lower(), note.path))
            for alias in note.aliases:
                self.alias_index.setdefault(alias.lower(), []).append(note.path)

    def suggest(self, note: Note, link: Link) -> Optional[Suggestion]:
        target = link.target.replace("\\", "/").strip()
        key = target.lower()
        if key.endswith(".md"):
            key = key[:-3]

        # alias: a self-link through an alias usually marks a note still to be
        # written ("待建"), so it is not a fix.
        hits = sorted(set(self.alias_index.get(key, [])))
        if len(hits) == 1 and hits[0] != note.path:
            return self._make("alias", link, shortest_target(self.vault, hits[0]), True)

        if "/" in target:
            base = target.rsplit("/", 1)[-1]
            found = self.vault.lookup(base)
            if len(found) == 1:
                return self._make("moved", link, shortest_target(self.vault, found[0]), False)

        if "/" not in key:
            cands = [p for name, p in self.names
                     if name.startswith(key) and NAME_SEPARATOR_RE.match(name[len(key):])]
            if len(cands) == 1 and cands[0] != note.path:
                return self._make("prefix", link, shortest_target(self.vault, cands[0]), True)
        return None

    @staticmethod
    def _make(kind: str, link: Link, new_target: str, keep_old_text: bool) -> Suggestion:
        return Suggestion(kind, new_target, render(link, new_target, keep_old_text))


@dataclass
class FileFix:
    path: str
    changes: List[str]  # human-readable, one per change
    new_text: str       # final file content, original line endings restored
    drop_bom: bool


def plan_fixes(vault: Vault, notes: Iterable[Note], accept: Iterable[str],
               fix_bom: Callable[[str], bool],
               fix_links: Callable[[str], bool]) -> Tuple[List[FileFix], List[str]]:
    """Return (files to rewrite, notes that were skipped and why).
    fix_bom / fix_links take a vault-relative path, so config excludes apply per file."""
    accept = set(accept)
    suggester = Suggester(vault)
    fixes: List[FileFix] = []
    skipped: List[str] = []
    for note in notes:
        changes: List[str] = []
        edits: List[Tuple[int, int, str]] = []
        if fix_links(note.path):
            for link in note.links:
                if vault.resolves(link.target):
                    continue
                s = suggester.suggest(note, link)
                if s and s.kind in accept:
                    edits.append((link.start, link.end, s.replacement))
                    changes.append(f"第 {link.line} 行  {link.raw}  →  {s.replacement}"
                                   f"（{KIND_TITLES[s.kind]}）")
        drop_bom = note.has_bom and fix_bom(note.path)
        if drop_bom:
            changes.append("去掉 UTF-8 BOM")
        if not changes:
            continue
        if not note.valid_utf8 or note.newline is None:
            why = "不是合法 UTF-8" if not note.valid_utf8 else "混用了 CRLF 和 LF"
            skipped.append(f"{note.path}（{why}，为免损坏未改动）")
            continue
        text = note.text
        for start, end, new in sorted(edits, reverse=True):
            text = text[:start] + new + text[end:]
        if note.newline != "\n":
            text = text.replace("\n", note.newline)
        fixes.append(FileFix(note.path, changes, text, drop_bom))
    return fixes, skipped


def write_fix(vault: Vault, fix: FileFix, had_bom: bool) -> None:
    data = fix.new_text.encode("utf-8")
    if had_bom and not fix.drop_bom:
        data = b"\xef\xbb\xbf" + data
    # Write a sibling temp file, then swap it in: a crash never leaves a half-written note.
    target = vault.full_path(fix.path)
    tmp = target + ".vd-tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

