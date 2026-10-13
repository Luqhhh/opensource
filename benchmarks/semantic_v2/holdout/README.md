# semantic_v2 独立留出集

这是 **2 个新项目、4 个历史迁移失败和 2 个健康对照**。它们未用于本轮方法优化，所有输入与外部检查在首次模型调用前冻结。项目版本是为复现历史兼容性变化选定的，不能据此说当前上游文档有缺陷。每项补丁都是适配后的 Markdown 示例补丁，尚未作为上游 PR 提交。

| 项目 | 文档／正控制版本 | 目标版本 | 失败／健康 | 选定运行源码 |
|---|---|---|---|---|
| [Mistune](mistune/README.md) | 0.8.4 / `6470c42b2087a4649ad0437227cf7b5c570c3a91` | 3.1.3 / `45e4de61b8897fe5b0458d5ebe3d3cc7bde408d2` | 2 / 1 | 36 文件、280,266 字节，含固定 typing_extensions |
| [Werkzeug](werkzeug/README.md) | 2.2.3 / `22a254fca2ad0130adbbcbd11d3de51bcb04a08b` | 3.0.6 / `5eaefc3996aa5cc8c5237d8b82f1b89eed6ea624` | 2 / 1 | 54 文件、718,749 字节，含固定 MarkupSafe Python 回退实现 |

相同外部契约在旧版本上 **6/6 通过**；目标版本 **4 失败、2 通过**；人工参考候选回放及补丁应用复查 **6/6 通过**；4 个刻意错误候选全部被拒绝。人工参考回放不是模型效果，不计入后续模型成功率。

证据位于 [validation-final](validation-final/)：每个项目包含 `old-control`、`reference/baseline`、`reference/repair`、`reference/patched`、`negative` 和汇总 `validation.json`。冻结输入清单为 [input-inventory.json](input-inventory.json)，其 SHA-256 在 [input-inventory.sha256](input-inventory.sha256)。每个项目另有原始文件 SHA、精确上游链接、原文行号和机械提取说明。

复核原文与运行输入，无需网络：

```sh
python3 benchmarks/semantic_v2/holdout/verify_provenance.py
python3 benchmarks/semantic_v2/holdout/verify_provenance.py --runtime --output /tmp/semantic-v2-holdout-new-recheck
```

第二条要求输出目录尚不存在。上游代码始终通过 fail-closed Bubblewrap runner 执行，宿主仅解析文本、哈希与调用仓库验证器。未安装这些库到宿主解释器。

采样范围、排除理由和准备阶段失误保留于 [sampling-record.json](sampling-record.json)。这不是随机抽样或双盲：独立采集者在选定项目及案例之后，为查既有 FileProvider 接口意外看到了正在开发的通用 SYSTEM_V2 增补文字及反馈分类开头；没有看模型输出或检索实现，也没有据此替换案例。方法作者在方法锁定前没有读取这些具体题目或参考答案。后续模型对照仍须单独记录方法锁、协议锁及调用证据，不能把本目录的采集控制称为模型留出结果。

边界检查使用 evaluator 自有的固定输入和预期结果，检查复用、多输入、类型、输出格式与副作用；这些检查没有提供给模型。行为要求及需要保留的可复用名称在案例上下文显式声明。有限测试仍不能证明完整语义等价；示例与检查共享解释器，也不构成抵御恶意候选的独立安全边界。
