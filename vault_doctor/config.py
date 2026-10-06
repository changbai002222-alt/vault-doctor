"""Optional per-vault config: .vault-doctor.json in the vault root.

{
  "ignore": ["40 Archive"],                       // folder names to skip entirely
  "checks": {
    "no-frontmatter": {"exclude": ["10 行动线/03 课程/MySQL教程/**"]},
    "bom": {"enabled": false}
  }
}

JSON (not TOML/YAML) because it is in the standard library on every Python 3.9+.
Comments are not allowed in the real file.
"""
from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

CONFIG_NAME = ".vault-doctor.json"


class ConfigError(Exception):
    pass


@dataclass
class CheckConfig:
    enabled: bool = True
    exclude: List[str] = field(default_factory=list)  # glob patterns on vault-relative paths

    def excludes(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, pat) or fnmatch.fnmatchcase(path, pat.rstrip("/") + "/**")
                   for pat in self.exclude)


@dataclass
class Config:
    path: Optional[str] = None
    ignore: List[str] = field(default_factory=list)
    checks: Dict[str, CheckConfig] = field(default_factory=dict)

    def for_check(self, name: str) -> CheckConfig:
        return self.checks.get(name, CheckConfig())


def _str_list(value, where: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where} 必须是字符串数组")
    return value


def load_config(vault_root: str, explicit: Optional[str], known_checks) -> Config:
    path = explicit or os.path.join(vault_root, CONFIG_NAME)
    if not os.path.isfile(path):
        if explicit:
            raise ConfigError(f"配置文件不存在：{explicit}")
        return Config()
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} 不是合法 JSON：第 {e.lineno} 行 {e.msg}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 顶层必须是对象")
    unknown = set(data) - {"ignore", "checks"}
    if unknown:
        raise ConfigError(f"{path} 有未知字段：{', '.join(sorted(unknown))}")

    cfg = Config(path=path, ignore=_str_list(data.get("ignore", []), "ignore"))
    checks = data.get("checks", {})
    if not isinstance(checks, dict):
        raise ConfigError("checks 必须是对象")
    for name, opts in checks.items():
        if name not in known_checks:
            raise ConfigError(f"checks 里有未知检查项：{name}（可选：{', '.join(known_checks)}）")
        if not isinstance(opts, dict) or set(opts) - {"enabled", "exclude"}:
            raise ConfigError(f"checks.{name} 只支持 enabled / exclude 两个字段")
        enabled = opts.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"checks.{name}.enabled 必须是 true / false")
        cfg.checks[name] = CheckConfig(enabled, _str_list(opts.get("exclude", []), f"checks.{name}.exclude"))
    return cfg
