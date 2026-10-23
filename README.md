# 例证 · ExampleProof

**把开源项目原文变成可以逐步完成的学习任务。** 导入公开 GitHub 仓库或源码 ZIP，填写学习目标，在同一个工作台查看路线、阅读原文与源码、提问排错、记录笔记，并在下次打开时继续学习。

面向 AIC 2026「AI+开源」的 **AI开发工具与开源协作** 方向。公开仓库：<https://github.com/Luqhhh/opensource>。自主代码采用MIT；第三方材料保留原许可证。

## 快速开始

需要Python 3.10+。Windows可将 `python3` 换成 `python`：

```sh
git clone https://github.com/Luqhhh/opensource.git
cd opensource
python3 -m venv .venv
# Linux / WSL
. .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install .
exampleproof learn --provider none
```

打开 <http://127.0.0.1:8765/>。上传项目ZIP或填写公开仓库地址，输入具体目标，例如“用TinyDB保存两条记录，按条件查询并验证重新打开后仍有数据”。基础路线无需模型，支持原文阅读、笔记、进度和导出。

在源码目录也可直接运行 `python3 -m exampleproof learn --provider none`，无需安装第三方Python运行依赖。

## AI学习支持

在启动服务的终端配置自己的 `DEEPSEEK_API_KEY` 后运行 `exampleproof learn`。本地模型使用：

```sh
exampleproof learn --provider ollama --model YOUR_LOCAL_MODEL
```

配置云端模型后，导入页的“自动用AI细化学习路线”会使用目标和经脱敏的项目片段。可取消勾选，仅生成基础路线。问答、排错和重新规划各自显示发送预览，确认后才发出请求。不要把密钥写进项目、目标或截图。

模型失败时保留基础路线和错误记录。引用帮助核对回答，但引用存在不代表回答正确；AI反馈和自行勾选的进度不证明已经掌握知识。

## 一次学习如何进行

1. **说明目标**：导入项目，选择基础水平，说清想完成的事情。
2. **开始任务**：查看“现在做”、操作位置和完成标志，打开对应原文。
3. **理解与排错**：解释片段、提问或粘贴实际报错，回答和引用保存在任务旁。
4. **记录与调整**：写笔记、做练习、拆分或跳过任务；调整可撤销。
5. **继续学习**：保存进度，关闭后重开，恢复学习记录；需要时导出指南或记录。

可选Python运行检查需要Linux、Bubblewrap和 `/usr/bin/python3`。只执行用户明确提交的完整示例，项目副本只读、无网络、最多5秒，不安装依赖；沙箱不可用时停止。每次运行独立，文件和变量不跨运行保留。阅读与问答不依赖沙箱。

## 用户体验与开放复用

效果验证围绕真实读者任务和访谈展开：[试用方案、项目与指标](docs/user-study/README.md)。受访者无需填写模型评分表。卡点、完成情况、求助、耗时与主观体验由实际记录产生，未回收的数据保持空白。

- [受访者说明与任务卡](docs/user-study/participant-guide.md)
- [主持人手册](docs/user-study/facilitator-guide.md)
- [安装复现与维护计划](docs/reproduction.md)
- [完整学习入口说明](docs/learning-app.md)
- [技术报告与演示材料](docs/submission/README.md)
- [第三方资源与自主边界](docs/resources.md)

## 维护者工具

保留教程静态分析、受限任务验证和补丁导出，不自动改写原项目：

```sh
exampleproof doctor --json
exampleproof analyze /path/to/project --static --output /tmp/exampleproof-analysis
exampleproof task-init --help
exampleproof task-check --help
exampleproof task-improve --help
```

模型候选与调用者冻结的检查分开；既有断言和预期输出受到保护。通过有限检查的补丁仍需人工审阅。高级命令见 [教程分析](docs/next-stage.md)、[任务验证](docs/task-improvement.md)。

## 开发与边界

```sh
python3 -m unittest discover -s tests -v
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
node tests/code_highlight.test.cjs
```

Python运行依赖为空，前端为本地HTML/CSS/JavaScript。Node仅用于开发检查。打包按实际源码和前端资源逐字节核对wheel、sdist与安装目录，并在仓库外启动学习入口。

服务只监听本机，适合单用户，没有公网账号隔离。项目输入有文件数、体积和类型限制；复杂文档渲染与跨语言语义导航有限。运行检查不支持联网安装、编译扩展和长任务。

工程测试、自动操作演示、实时模型调用和读者观察分别记录。历史原始记录保留原样；当前介绍以学习流程与用户体验为主。反馈使用 [Issues](https://github.com/Luqhhh/opensource/issues)，删除私人内容和凭据。开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。
