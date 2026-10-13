# 例证 · ExampleProof

开源文档示例验证与修复助手。面向 AIC 2026「AI+开源」主题赛的 **AI开发工具与开源协作** 方向。

仓库：<https://github.com/Luqhhh/opensource>

**当前状态：v0.1 原型。** 提取 Markdown 中的 Python 示例，在 Linux Bubblewrap 隔离环境中执行，接收修复候选并复验，生成 JSON、HTML 报告及统一补丁。支持本地 Ollama；没有自动下载模型。随附演示使用显式记录的候选补丁，**不代表实时模型推理结果或真实项目修复成功率**。

## 工作流程

文档与选定源码 → 示例提取 → 隔离执行 → 源码/错误信息辅助修复 → 断言完整性检查 → 行为复验 → 报告与补丁。

- 原文档和源码保持只读，补丁需由使用者审核后应用。
- 保留原始断言。移除断言、将断言移入条件分支、吞异常、提前退出等候选会被拒绝或无法通过检查。
- **运行成功不等于行为正确。** 未配置输出/行为检查且无原始顶层断言的示例只标记为可运行，其候选不进入 `verified.patch`。
- `verified_repair` 只表示通过有限检查，并非一般语义等价证明。仍需人工审核修复是否保留原任务。

## 本地运行

需要 Linux、Python 3.10+、`/usr/bin/python3` 和可创建用户/网络命名空间的 Bubblewrap。执行器没有退回宿主机执行的模式。v0.1 仅支持单进程、单线程示例，运行环境只含 Python 标准库及配置中明确列出的 `.py` 源码；第三方依赖环境将在后续版本支持。

在仓库目录运行，无需安装 Python 依赖：

```sh
# 只提取，不执行
python3 -m exampleproof scan examples/tutorial

# 检查原文档；演示内有已知错误，预期退出码 1
python3 -m exampleproof check examples/tutorial --output artifacts/check

# 使用记录的候选补丁复验；不调用模型
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.json --output artifacts/demo
```

输出为 `report.html`、`report.json` 和 `verified.patch`。HTML 为可直接打开的独立文件，不依赖网络或 JavaScript。

已有本地 Ollama 模型时，可改为实时修复（将模型名替换为本机实际安装的名称）：

```sh
python3 -m exampleproof repair examples/tutorial \
  --model YOUR_LOCAL_MODEL --output artifacts/live
```

模型只收到示例、周边文档、错误信息以及明确选择的源文件，不包含配置中的外部检查或预期输出。当前只允许回环地址的 Ollama 服务。模型接口适配有协议单元测试；是否完成真实模型测试以 [验证记录](docs/validation.md) 为准。

## 配置一个项目

在目标项目根目录创建 `exampleproof.json`。Python 示例按文档内出现顺序编号，从 `#1` 开始；可先运行 `scan` 查看编号。

```json
{
  "documents": ["README.md"],
  "source_files": ["sdk/__init__.py"],
  "timeout_seconds": 5,
  "examples": {
    "README.md#1": {
      "setup": "from sdk import double",
      "checks": "assert result == 6",
      "expected_stdout": "6\n"
    },
    "README.md#2": {"skip": "需要未提供的数据集"}
  }
}
```

`setup` 与 `checks` 由使用者明确配置。示例之间不共享状态。无法独立执行的片段应配置初始化代码或说明跳过原因。只支持普通围栏代码块；列表嵌套、缩进代码块、Notebook、跨代码块自动上下文推导暂未支持。

退出码：`0` 为没有失败或未验证修复候选（仍应阅读 skipped / runnable_unverified 计数）；`1` 为执行、检查、模型或候选失败；`2` 为配置/隔离环境错误、无示例或全部跳过。

## 测试

```sh
python3 -m unittest discover -s tests -v
# 完整执行测试，需要系统允许 Bubblewrap 创建命名空间
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

首批演示包括一个 Python 真实兼容性变更的重现、两个自制 SDK 变更案例、一个正常案例、一个上下文缺失片段及一个无行为检查的案例。它们用于验证工程流程，不能计为 6 个真实开源缺陷。[案例来源](docs/cases.md)

## 参赛资料

- [项目范围、评分对应与开发安排](docs/competition.md)
- [资源与 AI 使用记录](docs/resources.md)
- [架构与执行边界](docs/architecture.md)
- [验证记录与当前局限](docs/validation.md)

许可证：MIT。报告与参赛材料需如实披露使用的第三方组件、模型及 AI 辅助开发情况。
