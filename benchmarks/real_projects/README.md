# 三个真实项目的历史文档迁移案例

本集合从 **TinyDB、more-itertools、MarkupSafe 官方文档**采集 **5 个历史版本迁移失败案例和 3 个健康对照**。全部固定原始文档版本、目标源码版本和提交；保留原始片段、许可证、SHA-256、提取转换、原始异常、工程参考补丁及应用后复查证据。没有人为改坏示例，没有用自造库替代上游代码，也不声称这些是当前上游文档的缺陷。

三组案例是在本仓库既有教程/兼容性开发样例之后新采集的。选取、检查编写及参考候选验证期间没有调用实时模型，没有根据这些案例的模型输出调整提示词；后续公平对照须先冻结案例和条件，再记录所有请求与结果。“未用于本地调提示词”不等于模型训练时未见过这些公开文本。

## 项目与固定版本

| 项目及证据入口 | 官方文档 / 旧版正控制 | 迁移目标源码 | 失败 + 健康 | 来源许可 |
|---|---|---|---|---|
| [TinyDB](tinydb/README.md) | 3.15.2 / [`5e7813053f721ab37acd4ed1e50b41009886f5b2`](https://github.com/msiemens/tinydb/tree/5e7813053f721ab37acd4ed1e50b41009886f5b2) | 4.8.2 / [`10644a0e07ad180c5b756aba272ee6b0dbd12df8`](https://github.com/msiemens/tinydb/tree/10644a0e07ad180c5b756aba272ee6b0dbd12df8) | 2 + 1 | MIT |
| [more-itertools](more_itertools/README.md) | 5.0.0 / [`53c2c692d3175e4487235213465afb14a211ec3c`](https://github.com/more-itertools/more-itertools/tree/53c2c692d3175e4487235213465afb14a211ec3c) | 9.0.0 / [`ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587`](https://github.com/more-itertools/more-itertools/tree/ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587) | 2 + 1 | MIT；Python 文档派生 recipes 保留归属及 PSF 许可文本 |
| [MarkupSafe](markupsafe/README.md) | 1.1.1 / [`22c946de28c2f5916f8c88a983a3e48e1cdbd2fd`](https://github.com/pallets/markupsafe/tree/22c946de28c2f5916f8c88a983a3e48e1cdbd2fd) | 2.1.5 / [`fbba4acd0312826cec9cfe18371c7df07962cb65`](https://github.com/pallets/markupsafe/tree/fbba4acd0312826cec9cfe18371c7df07962cb65) | 1 + 1 | BSD-3-Clause |

旧版 more-itertools 正控制另使用固定 **six 1.16.0** 源码，提交 [`65486e4383f9f411da95937451205d3c7b61b9e1`](https://github.com/benjaminp/six/tree/65486e4383f9f411da95937451205d3c7b61b9e1)，MIT。它只作为旧版隔离运行的源码输入，不安装到宿主，不增加 ExampleProof 运行依赖。MarkupSafe 两版均使用上游提供的纯 Python 实现，结果不涉及 C 扩展。

## 八个案例

| 项目 / 案例 | 上游原始文档位置 | 目标版原始结果 | 检查所约束的主要行为 |
|---|---|---|---|
| TinyDB / [purge_default](tinydb/cases/purge_default.md) | [getting-started.rst L74–75](https://github.com/msiemens/tinydb/blob/5e7813053f721ab37acd4ed1e50b41009886f5b2/docs/getting-started.rst#L74-L75)，初始化 L25–26、L31–32 | `purge` 不存在 | 清空默认表，保留命名表，验证持久化及重新插入 ID |
| TinyDB / [purge_named_table](tinydb/cases/purge_named_table.md) | [usage.rst L463–473](https://github.com/msiemens/tinydb/blob/5e7813053f721ab37acd4ed1e50b41009886f5b2/docs/usage.rst#L463-L473)，初始化同上 | `purge_table` 不存在 | 删除指定表，保留默认表，重建目标表为空 |
| TinyDB / [healthy_query](tinydb/cases/healthy_query.md) | [getting-started.rst L52–55](https://github.com/msiemens/tinydb/blob/5e7813053f721ab37acd4ed1e50b41009886f5b2/docs/getting-started.rst#L52-L55)，初始化同上 | `checked` | 插入数据、两种查询与无匹配结果 |
| more-itertools / [collate](more_itertools/cases/collate.md) | [more.py L363–382](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L363-L382) 中 3 组 doctest | `collate` 导入失败 | 排序归并、重复元素、数值 key、逆序、空输入 |
| more-itertools / [grouper](more_itertools/cases/grouper.md) | [recipes.py L291–292](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/recipes.py#L291-L292) | 旧参数顺序触发 `TypeError` | 分组顺序、最后一项保留、填充值与空输入 |
| more-itertools / [healthy_chunked](more_itertools/cases/healthy_chunked.md) | [more.py L101–102](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L101-L102) | `checked` | 列表分块，不足一组的末尾保留且不填充 |
| MarkupSafe / [safe_string](markupsafe/cases/safe_string.md) | [_native.py L54–66](https://github.com/pallets/markupsafe/blob/22c946de28c2f5916f8c88a983a3e48e1cdbd2fd/src/markupsafe/_native.py#L54-L66) 的公开函数文档 | `soft_unicode` 不存在 | 字符串转换保留安全标记，避免二次转义 |
| MarkupSafe / [optional_values](markupsafe/cases/optional_values.md) | [_native.py L39–47](https://github.com/pallets/markupsafe/blob/22c946de28c2f5916f8c88a983a3e48e1cdbd2fd/src/markupsafe/_native.py#L39-L47) 的公开函数文档 | `checked` | 可空值转换与转义行为 |

表内范围是便于阅读的定位；`provenance.json` 记录实际选择的每组起止行，不能把范围之间的文字误认为执行代码。TinyDB 初始化片段来自 [getting-started.rst L25–32](https://github.com/msiemens/tinydb/blob/5e7813053f721ab37acd4ed1e50b41009886f5b2/docs/getting-started.rst#L25-L32)。more-itertools 和 MarkupSafe 的 docstring 由各自 Sphinx 文档引用，归属链和原始文件一并留存。

## 工程证据与结果边界

同一原始文档和对应检查已在各自旧版本源码上得到 **8/8 checked**，证明这里声明的原始前置条件能成立。目标版本原始检查为 **5 failed、3 checked**；预编参考候选修复 5 个失败案例后，临时副本应用补丁并复查为 **8/8 checked**。这组工程验证全部为 **0 次模型请求**，不能记为模型成功率。

| 项目 | 旧版正控制 | 原始失败 / 参考修复 / 补丁复查 |
|---|---|---|
| TinyDB | [historical-validation.json](tinydb/evidence/historical-validation.json) | [reference-replay/benchmark.json](tinydb/evidence/reference-replay/benchmark.json) |
| more-itertools | [old-version-control/validation.json](more_itertools/evidence/old-version-control/validation.json) | [validation.json](more_itertools/evidence/validation.json) |
| MarkupSafe | [old-version-control/check/report.json](markupsafe/evidence/old-version-control/check/report.json) | [verified/benchmark.json](markupsafe/evidence/verified/benchmark.json) |

候选修复只改变规范化的 `cases/*.md`。导出的 `verified.patch` 可应用于相应基准副本，**不能直接应用到上游仓库的 RST/docstring 文件**；给上游提交改动需要另行映射原位置，并确认维护版本。原始文档、原始库代码与健康对照均保留。

## 纳入、排除与冻结规则

纳入必须同时满足：官方公开来源和明确许可；可固定提交与原始行范围；原始代码通过机械提取而保留 API、输入和操作；两版上游源码可原样映射到沙箱；旧版本正控制通过；目标版本存在可复现失败或明确健康对照；有独立于模型候选的行为检查；每个选定文件不超过 256,000 字节、单项目选定输入合计不超过 2,000,000 字节。

排除需要联网、外部服务、访问真实用户数据、编译扩展才能成立的案例，以及无法隔离执行、无法固定来源/许可、需修改上游实现或人为破坏正确代码才能失败的案例。此前用于提示词开发的教程和自编 CPython 兼容性样例不纳入本集合。框架所不支持的其他语言、异步/多进程复杂场景及超出输入限制的项目也不属于本次评测范围。

本次采用有目的的人工/AI 辅助选取，优先选择容易复现、结果可检查的历史 API 迁移，**不是随机样本**。TinyDB 两个失败来自相近的表管理 API 迁移，八例不能当作八个独立项目。没有维护者使用反馈，也没有统计意义上的项目总体成功率结论。

每个项目的 `verify_provenance.py` 用于核对原样文件与提取过程；各子项目 README 提供复现命令。公平对照应保存冻结清单及 SHA，固定模型、运行参数、每例调用预算和条件顺序；只向模型提供条件允许的代码、文档上下文、源码及执行反馈。**参考候选、负例候选、checks、预期输出、元数据和任何已有修复证据不得作为模型输入。** 冻结后不得根据模型输出改案例、检查、提示词或挑选成功结果；失败、拒绝、请求异常、耗时和 token 消耗均应记录。

在仓库根目录核对三个项目来源：

```sh
PYTHONPATH=. python3 benchmarks/real_projects/tinydb/verify_provenance.py
python3 benchmarks/real_projects/more_itertools/verify_provenance.py
python3 benchmarks/real_projects/markupsafe/verify_provenance.py
```

有限检查不证明所有输入的语义等价，也不是恶意候选的完整安全边界。这个集合支持“真实上游历史文档迁移的可复现实验”这一结论；实时模型效果必须以独立保存的公平对照结果为准。
