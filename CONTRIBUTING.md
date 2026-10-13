# 参与开发与案例贡献

ExampleProof 接受功能修复、文档改进和可复现案例。先阅读 [架构与边界](docs/architecture.md)，保持运行时只依赖 Python 标准库。执行示例必须经过隔离执行器，原项目仅导出补丁供审核。

## 本地验证

```sh
python3 -m unittest discover -s tests -v
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
python3 -m exampleproof benchmark benchmarks/compatibility \
  --proposals benchmarks/compatibility/proposals.json --output artifacts/contribution-check
git diff --check
```

完整验证需要 Linux、Bubblewrap、`/usr/bin/python3` 和 Git，且系统允许创建用户和网络命名空间。不支持的环境会报告失败，不应通过跳过沙箱来宣称验证成功。评测输出目录必须新建；重复运行请更换名称。

## 提交一个案例

1. 写清原项目、许可证、精确版本或提交、文档位置和复现命令；仅根据变更说明自编的案例应标记为历史重现。
2. 用最少的选定文档和源码复现，提供 `exampleproof.json`。不要依赖自动安装或下载，外部依赖暂不支持。
3. 写出原有功能意图，配置能区分正确修复和典型错误修复的行为检查。模型新增的断言不能充当独立评测证据。
4. 需要纳入评测时提供 `metadata.json`，包含所有示例及其预期基线状态，最好加入健康对照。冻结输入后保存完整原始、修复和补丁复查结果。
5. 区分候选回放、真实模型调用、人工修复和模型辅助开发；披露失败、跳过和环境不可用。案例与提示词共同迭代的结果只能称为开发验证。

提交说明应描述问题、最终行为、实际运行的验证及剩余局限。新增第三方代码、数据、模型或构建工具时同步维护 [资源清单](docs/resources.md)。不要将用户项目、模型权重或访问凭据作为回归测试附件。

## 维护约定

JSON 报告的字段变更需要保留旧字段含义或明确提高 schema 版本；新增 CLI 行为应更新安装使用说明。合并前检查核心测试、真实沙箱测试、兼容性案例回放和补丁复查，修复失败时保留证据。模型成功率、用户反馈、上游贡献与参赛进展仅记录真实完成且可核验的结果。
