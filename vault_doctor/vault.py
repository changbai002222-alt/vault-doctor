"""Load an Obsidian vault: find notes, split frontmatter, extract wikilinks."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# Hidden folders (".git", ".obsidian", ...) are always skipped; see Vault._load.
DEFAULT_IGNORE = {"node_modules"}

# Code is blanked before link extraction: [[x]] inside code is not a link.
CODE_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[`~]*[ \t]*$", re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
FM_KEY_RE = re.compile(r"^([^\s:#-][^:]*?)\s*:(.*)$")
FM_ITEM_RE = re.compile(r"^\s+-\s*(.*)$")
# What may follow a short name inside a longer file name: "概念——观点", "标题--2026.9.7".
NAME_SEPARATOR_RE = re.compile(r"^[\s\-—_｜|:：,，.]")


@dataclass
class Link:
    target: str            # note/file name, without #heading, ^block or |alias
    line: int
    raw: str               # the full [[...]] text, for reporting
    embed: bool
    start: int = 0         # offsets of raw in Note.text
    end: int = 0
    subpath: str = ""      # "#heading" or "^block", kept when rewriting
    display: Optional[str] = None
    escaped_pipe: bool = False  # "\|" separator, as used inside Markdown tables


@dataclass
class Note:
    path: str                     # relative to vault root, "/" separated
    text: str                     # BOM removed, newlines normalized to "\n"
    has_bom: bool
    frontmatter: Optional[dict]   # top-level key -> str or list of str; None = no block
    body: str
    links: List[Link] = field(default_factory=list)
    newline: Optional[str] = "\n"  # original line ending; None = mixed CRLF/LF
    valid_utf8: bool = True        # False = undecodable bytes were replaced

    @property
    def aliases(self) -> List[str]:
        if not self.frontmatter:
            return []
        out: List[str] = []
        for key in ("alias", "aliases"):
            out.extend(_as_list(self.frontmatter.get(key)))
        return out


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    return s.strip()


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif value.startswith("[") and value.endswith("]"):
        items = value[1:-1].split(",")
    else:
        items = [value]
    return [v for v in (_unquote(i) for i in items) if v]


def split_frontmatter(text: str) -> Tuple[Optional[dict], str]:
    """Return (top-level keys, body). Values are raw strings, or lists for
    "key:\\n  - item" blocks. Deliberately small; not a full YAML reader."""
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ("---", "..."):
            keys: dict = {}
            last = None
            for line in lines[1:i]:
                m = FM_KEY_RE.match(line)
                if m:
                    last = m.group(1)
                    keys[last] = m.group(2).strip()
                    continue
                item = FM_ITEM_RE.match(line)
                if item and last is not None:
                    if not isinstance(keys[last], list):
                        keys[last] = [keys[last]] if keys[last] else []
                    keys[last].append(item.group(1).strip())
            return keys, "\n".join(lines[i + 1:])
    return None, text  # unclosed block: Obsidian treats it as body too


def _blank(m: "re.Match[str]") -> str:
    # Same length, newlines kept: offsets and line numbers stay valid.
    return re.sub(r"[^\n]", " ", m.group(0))


def extract_links(text: str) -> List[Link]:
    clean = CODE_FENCE_RE.sub(_blank, text)
    clean = INLINE_CODE_RE.sub(_blank, clean)
    links = []
    for m in WIKILINK_RE.finditer(clean):
        inner = m.group(2)
        sep = re.search(r"\\?\|", inner)
        ref = inner[:sep.start()] if sep else inner
        display = inner[sep.end():] if sep else None
        cut = re.search(r"[#^]", ref)
        target = (ref[:cut.start()] if cut else ref).strip()
        if not target:
            continue  # [[#heading]] points into the same note
        links.append(Link(
            target=target,
            line=clean.count("\n", 0, m.start()) + 1,
            raw=text[m.start():m.end()],
            embed=bool(m.group(1)),
            start=m.start(),
            end=m.end(),
            subpath=ref[cut.start():].strip() if cut else "",
            display=display,
            escaped_pipe=bool(sep) and sep.group(0) == "\\|",
        ))
    return links


def _lookup_keys(rel_path: str) -> List[str]:
    """Every name a link may use for this file: "a/b/c.md" -> c, b/c, a/b/c.
    Non-.md files keep their extension; .md notes are also reachable with it."""
    parts = rel_path.lower().split("/")
    keys = ["/".join(parts[i:]) for i in range(len(parts))]
    if rel_path.lower().endswith(".md"):
        keys += [k[:-3] for k in keys]
    return keys


def normalize_target(target: str) -> str:
    t = target.replace("\\", "/").strip().lower()
    while t.startswith("./"):
        t = t[2:]
    return t.lstrip("/")


def note_name(rel_path: str) -> str:
    """"a/b/笔记.md" -> "笔记"; attachments keep their extension."""
    base = rel_path.rsplit("/", 1)[-1]
    return base[:-3] if base.lower().endswith(".md") else base


class Vault:
    def __init__(self, root: str, ignore: Optional[Set[str]] = None):
        self.root = os.path.abspath(root)
        self.ignore = set(DEFAULT_IGNORE) if ignore is None else set(ignore)
        self.notes: List[Note] = []
        self.files: List[str] = []
        self._keys: Dict[str, List[str]] = {}  # lookup key -> files it can mean
        self._load()

    @property
    def file_count(self) -> int:
        return len(self.files)

    def _load(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Obsidian never indexes dot-folders, so links into them don't resolve either.
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in self.ignore and not d.startswith("."))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                self.files.append(rel)
                for key in _lookup_keys(rel):
                    self._keys.setdefault(key, []).append(rel)
                if name.lower().endswith(".md"):
                    self.notes.append(self._read_note(full, rel))

    @staticmethod
    def _read_note(full: str, rel: str) -> Note:
        with open(full, "rb") as f:
            raw = f.read()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            decoded, valid = raw.decode("utf-8-sig"), True
        except UnicodeDecodeError:
            decoded, valid = raw.decode("utf-8-sig", errors="replace"), False
        crlf = decoded.count("\r\n")
        lf = decoded.count("\n") - crlf
        newline = "\r\n" if crlf and not lf else "\n" if not crlf else None
        text = decoded.replace("\r\n", "\n")
        fm, body = split_frontmatter(text)
        return Note(rel, text, has_bom, fm, body, extract_links(text), newline, valid)

    def full_path(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split("/"))

    def resolves(self, target: str) -> bool:
        """Obsidian matches links case-insensitively, by name or path suffix.
        Aliases do NOT make [[alias]] resolve; they only help autocomplete."""
        return normalize_target(target) in self._keys

    def lookup(self, target: str) -> List[str]:
        return self._keys.get(normalize_target(target), [])

