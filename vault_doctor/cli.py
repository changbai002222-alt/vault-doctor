"""Command line entry: vault-doctor check <vault> [options]."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .checks import CHECKS, TITLES, run_checks
from .vault import DEFAULT_IGNORE, Vault


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vault-doctor", description="Obsidian 知识库体检工具")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="体检一个库（只读，不改任何文件）")
    c.add_argument("vault", help="库的根目录")
    c.add_argument("--only", action="append", choices=list(CHECKS), metavar="CHECK",
                   help=f"只跑某项检查，可重复；可选：{', '.join(CHECKS)}")
    c.add_argument("--ignore", action="append", default=[], metavar="DIR",
                   help="额外跳过的目录名，可重复（. 开头的隐藏目录和 node_modules 总是跳过，与 Obsidian 一致）")
    c.add_argument("--json", action="store_true", help="输出 JSON，方便接脚本")
    c.add_argument("--limit", type=int, default=20,
                   help="每项最多列出多少条，0 = 全部（默认 20；--json 不受影响）")
    return p


def _print_report(vault: Vault, issues, names: List[str], limit: int) -> None:
    print(f"体检：{vault.root}")
    print(f"共 {vault.file_count} 个文件，其中笔记 {len(vault.notes)} 篇\n")
    for name in names:
        group = [i for i in issues if i.check == name]
        mark = "[OK]" if not group else "[!!]"  # ASCII: GBK consoles can't print ✔
        print(f"{mark} {TITLES[name]}（{name}）：{len(group)}")
        shown = group if limit <= 0 else group[:limit]
        for i in shown:
            where = f"{i.path}:{i.line}" if i.line else i.path
            print(f"    {where}  {i.message}")
        if len(shown) < len(group):
            print(f"    …还有 {len(group) - len(shown)} 条，用 --limit 0 看全部")
    print(f"\n合计 {len(issues)} 个问题")


def main(argv: Optional[List[str]] = None) -> int:
    # Piped output on Windows uses the ANSI code page; never crash on odd file names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.vault):
        print(f"错误：目录不存在：{args.vault}", file=sys.stderr)
        return 2

    vault = Vault(args.vault, ignore=DEFAULT_IGNORE | set(args.ignore))
    names = args.only or list(CHECKS)
    issues = run_checks(vault, names)

    if args.json:
        out = {
            "vault": vault.root,
            "files": vault.file_count,
            "notes": len(vault.notes),
            "counts": {n: sum(1 for i in issues if i.check == n) for n in names},
            "issues": [i.to_dict() for i in issues],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_report(vault, issues, names, args.limit)
    return 1 if issues else 0
