# 验证记录

验证日期：2026-10-13。环境：Linux、Python 3.10.12、Bubblewrap 0.6.1。

## 自动验证

```sh
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

结果：104 项通过，其中 91 项核心测试、13 项真实沙箱集成测试。未开启 `EXAMPLEPROOF_SANDBOX_TESTS` 时为 91 项通过、13 项跳过。覆盖 Markdown 提取、路径约束、断言保留、失败状态、HTML 转义、模型协议模拟，以及网络隔离、源码只读、子进程限制、运行超时、输出限制、提前退出与错误输出检查。

新增回归覆盖：多轮失败反馈与重试上限、拒绝/重复/候选耗尽/服务错误的停止条件、模型断言不能新增独立证据、token 数据不完整时不虚报总量、外部检查反馈脱敏、禁代理及重定向、解包赋值和危险引用完整性、低层退出的完成凭据校验、报告硬链接保护，以及 Markdown 缩进、CRLF、无文件末尾换行和候选内嵌围栏。补丁测试对一次性副本执行 `git apply --check` 和实际应用，再重新提取或隔离执行。

推理取证回归另覆盖可调 socket 超时、原始请求/响应保存、超时与解析失败的报告、HTTP 服务错误正文、无效 Unicode、复杂 AST 拒绝，以及解析失败后仍统计服务返回的 token 消耗。GitHub workflow 配置 Python 3.10–3.14 核心矩阵和强制无跳过的 Bubblewrap 集成测试；远端运行结果以 Actions 实际状态为准。

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

## 尚未验证

- Ollama 接口目前只完成协议模拟测试，尚未运行真实模型推理。
- 案例包含一个历史兼容性问题重现和自制 SDK 场景，不是从真实项目抽样得到的成功率评测。
- 跨项目修复成功率、未见评测集、误修复率、模型成本与第三方依赖环境尚未验证。
- 通过有限行为检查不证明一般语义等价；补丁仍需人工审核。
