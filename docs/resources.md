# 第三方资源与 AI 使用记录

本表为持续维护的开发记录，提交参赛前补齐实际版本、来源及许可核验结果。

| 资源 | 当前用途 | 状态 |
|---|---|---|
| Python 标准库 | 提取、数据结构、隔离执行调度、报告、CLI、测试 | 不随仓库再分发解释器；需记录评测环境具体版本 |
| Bubblewrap | Linux 隔离执行 | 系统工具，非本仓库代码；[上游与许可证](https://github.com/containers/bubblewrap) |
| setuptools | 可选 Python 包构建 | 当前 CLI 可直接运行，安装打包流程尚需验证 |
| actions/checkout v7 | GitHub CI 检出源码 | [官方 v7.0.1 发布](https://github.com/actions/checkout/releases/tag/v7.0.1)，[MIT 许可证](https://github.com/actions/checkout/blob/v7/LICENSE)；仅 CI 使用 |
| actions/setup-python v7 | GitHub CI Python 3.10–3.14 核心测试矩阵 | [官方 v7.0.0 发布](https://github.com/actions/setup-python/releases/tag/v7.0.0)，[MIT 许可证](https://github.com/actions/setup-python/blob/v7/LICENSE)；仅 CI 使用 |
| Ollama API | 可选本地模型服务适配 | [接口文档](https://docs.ollama.com/api/generate)；未捆绑或下载模型，模型许可证依实际选型补充 |
| Sybil、Drift | 竞品与相关工作调研 | 未复制实现代码；[Sybil](https://sybil.readthedocs.io/en/latest/)、[Drift](https://github.com/pallaprolus/drift) |

## AI 辅助开发

2026-10-13：使用对话式 AI 协助选题、规则梳理、架构设计、代码和测试编写、示例补丁制作及文档整理。开发记录保留在仓库提交及对话中。用户需审核设计、关键代码、评测口径及参赛材料，并记录实际修改和验证过程。

随附 proposals.json 和 proposals.multiround.json 是已记录的候选补丁；后者额外包含一个刻意失败的候选，用于演示反馈后的下一轮复验。运行它们不产生模型调用，不能写成“实时 AI 自动修复评测”。真实模型名称、版本、参数、提示词、token 消耗及推理原始记录将在后续模型接入时补充。

同日后续开发：使用 AI 辅助实现有界多轮修复、证据记录、Markdown 补丁兼容性及执行完整性修复，并编写回归测试。全部新增实现使用 Python 标准库，未新增第三方运行依赖，未下载模型或新增真实开源案例。完成凭据仍与示例同进程生成，不应表述为独立验证器。
