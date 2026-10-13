# 首批案例与来源

| 示例 | 类型 | 预期现象 | 来源 |
|---|---|---|---|
| README.md#1 | 真实兼容性变更的自编重现 | Python 3.10+ 从 collections 导入 Mapping 失败 | [Python 3.10 移除项](https://docs.python.org/3.10/whatsnew/3.10.html#removed) |
| README.md#2 | 自制 SDK 测试夹具 | digits 关键字改为 decimals | 本仓库原创 sdk/__init__.py |
| README.md#3 | 自制 SDK 测试夹具 | 字典下标读取改为 dataclass 属性读取 | 本仓库原创 sdk/__init__.py |
| README.md#4 | 正常对照 | 无需修复，不能调用修复服务 | 本仓库原创 |
| README.md#5 | 上下文不足对照 | 明确跳过，不能计为通过 | 本仓库原创 |
| README.md#6 | 无行为检查对照 | 可以执行，行为仍未验证 | 本仓库原创 |

proposals.json 是本轮 AI 辅助开发时编写并保存的候选补丁。演示重放这些候选，实际执行检查，但没有进行在线模型推理。记录候选通过复验不代表模型在未见案例上的修复能力。

proposals.multiround.json 在相同案例上演示多轮回放：`README.md#2` 的第一轮使用不受支持的 `precision` 关键字，复验失败；第二轮改用源码定义的 `decimals` 并保留原断言。它没有增加真实缺陷或实时模型样本，只验证逐轮记录、停止条件和最终补丁筛选。

## CPython 历史兼容性小型基准

[benchmarks/compatibility](../benchmarks/compatibility/README.md) 新增 8 个独立标准库案例：Base64 MIME 编解码、等待计时、数组二进制追加、HTML 字符引用还原、整数最大公约数、JSON 参数移除共 6 个历史兼容性重现，以及查询参数与 HTML 转义 2 个正常对照。每例记录 CPython 官方来源、准确弃用及移除版本，并配置外部行为检查和预期输出。

首次在隔离环境的 CPython 3.10.12 上执行，基线为 6 个失败、2 个正常；保存候选回放后为 6 个通过复验的修复、2 个正常。健康对照没有候选尝试，实时推理请求数为 0。[元数据](../benchmarks/compatibility/metadata.json) 和[原始报告](../benchmarks/compatibility/evidence/replay.json) 可核查来源、输入指纹与逐例结果。

这批案例与候选由 AI 辅助自编，是公开的开发验证材料，不是第三方仓库缺陷采集、盲测集或实时模型成绩；8 个标准库例子不支持跨项目泛化结论。

## 已采集的真实项目历史文档

[三个真实项目案例集](../benchmarks/real_projects/README.md) 固定 TinyDB 3.15.2→4.8.2、more-itertools 5.0.0→9.0.0、MarkupSafe 1.1.1→2.1.5 的官方文档和源码，共 5 个迁移失败、3 个健康对照。同一检查在原版 8/8 通过；目标版为 5 个失败、3 个通过，工程参考补丁应用复查 8/8 通过。参考回放请求数为 0，真实模型成绩另见 [冻结对照证据](evidence/real-projects-20261013/README.md)。

每例都保留固定 commit、原文 URL/行号、原始文件及许可证、SHA-256、机械提取规则、原始错误、补丁与复查报告。文档补丁适用于规范化的 Markdown 副本，不能直接应用于上游 RST/docstring。案例没有用于本应用提示词调整，但可能存在于基础模型预训练中；它们是人为选择的历史迁移，不代表当前上游待修缺陷或随机项目样本。

## 后续案例

优先选择无需 GPU、外部账号或大数据集的 Python 开源项目。每例记录仓库许可、精确提交、文档位置、依赖版本、复现命令、问题证据、修复补丁与独立结果断言。开发集和最终评测集分开，保留失败与不适用案例。

一个后续候选是 [Cleanlab issue #1260](https://github.com/cleanlab/cleanlab/issues/1260)，涉及教程与依赖版本兼容性。当前尚未在本项目复现，不能计入已验证案例。
