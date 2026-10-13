# 验证记录

验证日期：2026-10-13。环境：Linux、Python 3.10.12、Bubblewrap 0.6.1。

## 自动验证

```sh
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

结果：105 项通过，其中 92 项核心测试、13 项真实沙箱集成测试。未开启 `EXAMPLEPROOF_SANDBOX_TESTS` 时为 92 项通过、13 项跳过。覆盖 Markdown 提取、路径约束、断言保留、失败状态、HTML 转义、模型协议模拟，以及网络隔离、源码只读、子进程限制、运行超时、输出限制、提前退出与错误输出检查。

新增回归覆盖：多轮失败反馈与重试上限、拒绝/重复/候选耗尽/服务错误的停止条件、模型断言不能新增独立证据、token 数据不完整时不虚报总量、外部检查反馈脱敏、禁代理及重定向、解包赋值和危险引用完整性、低层退出的完成凭据校验、报告硬链接保护，以及 Markdown 缩进、CRLF、无文件末尾换行和候选内嵌围栏。补丁测试对一次性副本执行 `git apply --check` 和实际应用，再重新提取或隔离执行。

推理取证回归另覆盖可调 socket 超时、原始请求/响应保存、超时与解析失败的报告、HTTP 服务错误正文、无效 Unicode、复杂 AST 拒绝、原始错误不重复发送，以及解析失败后仍统计服务返回的 token 消耗。GitHub workflow 配置 Python 3.10–3.14 核心矩阵和强制无跳过的 Bubblewrap 集成测试；[首轮 CI](https://github.com/Luqhhh/opensource/actions/runs/38348590555) 的 6 个任务全部成功（commit 30fed20，当时 104 项测试），后续提交以 Actions 实际状态为准。

端到端测试还将生成的统一补丁应用到临时副本，重新执行检查，确认三个修复在完整文档中生效，原始演示文件未修改。

## 演示结果

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.json --output artifacts/demo
```

| 状态 | 数量 | 含义 |
|---|---:|---|
| verified_repair | 3 | 已记录的候选补丁通过原有断言与外部行为检查 |
| checked | 1 | 原始示例通过检查 |
| skipped | 1 | 配置明确说明缺少数据集 |
| runnable_unverified | 1 | 可以运行，但未提供行为检查 |

命令退出码为 0，生成 HTML、JSON 与统一补丁。`git apply --check --directory=examples/tutorial artifacts/demo/verified.patch` 通过。每次运行可在本地重新生成报告；耗时和时间戳随环境变化。

## 多轮回放验证

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.multiround.json \
  --max-attempts 3 --output artifacts/multiround
git apply --check --directory=examples/tutorial artifacts/multiround/verified.patch
```

退出码为 0，最终状态与上述六例相同。三个失败示例共返回 4 个候选：`README.md#2` 先 `repair_failed`，再 `verified_repair`；另两个示例各一轮通过。JSON schema 2 和独立 HTML 均保留逐轮记录；最终补丁仅包含通过检查的候选，应用检查通过。回放不产生模型调用，token 计数为 null。

`python3 -m compileall -q exampleproof tests` 和 `git diff --check` 通过。演示及测试没有修改原始文档和源码。

## 真实 Ollama 推理

Ollama 0.40.3 + `qwen2.5-coder:7b`（Q4_K_M），在 RTX 4070 Laptop GPU 上对相同开发样例完成三次实时运行。原提示词的单轮和三轮上限两次运行均修复 2/3 个失败示例，另 1 例为模型主动放弃，退出码 1。调整通用提示词并删除重复堆栈后，修复 3/3 个失败示例，退出码 0；输入 token 从 2440 降至 1977（约 19%）。原始失败记录完整保留。

优化后三处补丁应用到临时副本后，重新隔离执行得到 4 个 checked、1 个 skipped、1 个 runnable_unverified，退出码 0。案例、完整请求/响应、模型摘要、耗时与对比局限见 [真实推理证据](evidence/ollama-20261013/README.md)。这是基于已见开发样例的提示词迭代，不是未见项目成功率评测；本次成功候选均为第一轮，不能据此证明多轮反馈提升。

## 安装包验证

临时 venv 使用已声明的隔离构建依赖 setuptools 84.0.0 生成 `aic_exampleproof-0.1.0-py3-none-any.whl`。包内 11 个 Python 文件与当前实现一致，无运行时依赖；从仓库外安装并验证模块入口、console script 和 `--help` 均通过。系统 Python 包未升级。wheel SHA-256：`7927a4188f97248f1bd4de19c231dadd06a9838b73b70912c3bccefcc5916e0d`；该摘要只标识本次构建，不承诺不同构建时间的 wheel 字节完全一致。

## 尚未验证

- 尚未验证更多模型、CPU 推理及长上下文项目；本次真实调用未触发后续失败重试。
- 案例包含一个历史兼容性问题重现和自制 SDK 场景，不是从真实项目抽样得到的成功率评测。
- 跨项目修复成功率、未见评测集、误修复率、模型成本与第三方依赖环境尚未验证。
- 通过有限行为检查不证明一般语义等价；补丁仍需人工审核。
