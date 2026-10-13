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

## 待采集的真实案例

优先选择无需 GPU、外部账号或大数据集的 Python 开源项目。每例记录仓库许可、精确提交、文档位置、依赖版本、复现命令、问题证据、修复补丁与独立结果断言。开发集和最终评测集分开，保留失败与不适用案例。

一个后续候选是 [Cleanlab issue #1260](https://github.com/cleanlab/cleanlab/issues/1260)，涉及教程与依赖版本兼容性。当前尚未在本项目复现，不能计入已验证案例。
