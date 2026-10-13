# Ollama 真实推理验证 · 2026-10-13

本目录保存真实本地模型调用的请求、响应、补丁和补丁应用后的复查结果。所有候选均由 Ollama 当次生成，未读入 proposals.json，也未人工改写候选。开发样例包含一个标准库历史兼容性重现、两个自制 SDK 错误，以及正常/跳过/无行为检查三个对照。它们不是未见真实项目评测集。

## 环境与来源

- Ollama 0.40.3，官方 Linux amd64 发行包 SHA-256：`ce6f8b671a699bf1ebafb28d60dbbabf4f37b30b499145fa308a8ba72de021d6`。
- 模型：[qwen2.5-coder:7b](https://ollama.com/library/qwen2.5-coder:7b)，7.6B、Q4_K_M、Apache-2.0；manifest SHA-256：`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`。
- 主模型文件 SHA-256：`60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463`。安装包、manifest 和每个模型 layer 均核验摘要；模型权重保存在仓库外，不随本仓库再分发。
- 本机内置 `ollama pull` 在 manifest 阶段超时，改用 curl 从同一官方 registry 下载并校验 manifest/layers 后，由 Ollama 加载推理。
- NVIDIA GeForce RTX 4070 Laptop GPU，8 GB；Python 3.10.12；Bubblewrap 0.6.1。上下文 8192，单并行请求，temperature 0，非流式 JSON，socket 超时 180 秒。
- 详细环境、基线 commit 与优化后 Python 源码摘要见 [environment.json](environment.json)。请求中的完整提示词与选定源码见各轮 `inference_evidence.request`；原始解析后响应见 `inference_evidence.response`。

## 结果

| 运行 | 每例轮数上限 | 失败示例修复 | 模型请求 | 输入 token | 输出 token | 请求累计耗时 |
|---|---:|---:|---:|---:|---:|---:|
| single：原提示词 | 1 | 2/3 | 3 | 2440 | 248 | 12.9232 秒 |
| multiround：原提示词 | 3 | 2/3 | 3 | 2440 | 248 | 7.4572 秒 |
| optimized：优化提示词 | 3 | 3/3 | 3 | 1977 | 273 | 9.5299 秒 |

原提示词下，模型对 `collections.Mapping` 示例返回空代码并解释 import 错误，因此标记 `declined`，两次运行退出码均为 1。放弃按设计直接停止；仅提高轮数上限没有带来提升。其他两例修改 SDK 参数名和属性访问，均通过原断言及外部检查。

观察基线后，修改了通用提示词：要求返回完整代码块，明确可用依赖范围，并允许标准库兼容性修复使用已知的标准库 API；同时从请求中删除重复的原始错误堆栈。没有向提示词注入本例正确导入、候选补丁或外部检查。优化后三例各在第一轮通过，输入 token 减少 463（约 19%）。这些调整基于本开发集，不能据此宣称未见案例泛化提升或多轮反馈优于单轮。

首次运行包含冷启动；后续运行受模型缓存影响，输出长度也不同。本记录不支持推理速度提升或稳定成功率结论。真实调用没有触发后续失败重试，重试分支另由协议模拟与记录候选的沙箱测试覆盖。

## 补丁复查

三次运行的补丁均通过 `git apply --check`，并实际应用到一次性项目副本后重新执行 `check`。原文档、源码及配置逐字节保持不变。

- 基线两次：仍有 1 个失败示例，3 个 checked、1 个 skipped、1 个 runnable_unverified，复查退出码 1。
- 优化后：4 个 checked、1 个 skipped、1 个 runnable_unverified，无失败，复查退出码 0。
- 正常、跳过及无行为检查的对照均未触发模型请求。

每个子目录包含 `report.json`、`verified.patch` 和 `patched-check.json`。`single` / `multiround` 使用 commit `30fed20`；`optimized` 的实现摘要在环境记录中，可对照本次提交源码。

## 重跑当前版本

按 [Ollama 安装说明](https://docs.ollama.com/linux) 安装服务并准备上述模型。启动服务时使用 `OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_NUM_PARALLEL=1 ollama serve`，在另一个终端运行：

```sh
python3 -m exampleproof repair examples/tutorial \
  --model qwen2.5-coder:7b --model-timeout 180 \
  --max-attempts 3 --output artifacts/live-recheck
git apply --check --directory=examples/tutorial artifacts/live-recheck/verified.patch
```

核对模型 manifest 摘要；同名 tag、运行环境和推理实现变化均可能改变结果。原提示词的基线需在 `30fed20` 的独立检出中运行，候选回放不能替代新的实时推理。
