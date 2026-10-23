# 开源及第三方资源使用清单

本表对应当前学习工作台和交付材料。自主代码采用MIT；复制的第三方文件继续遵守原许可。开发使用的服务与作品运行时调用的模型分开列明。完整来源、历史复制文件和许可文本见仓库 `docs/resources.md` 及各材料中的LICENSE/NOTICE。

## 运行资源与可选服务

| 资源与类型 | 版本与来源 | 许可或授权 | 用法、义务与自主边界 |
| --- | --- | --- | --- |
| Python/CPython，运行时 | Python 3.10+；python.org | PSF License及发行包附属许可 | 使用标准库实现服务、索引和记录；不改写解释器；随包保留复制资源的归属 |
| Bubblewrap，隔离工具 | 本次0.6.1；github.com/containers/bubblewrap | LGPL-2.0-or-later，依上游声明 | 可选执行边界；调用系统工具，不捆绑二进制，不作为自研 |
| DeepSeek API，云服务 | 配置模型deepseek-flash；api-docs.deepseek.com | 账户适用服务条款，不等同开源权重许可 | 路线与问答，需用户自行配置服务；发送内容经选择与预览；不分发权重或密钥 |
| Ollama，本地服务 | 用户自行安装；ollama.com | MIT；模型另按自身许可 | 可选本地模型传输；不随作品安装或分发模型 |
| Qwen2.5-Coder，既有可选模型 | 7B-Instruct；Qwen官方发布 | Apache-2.0 | 用户自行选择；权重不纳入源码和桌面包，保留模型许可边界 |
| GitHub，托管与输入服务 | 在线服务；github.com | GitHub服务条款，仓库内容另看许可 | 公开成果、源码下载和CI；不公开账号凭据 |

## 学习材料与既有复制资源

| 资源 | 固定版本或来源 | 许可 | 使用与义务 |
| --- | --- | --- | --- |
| TinyDB源码与文档 | [msiemens/tinydb，edff96ae](https://github.com/msiemens/tinydb/tree/edff96aeb2616402e9489d46e90a592c05565621) | MIT | 桌面试用ZIP、实际界面演示；保留LICENSE和作者版权，上游代码不计自研 |
| Schedule源码与文档 | [dbader/schedule，82a43db1](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651) | MIT | 固定试用ZIP，保留LICENSE.txt；不修改上游文件 |
| CPython API索引及归属 | CPython 3.10.12固定资源；python.org | PSF及原文件许可 | 既有维护者工具使用；安装包保留CPython许可与stdlib-attribution |
| 仓库中既有第三方案例材料 | TinyDB、more-itertools、MarkupSafe、Mistune、Werkzeug、six、typing_extensions等；精确版本见各provenance | MIT、BSD、PSF等原许可，逐项见详细清单 | 保留源文件、LICENSE/NOTICE及来源；不把第三方代码统标为团队MIT成果 |

## 开发与材料制作工具

| 资源 | 版本或来源 | 许可与使用方式 |
| --- | --- | --- |
| Codex，AI开发辅助服务 | 本次开发会话；具体服务记录由账户保存 | 账户适用服务条款；辅助实现、测试、文档和演示。AI生成内容需核查，不当然视为独占原创 |
| 图像生成概念参考 | 既有工作台视觉方向概念图 | 仅供设计参考，未随产品分发；当前页面、图示为自编CSS/图形 |
| setuptools、build、wheel | 84.2.1、1.6.1、0.48.0；PyPI官方包 | MIT；只在独立构建环境使用，不增加运行依赖 |
| Pandoc、XeLaTeX/TeX Live | 本机版本见build-manifest；pandoc.org、tug.org | Pandoc GPL-2.0-or-later，XeTeX及TeX组件各自许可；仅调用工具生成材料 |
| Fandol、Latin Modern字体 | 系统字体；CTAN | Fandol GPL及字体嵌入例外、Latin Modern GUST Font License；PDF嵌入字形，不另发字体 |
| Poppler，PDF核查 | 本机pdfinfo/pdftotext；poppler.freedesktop.org | 系统发行包许可；核查页数、文本和渲染，不捆绑工具 |
| websocket-client、Pillow | 1.9.2、12.2.0；PyPI及官方发布 | Apache-2.0、MIT-CMU及包内附属声明；仓库外自动化与自编图示，不作为运行依赖 |
| FFmpeg、Microsoft Edge、System.Speech | FFmpeg 4.4；已有系统浏览器与Microsoft Huihui zh-CN语音 | FFmpeg本次GPL构建，仅调用不分发；浏览器与系统语音依适用条款。自动画面剪辑与合成旁白，不是受访者录像 |
| GitHub Actions官方组件 | checkout@v7、setup-python@v7；解析提交以CI为准 | MIT及GitHub服务条款；自编工作流调用，不复制组件实现 |

公开范围为团队有权提供的源码、文档、图示和工程记录。受访者联系方式、原始私人录屏、密钥及模型权重不公开。用户体验引用按参与者选择处理。
