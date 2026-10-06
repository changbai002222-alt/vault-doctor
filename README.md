# vault-doctor

给 Obsidian 知识库做体检的命令行工具：找出断链、缺 frontmatter、空笔记、带 BOM 的文件，并能自动修复其中有唯一答案的部分。

- **`check` 只读**；**`fix` 默认只预览**，加 `--write` 才写盘。
- **零依赖**：只用 Python 标准库，Python 3.9+。
- **贴近 Obsidian 的链接规则**：大小写不敏感；按文件名或路径后缀匹配；认 `[[笔记|别名]]`、表格里的 `[[笔记\|别名]]`、`[[笔记#标题]]`、`[[笔记^块]]`、`![[图片.png]]`；代码块和行内代码里的 `[[...]]` 不算链接；`.` 开头的隐藏目录不参与（Obsidian 也不索引它们）。

## 安装

```bash
git clone <仓库地址>
cd vault-doctor
pip install -e .
```

不想安装也可以直接在仓库目录里跑 `python -m vault_doctor`。

## 体检：check

```bash
vault-doctor check ~/我的库                       # 跑全部检查
vault-doctor check ~/我的库 --only broken-link
vault-doctor check ~/我的库 --ignore "40 Archive" --limit 0
vault-doctor check ~/我的库 --json > report.json
```

| 选项 | 作用 |
|---|---|
| `--only CHECK` | 只跑某项，可重复 |
| `--ignore DIR` | 额外跳过某个目录名，可重复 |
| `--config FILE` | 指定配置文件（默认读库根目录的 `.vault-doctor.json`） |
| `--limit N` | 每项最多列 N 条，`0` = 全部（默认 20） |
| `--json` | 输出 JSON |

退出码：`0` 没问题，`1` 发现问题，`2` 参数或配置错误。可以直接接 git hook 或 CI。

| 检查项 | 查什么 |
|---|---|
| `broken-link` | `[[链接]]` 指向的笔记或附件不存在（报文件 + 行号；能找到唯一答案时附上修复建议） |
| `no-frontmatter` | 笔记开头没有 `---` 包住的元数据块 |
| `empty-note` | 去掉 frontmatter 后正文为空 |
| `bom` | 文件以 UTF-8 BOM 开头（一些工具会因此读不到 frontmatter） |

## 修复：fix

```bash
vault-doctor fix ~/我的库                  # 预览，不改任何文件
vault-doctor fix ~/我的库 --write          # 写入
vault-doctor fix ~/我的库 --write --accept prefix   # 连「按名字前缀猜改名」也接受
```

**先确认库有 git 之类的备份再加 `--write`。** 断链修复分三类，只有一个确定答案才会改：

| 类型 | 情形 | 例子 | 默认 |
|---|---|---|---|
| `alias` | 目标是某篇笔记 frontmatter 里的别名 | `[[反脆弱]]` → `[[反脆弱性——在波动中变强\|反脆弱]]` | 应用 |
| `moved` | 带路径的链接，文件本身还在，只是搬了位置 | `[[旧/路径/笔记]]` → `[[笔记]]` | 应用 |
| `prefix` | 笔记后来改了长名字，旧名是新名的前缀（后面跟 `——`、`-`、空格等分隔符） | `[[课表]]` → `[[课表——2026]]` | **需 `--accept prefix`** |

说明：

- 改写时保留 `#标题`、`^块`、显示文字、表格里的 `\|`、`![[嵌入]]`。原来没有显示文字的，会补上原文字，读起来不变。
- 保留文件原有的换行符（CRLF / LF）；混用两种换行、或不是合法 UTF-8 的文件会跳过并说明原因。
- 写入是原子的（先写临时文件再替换）。
- 多个候选、或别名指向笔记自己（通常是「待建」的占位链接）时不改。
- `fix` 还会去掉 UTF-8 BOM。`--no-links` / `--no-bom` 可单独关掉。

## 配置：.vault-doctor.json

放在库根目录，`check` 和 `fix` 都遵守。导入的第三方内容、归档目录通常不该被要求有 frontmatter：

```json
{
  "ignore": ["40 Archive"],
  "checks": {
    "no-frontmatter": { "exclude": ["10 行动线/03 课程/MySQL教程/**"] },
    "bom": { "enabled": false }
  }
}
```

- `ignore`：按目录名整个跳过。
- `checks.<名称>.enabled`：关闭某项检查（命令行 `--only` 可以临时再打开）。
- `checks.<名称>.exclude`：按库内相对路径（用 `/`）的通配符豁免；写目录名等于豁免整个目录。
- 文件必须是合法 JSON（不能有注释）；写错字段名会直接报错，不会悄悄忽略。

## 输出示例

```text
体检：D:\我的库
配置：D:\我的库\.vault-doctor.json
共 1187 个文件，其中笔记 496 篇

[!!] 断链（broken-link）：1
    20 认知线/知识图谱_索引.md:21  找不到目标：[[反脆弱|《反脆弱》]]  → 建议 [[反脆弱性——在波动中变强|《反脆弱》]]（别名）
[OK] 缺 frontmatter（no-frontmatter）：0
[OK] 空笔记（empty-note）：0
[OK] UTF-8 BOM（bom）：0

合计 1 个问题
其中 1 处断链有修复建议（1 处可直接用 vault-doctor fix 修）
```

## 开发

```bash
pip install -e .
python -m unittest discover -s tests -t tests
```

新增检查：在 `vault_doctor/checks.py` 写一个 `check_xxx(vault)` 生成器，产出 `Issue`，再登记到 `CHECKS` 和 `TITLES`。

## 路线图

- [ ] 更多检查：孤儿笔记、文件名规范、重复标题
- [ ] 补最小 frontmatter 的修复
- [ ] Obsidian 插件形态

## 许可证

MIT，见 [LICENSE](LICENSE)。版本历史见 [CHANGELOG.md](CHANGELOG.md)。
