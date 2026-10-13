# 验证记录

验证日期：2026-10-13。环境：Linux、Python 3.10.12、Bubblewrap 0.6.1。

## 自动验证

```sh
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

结果：25 项通过，其中 17 项核心测试、8 项真实沙箱集成测试。覆盖 Markdown 提取、路径约束、断言保留、失败状态、HTML 转义、模型协议模拟，以及网络隔离、源码只读、子进程限制、运行超时、输出限制、提前退出与错误输出检查。

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

## 尚未验证

- Ollama 接口目前只完成协议模拟测试，尚未运行真实模型推理。
- 案例包含一个历史兼容性问题重现和自制 SDK 场景，不是从真实项目抽样得到的成功率评测。
- 跨项目修复成功率、未见评测集、误修复率、模型成本与第三方依赖环境尚未验证。
- 通过有限行为检查不证明一般语义等价；补丁仍需人工审核。
