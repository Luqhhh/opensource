# 待合入 docs/resources.md 的资源说明

本轮增加的运行资源仅用于隔离评测，没有增加 ExampleProof 的宿主运行时依赖。

| 资源 | 固定版本／commit | 许可 | 用途及位置 |
|---|---|---|---|
| Mistune | 0.8.4 `6470c42b2087a4649ad0437227cf7b5c570c3a91`；3.1.3 `45e4de61b8897fe5b0458d5ebe3d3cc7bde408d2` | BSD-3-Clause，原 LICENSE 随各版本保留 | `benchmarks/semantic_v2/holdout/mistune/upstream` 的公开 README、API 源码；历史正控制、目标源码和机械文档提取 |
| Werkzeug | 2.2.3 `22a254fca2ad0130adbbcbd11d3de51bcb04a08b`；3.0.6 `5eaefc3996aa5cc8c5237d8b82f1b89eed6ea624` | BSD-3-Clause，原 LICENSE 随各版本保留 | `benchmarks/semantic_v2/holdout/werkzeug/upstream` 的公开 docstring、Sphinx 入口和纯 Python 源码 |
| typing_extensions | 4.12.2 `e1250ff869e7ee5ad05170d8a4b65469f13801c3` | PSF-2.0，完整 LICENSE 保留 | Mistune 在 Python 3.10 上的 `Self` 依赖，固定源文件 `typing_extensions.py`；旧、新控制使用同一个版本 |
| MarkupSafe | 2.1.5 `fbba4acd0312826cec9cfe18371c7df07962cb65` | BSD-3-Clause，完整 LICENSE.rst 保留 | Werkzeug 的固定依赖，原生 Python fallback 的 `__init__.py`、`_native.py`；不代表新 MarkupSafe 案例 |
| Click（仅采样记录） | 7.1.2 `1784558ed7c75c65764d2a434bd9cbb206ca939d`；8.1.8 `934813e4d421071a1b3db3973c02fe2721359a6e` | BSD-3-Clause，原 LICENSE 保留 | `collection/click` 保留检查过的官方文档及 utils/termui 源码；因完整示例依赖 decorator/函数定义，未纳入修复器支持的直线代码留出集，不计入分母 |

所有被采样选中的公开代码字节及来源 URL、commit、SHA-256 在各项目 `provenance.json` 可核对。`collection` 保留重建所需上游字节和采样排除证据；后续模型输入只来自项目 `exampleproof.json` 选定的目标 `.py` 与案例，原始旧版实现、人工参考候选与外部检查不作为检索上下文。后续程序应单独验证该输入边界。
