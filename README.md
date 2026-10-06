# vault-doctor

给 Obsidian 知识库做体检的命令行工具：找出断链、缺 frontmatter、空笔记、带 BOM 的文件。

- **只读**：不改库里任何文件。
- **零依赖**：只用 Python 标准库，Python 3.9+。
- **贴近 Obsidian 的链接规则**：大小写不敏感；按文件名或路径后缀匹配；认 `[[笔记|别名]]`、表格里的 `[[笔记\|别名]]`、`[[笔记#标题]]`、`[[笔记^块]]`、`![[图片.png]]`；代码块和行内代码里的 `[[...]]` 不算链接；`.` 开头的隐藏目录不参与（Obsidian 也不索引它们）。

## 安装

```bash
git clone <仓库地址>
cd vault-doctor
pip install -e .
```

不想安装也可以直接在仓库目录里跑 `python -m vault_doctor`。

## 用法

```bash
vault-doctor check ~/我的库                 # 跑全部检查
vault-doctor check ~/我的库 --only broken-link
vault-doctor check ~/我的库 --ignore 40\ Archive --limit 0
vault-doctor check ~/我的库 --json > report.json
```

| 选项 | 作用 |
|---|---|
| `--only CHECK` | 只跑某项，可重复 |
| `--ignore DIR` | 额外跳过某个目录名，可重复 |
| `--limit N` | 每项最多列 N 条，`0` = 全部（默认 20） |
| `--json` | 输出 JSON |

退出码：`0` 没问题，`1` 发现问题，`2` 参数错误。可以直接接 git hook 或 CI。

## 检查项

| 名称 | 查什么 |
|---|---|
| `broken-link` | `[[链接]]` 指向的笔记或附件不存在（报文件名 + 行号） |
| `no-frontmatter` | 笔记开头没有 `---` 包住的元数据块 |
| `empty-note` | 去掉 frontmatter 后正文为空 |
| `bom` | 文件以 UTF-8 BOM 开头（一些工具会因此读不到 frontmatter） |

## 输出示例

```
体检：D:\我的库
共 1186 个文件，其中笔记 495 篇

[!!] 断链（broken-link）：2
    20 认知线/知识图谱_索引.md:21  找不到目标：[[反脆弱|《反脆弱》]]
    50 Journal/2026-09-27.md:16  找不到目标：[[ChatGPT 对话]]
[OK] 缺 frontmatter（no-frontmatter）：0
[OK] 空笔记（empty-note）：0
[OK] UTF-8 BOM（bom）：0

合计 2 个问题
```

## 开发

```bash
python -m unittest discover -s tests -t tests   # 需把仓库根目录加进 PYTHONPATH，或先 pip install -e .
```

新增检查：在 `vault_doctor/checks.py` 写一个 `check_xxx(vault)` 生成器，产出 `Issue`，再登记到 `CHECKS` 和 `TITLES`。

## 路线图

- [ ] `--fix`：自动去 BOM、补最小 frontmatter
- [ ] 配置文件：按目录豁免检查（如第三方导入内容不要求 frontmatter）
- [ ] 更多检查：孤儿笔记、文件名规范、重复标题

## 许可证

MIT
