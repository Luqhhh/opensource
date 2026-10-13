# 参赛材料草稿

这组材料依据用户提供的 AIC·AI+开源规则整理，所有效果表述均来自仓库现有证据。材料没有填入未经确认的参赛单位、指导信息、团队经历或外部成果。

- [作品名称与300字内简介](abstract.txt)
- [技术报告](technical-report.md)
- [3–5分钟演示脚本](demo-script.md)
- [规则对照与实际缺项](checklist.md)
- [资源与AI使用记录](../resources.md)，构建时自动作为技术报告附件

从仓库根目录运行：

```sh
python3 scripts/build_submission.py
```

构建需要本机已有 Python 3.10+、Pandoc、XeLaTeX、`pdfinfo` 与 `pdftotext`，以及 TeX Live 的 Fandol 和 Latin Modern 字体。脚本不联网、不安装软件、不执行示例代码。已测 Pandoc 2.9.2.1 / XeTeX 0.999993（TeX Live 2022/dev/Debian）；其他版本输出分页可能变化。

输出目录为 `artifacts/submission/`：`technical-report-draft.pdf` 是包含资源清单的报告；`build-manifest.json` 记录输入摘要、构建工具、字符数、页数、大小及产物摘要；`technical-report-draft.txt` 可供文本审校。脚本将报告总页数限制为15页（比规则的“正文建议15页”更保守），体积限制为10,000,000字节。它会检查简介字符数并拒绝超限，但不认证内容真实性、匿名性或权属。

`artifacts/` 被仓库忽略；源码与脚本可重建PDF，实际提交时需另行选取生成文件。字体与排版工具改变可能导致PDF字节不同，清单中的摘要只标识本次产物。

**尚未完成：** 团队人工审核与授权确认、技术报告参考大纲核对、MP4录制/验收、报名系统提交。自动构建不能代替这些环节。决赛答辩PPT按晋级通知准备。
