# TinyDB：真实上游文档的版本迁移证据

本目录使用 [TinyDB](https://github.com/msiemens/tinydb) 官方 **v3.15.2** 文档中的真实命令，在固定的 **v4.8.2** 源码上复现两项 API 迁移失败，并保留一个正常查询对照。它们属于 `version_migration`，**不是 TinyDB 当前文档缺陷，也不是人为修改正确示例制造的错误**。

原文命令的唯一文本处理是去掉 `>>> ` 提示符，并按来源顺序拼接文档中的初始化与操作片段。原始 RST、两版代码、原始 MIT 许可证均保存在本目录，完整来源、行号、SHA-256 与映射在 [provenance.json](provenance.json)。没有安装第三方依赖；运行源码保持字节一致。

| 内容 | 固定版本 | 精确提交 |
|---|---|---|
| 原始文档及历史正确性复验 | v3.15.2 | `5e7813053f721ab37acd4ed1e50b41009886f5b2` |
| 迁移目标及修复后复验 | v4.8.2 | `10644a0e07ad180c5b756aba272ee6b0dbd12df8` |

| 案例 | 原始文档位置 | v4.8.2 原始结果 | 参考补丁 | 应用补丁复查 |
|---|---|---|---|---|
| 清空默认表 | `docs/getting-started.rst:74–75`；初始化 `25–26, 31–32` | `AttributeError: 'Table' object has no attribute 'purge'` | `db.purge()` → `db.truncate()` | `checked` |
| 删除指定表 | `docs/usage.rst:463–465, 473`；初始化同上 | `AttributeError: 'Table' object has no attribute 'purge_table'` | `db.purge_table(...)` → `db.drop_table(...)` | `checked` |
| 正常水果查询 | `docs/getting-started.rst:52–55`；初始化同上 | `checked` | 不生成候选 | `checked` |

这些替换来自目标版本的 [官方升级指南](https://github.com/msiemens/tinydb/blob/10644a0e07ad180c5b756aba272ee6b0dbd12df8/docs/upgrade.rst#L3-L16)。两项迁移均有实际 `before.stderr`、候选内容、候选执行结果及补丁复查记录，见 [reference-replay/benchmark.json](evidence/reference-replay/benchmark.json)、[原始失败报告](evidence/reference-replay/baseline/report.json)、[修复报告](evidence/reference-replay/repair/report.json)、[补丁](evidence/reference-replay/repair/verified.patch) 和 [复查报告](evidence/reference-replay/patched/report.json)。

**以上 2/2 是预先编写参考候选的回放结果，模型调用为 0，不能当作模型修复率。** 此目录的案例、检查和参考答案在新一轮模型对照前准备；它们未参与本项目此前提示词调整，但上游公开文本是否存在于模型训练集未知。模型对照应使用这些已冻结案例，并排除 `proposals.json`、`negative_proposals.json`、元数据、检查及历史/修复证据，不得将答案发送给模型。

## 检查约束与旧版本验证

外部检查存于 [exampleproof.json](exampleproof.json)，在修复候选之外冻结：

- 清空默认表后仍须保留表本身与独立的 `archive` 表，持久化存储必须反映清空，重新插入的 ID 从 1 开始。`archive` 是明确记录的检查夹具，由 setup 在隔离 `/tmp` 中创建；不是上游原文的一部分。
- 删除指定表须真正删除该表，同时保留默认表的两条水果记录；再次创建同名表必须为空，并能从 ID 1 插入记录。
- 正常查询对照检查全部数据、两种查询及无匹配结果。

所有案例使用同一检查在文档对应的 **v3.15.2 原始源码**上执行得到 **3/3 `checked`**，见 [historical-validation.json](evidence/historical-validation.json)。这证明迁移前片段在这里声明的前置条件下有效；并非只根据发行说明推断旧版能够运行。

两个故意写错的作用域候选分别把“清空默认表”改成“删除全部表”、把“删除指定表”改成“清空默认表”。两者都被外部检查拒绝，见 [negative-replay/benchmark.json](evidence/negative-replay/benchmark.json)。这是定向检查的验证，不能解释为通用误修复率。

## 复现

在仓库根目录执行，需要允许命名空间隔离的 Bubblewrap 和 `/usr/bin/python3`。示例执行没有宿主回退。首次验证使用 CPython 3.10.12。

```bash
PYTHONPATH=. python3 benchmarks/real_projects/tinydb/verify_provenance.py
PYTHONPATH=. python3 benchmarks/real_projects/tinydb/verify_provenance.py --historical-output artifacts/tinydb-historical.json
python3 -m exampleproof benchmark benchmarks/real_projects/tinydb --proposals benchmarks/real_projects/tinydb/proposals.json --output artifacts/tinydb-reference
python3 -m exampleproof benchmark benchmarks/real_projects/tinydb --proposals benchmarks/real_projects/tinydb/negative_proposals.json --output artifacts/tinydb-negative
```

输出路径须为新的文件/目录。参考候选命令预期退出码 0：原始结果 `failed: 2, checked: 1`，修复 `verified_repair: 2, checked: 1`，`git apply --check` 和临时副本补丁应用成功，复查 `checked: 3`。负例命令预期退出码 1：两项 `repair_failed`，正常对照保留。隔离不可用的 `blocked` 不算复现成功。

## 资源与局限

TinyDB 两个版本的源码和相关文档均按其 MIT 许可证复制；原始许可证分别在 [v3.15.2/LICENSE](upstream/v3.15.2/LICENSE) 和 [v4.8.2/LICENSE](upstream/v4.8.2/LICENSE)。可选的 `mypy_plugin.py` 未复制，因为它只用于静态分析并依赖 mypy；运行所需的库实现未作修改。`tinydb/*.py` 原路径直接对应沙箱 `/workspace/tinydb/*.py`，历史副本仅在旧版本验证时映射至该包路径。

本组只有一个项目的两个小型、已知且相近的迁移案例，不是随机采样，也没有维护者使用反馈。检查和参考候选由 AI 辅助编写，需要团队审核。有限行为检查无法证明所有输入语义等价；示例与检查共享 Python 进程，不构成针对恶意篡改的完整边界。真实模型结果应以独立冻结的对照报告为准。
