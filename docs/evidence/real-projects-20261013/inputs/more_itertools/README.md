# more-itertools 真实项目版本迁移证据

本目录从 **more-itertools 5.0.0 官方函数文档**逐行提取 2 个失效案例和 1 个健康对照，并使用未经修改的 **9.0.0 源码**在隔离环境运行。失效源于已公布的 API 迁移，**不是当前上游文档缺陷**，也没有为了制造失败而改坏示例。示例来自项目自身 docstring，`docs/api.rst` 通过 Sphinx `autofunction` 将它们呈现为官方 API 文档。

| 项目版本 | 精确提交 | 用途 |
|---|---|---|
| 5.0.0 | [`53c2c692d3175e4487235213465afb14a211ec3c`](https://github.com/more-itertools/more-itertools/tree/53c2c692d3175e4487235213465afb14a211ec3c) | 原始文档与期望结果 |
| 9.0.0 | [`ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587`](https://github.com/more-itertools/more-itertools/tree/ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587) | 目标运行源码与官方迁移记录 |

## 逐例结果

| 案例 | 原始文档位置 | 原始失败 | 参考修复 | 临时副本应用补丁后 |
|---|---|---|---|---|
| [collate](cases/collate.md) | [more.py L363–382](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L363-L382) 中 3 组 doctest | `ImportError: cannot import name 'collate'` | `from heapq import merge as collate` | `checked`，三组原始输出及额外输入全部通过 |
| [grouper](cases/grouper.md) | [recipes.py L291–292](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/recipes.py#L291-L292) | `TypeError: 'int' object is not iterable` | 将实参改为 `grouper('ABCDEFG', 3, fillvalue='x')` | `checked`，原始输出、整除、空输入与末尾填充通过 |
| [healthy_chunked](cases/healthy_chunked.md) | [more.py L101–102](https://github.com/more-itertools/more-itertools/blob/53c2c692d3175e4487235213465afb14a211ec3c/more_itertools/more.py#L101-L102) | 无，原本为 `checked` | 无候选，未修改 | `checked` |

官方 [9.0.0 版本记录 L8–15](https://github.com/more-itertools/more-itertools/blob/ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587/docs/versions.rst#L8-L15) 明确记录 `collate` 被移除、`grouper` 不再接受整数作为首个参数。该记录用于解释迁移原因，不作为模型的额外答案提示。

2026-10-13 实测：原始检查 **2 failed、1 checked**；预编参考候选回放 **2 verified_repair、1 checked**；临时副本 `git apply --check`、`git apply` 均成功，随后完整文档检查 **3 checked**。全程 **0 次模型请求**，3 个选定源码文件的 SHA-256 在补丁复查前后相同，健康对照没有生成候选。

原始记录分别见 [check.json](evidence/check.json)、[replay.json](evidence/replay.json)、[verified.patch](evidence/verified.patch)、[post_patch.json](evidence/post_patch.json) 和 [validation.json](evidence/validation.json)。这些结果仅证明工程复现和参考补丁有效；实时模型结果由仓库级公平对照独立记录。

旧版本正控制也已实测：同一份 3 个原始文档、同一 setup、同一外部检查和原始预期输出，在未经修改的 **5.0.0 + six 1.16.0** 源码上经 Bubblewrap 执行，得到 **3 checked**，见 [旧版报告](evidence/old-version-control/check/report.json) 与 [验证摘要](evidence/old-version-control/validation.json)。外部 `grouper` 检查使用两个版本共有的具名参数；原始文档仍保留旧的位置参数，目标版因此确实失败。所有检查调整均在冻结和实时模型请求前完成。

## 提取、来源与许可

- `original/*.doctest` 保留上游对应行的原样文本；`upstream/5.0.0/` 保存完整原始文件以便核对上下文。`provenance.json` 逐例记录精确行范围、URL、SHA-256 和转换步骤。
- Markdown 运行形式机械去除缩进和 `>>>`，补充 `from more_itertools import <符号>` 以还原文档隐含的模块命名空间，并用 `print(...)` 包装裸表达式以保留交互式结果显示。输入、调用参数、赋值及文档预期值没有改变。原始期望输出置于配置的 `expected_stdout`。
- 运行源码为 `more_itertools/__init__.py`、`more.py`、`recipes.py` 三个完整文件，合计 156,459 字节；文件内容与目标提交完全一致，没有伪造 SDK、修改库实现、安装第三方包或在宿主解释器导入下载源码。
- 上游声明 **MIT**，两个版本的版权/许可文本完整保存于 `upstream/<版本>/LICENSE`。`recipes.py` 自带的 Python `itertools` 文档来源归属也原样保留，另归档 [完整 PSF License Version 2 及历史版权/许可文本](upstream/cpython-3.7.0/LICENSE) 与 [来源说明](upstream/PYTHON-RECIPES-NOTICE.md)。许可文本取自固定 CPython 3.7.0 提交并记录 SHA；没有声称所有历史 recipes 都适用 0BSD，也没有将此版本视为每个 recipe 的精确来源。复制资源不属于本作品的自主实现。
- 旧版依赖 six 1.16.0，固定提交 [`65486e4383f9f411da95937451205d3c7b61b9e1`](https://github.com/benjaminp/six/tree/65486e4383f9f411da95937451205d3c7b61b9e1)，原始 `six.py` 和 MIT 许可证保存在 `upstream/six-1.16.0/`，只给旧版正控制的沙箱使用，不增加作品运行依赖或主机安装。
- `proposals.json` 是 AI 辅助编写的工程参考候选，不给模型读取。外部行为检查由评测配置持有，在实时模型运行前冻结，不能把候选新增断言算作独立证据。

## 复现

在仓库根目录运行，需要 Linux、可用的 Bubblewrap 命名空间和 `/usr/bin/python3`。实际解释器为 CPython 3.10.12，所有示例均经失败即关闭的 `SandboxRunner` 执行。

```bash
python3 -m exampleproof check benchmarks/real_projects/more_itertools --output artifacts/more-itertools-check
python3 -m exampleproof repair benchmarks/real_projects/more_itertools --proposals benchmarks/real_projects/more_itertools/proposals.json --output artifacts/more-itertools-reference
python3 benchmarks/real_projects/more_itertools/verify_provenance.py
python3 benchmarks/real_projects/more_itertools/verify_provenance.py --historical-output artifacts/more-itertools-historical
```

第一条预期退出码 1；第二条预期退出码 0。导出的补丁须在临时副本中应用并再次执行 `check`；保留本目录原始失效案例用于复现。**`verified.patch` 只适用于本目录规范化后的 `cases/*.md`，不是可以直接应用到上游 5.0.0 或 9.0.0 仓库的补丁。** 若给上游提交变更，需要人工将对应调用映射回原始 RST/docstring，并按所维护版本判断是否适用。

来源校验脚本核对全部 14 个上游原样文件、原始行片段、机械转换后的代码、预期输出和输入大小；普通校验不会执行上游代码。带 `--historical-output` 时仅通过 `SandboxRunner` 运行旧版正控制，输出目录必须尚不存在。

## 结论边界

只验证这 2 个版本迁移案例及 1 个健康对照，不代表该项目整体可靠性。旧版正控制使用当前声明的 CPython 3.10.12 和 six 1.16.0，不代表重建了 5.0.0 发布时的整套系统环境。这些公开示例可能出现在模型训练数据中；“未见案例”仅指没有进入本仓库此前提示词优化过程。外部检查与候选共享 Python 进程，不构成针对恶意候选的完整安全边界，也不能把预编参考候选回放成功率作为模型成绩。
