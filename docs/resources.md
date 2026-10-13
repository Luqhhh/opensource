# 第三方资源与 AI 使用记录

本表为持续维护的开发记录，提交参赛前补齐实际版本、来源及许可核验结果。

| 资源 | 当前用途 | 状态 |
|---|---|---|
| Python 标准库 | 提取、数据结构、隔离执行调度、报告、CLI、测试 | 不随仓库再分发解释器；需记录评测环境具体版本 |
| Bubblewrap | Linux 隔离执行 | 系统工具，非本仓库代码；[上游与许可证](https://github.com/containers/bubblewrap) |
| setuptools | 可选 Python 包构建 | 当前 CLI 可直接运行，安装打包流程尚需验证 |
| Ollama API | 可选本地模型服务适配 | [接口文档](https://docs.ollama.com/api/generate)；未捆绑或下载模型，模型许可证依实际选型补充 |
| Sybil、Drift | 竞品与相关工作调研 | 未复制实现代码；[Sybil](https://sybil.readthedocs.io/en/latest/)、[Drift](https://github.com/pallaprolus/drift) |

## AI 辅助开发

2026-10-13：使用对话式 AI 协助选题、规则梳理、架构设计、代码和测试编写、示例补丁制作及文档整理。开发记录保留在仓库提交及对话中。用户需审核设计、关键代码、评测口径及参赛材料，并记录实际修改和验证过程。

随附 proposals.json 是已记录的候选补丁。运行它不产生模型调用，不能写成“实时 AI 自动修复评测”。真实模型名称、版本、参数、提示词、token 消耗及推理原始记录将在后续模型接入时补充。
