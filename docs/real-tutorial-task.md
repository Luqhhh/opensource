# 第一条真实教程改进任务闭环

完成一条助手参与的真实案例：TinyDB 4.9.0 固定提交 `edff96aeb2616402e9489d46e90a592c05565621`，README.rst 首个持久化示例。原始项目与此提交已有实时诊断，后续候选及任务验证独立保存；没有新模型调用，没有改写旧 2×2 实验中“接受文字补丁为 0”的结果。

## 实际任务与改进

任务是“在一个空的可写工作目录复制 README 首个示例，写入原有两条记录，并在关闭重开后核对数据和查询”。[上游 README](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/README.rst#L65-L75) 使用 `/path/to/db.json`。它是明显的占位路径，熟悉这类示例并替换路径的读者可能不会遇到障碍；本例只验证字面复制条件下的首次运行体验，不宣称 TinyDB 的库实现有错误。

此前 Flash 规则检索组已提出“入门示例使用占位路径且未说明文件创建行为”，建议说明可写路径和父目录要求。[存储实现](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/storages.py#L18-L33) 的默认行为也支持这一局部说明。原始诊断、调用记录和时间保存在[录制分析](evidence/tutorial-task-tinydb-20261019/recorded-analysis.json)。

助手据此编写了一个明确候选：将首个代码块中的数据库路径改成相对路径 `db.json`，增加三行正文说明空的可写目录、文件复用和其他路径的父目录要求。两条原有插入语句、其他代码块、记录输出、库源码及全部任务检查均未改变。[上游文档补丁](evidence/tutorial-task-tinydb-20261019/tinydb-first-run.patch) 可供维护者逐行审阅。

## 已完成的验证

| 环节 | 实际结果 | 保存记录 |
| --- | --- | --- |
| 原版任务 | FileNotFoundError，未到达插入步骤 | [before.json](evidence/tutorial-task-tinydb-20261019/before.json) |
| 修改后任务 | 两条原始记录写入、查询、关闭重开后数据校验通过 | [after.json](evidence/tutorial-task-tinydb-20261019/after.json) |
| 导出补丁并应用临时副本 | git apply --check 和实际应用成功，重新提取并执行同一任务通过 | [replay.json](evidence/tutorial-task-tinydb-20261019/replay.json) |
| 负控制：仅改用内存数据库 | 被同一检查拒绝，原因是未满足 JSON 文件持久化任务 | [negative-after.json](evidence/tutorial-task-tinydb-20261019/negative-after.json) |

代码只在原有 fail-closed Bubblewrap runner 中执行，使用同一提交的原字节源码和 `/usr/bin/python3 -I -S`。没有在宿主导入 TinyDB，没有修改用户仓库或上游文件，没有安装包或借用旧版迁移实现。

[任务合同](evidence/tutorial-task-tinydb-20261019/task.json) 在候选构建前冻结，并在 before、after、replay 和负控制中逐字复用；SHA-256 为 `1fc251e279190784cecef1c5f8df0a933668197fa07e857adf65dc48b788a8e4`。候选不包含新增断言，也不能改合同。检查由同一助手编写，因此这是与候选分离的冻结工程检查，不是独立人工标注或盲测。

首次开发运行中，正例已通过，但负例构造遗漏新增导入语句的 REPL 提示符，被“保留原输出”检查在执行前拒绝。该失败产物保留；随后仅修正负控制的提示符，合同、正例候选和原始输入均未调整。完成记录来自单独的新输出目录，不以覆盖失败记录的方式重跑。

## 产品入口

新增 `task-check` 接收一个明确候选与冻结合同，提取 Markdown Python 围栏或有限的 RST Python/pycon 块，验证前后任务，并在临时副本应用导出的补丁复验：

```sh
python3 -m exampleproof task-check /path/to/tinydb-at-edff96ae \
  --contract docs/evidence/tutorial-task-tinydb-20261019/task.json \
  --candidate docs/evidence/tutorial-task-tinydb-20261019/candidate.json \
  --output /tmp/tinydb-task-review
```

输出须是项目外的新目录。报告包括冻结输入摘要、原始合同、候选、before/after/replay 记录和源码实现归档；只有原版失败、修改与补丁复查通过且原输入未变时才生成 `adoptable.patch`，其状态仍为 `human_review_pending`。原版已通过、只有运行成功却未完成任务、隔离阻塞或没有固定 oracle 均不能计作改进成功。

候选是精确匹配的文档替换，必须绑定原始文件 SHA-256。其他 Python 块、原始 REPL 预期输出、RST 指令及原有断言受到保护；选中块仍受既有直线代码守卫限制。此入口不执行安装命令，不支持任意 RST 指令、MDX 或通用结构编辑。`analyze` 的自动文字提案范围保持原有规则，本例由显式候选桥接到任务验证，不声称 `analyze` 已自动生成并验证该补丁。

完整重建这条案例可使用已有冻结研究目录：

```sh
python3 scripts/run_tinydb_first_run_case.py /path/to/archived-study \
  --output /tmp/tinydb-first-run-case
```

脚本校验已有上游文件与研究协议摘要，复用记录中的诊断，再构造候选和负控制，不调用模型。完整审阅包另保留所需上游源码和 MIT 许可证，允许离线重放；[来源清单](evidence/tutorial-task-tinydb-20261019/provenance.json) 与 [输入摘要](evidence/tutorial-task-tinydb-20261019/input-manifest.json) 用于核对。

## 结论边界

已经完成一条真实输入、助手参与的“已有诊断 → 明确修改 → 固定任务验证 → 可审阅补丁”工程闭环。它是同一版本的首次运行可用性案例，不是历史兼容重现；复用的是录制的实时诊断，新候选是助手编写，负控制是合成候选，来源分别标注。

这条案例是观察已有结果后挑选的已知开发项目，不是留出评测。没有验证包安装、完整 README 查询教程、RST 构建渲染或不同操作系统，也没有读者效率、独立人工质量评审或维护者采纳结果。`adoptable.patch` 表示通过这里声明的有限任务检查，仍待团队和上游维护者审核，不能称为上游已接受的改进。
