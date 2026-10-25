# 源途 · RepoPath 参赛材料

当前材料围绕开源项目学习流程与真实用户体验。团队忧郁蜂蜜水，编号AIC-2026-19649058，成员路庆浩、肖金诺。

- [技术报告](technical-report.md)：场景、架构、实现、自研边界与开放成果。
- [作品简介](abstract.txt)：名称与300字以内简介。
- [演示脚本](demo-script.md)：新品牌录制稿与旧版成片索引；原视频信息见原交付清单。
- [资源清单附件](resource-list.md)：提交版清单；详细来源见docs/resources.md。
- [答辩稿](defense-slides.md)：供决赛准备的PDF幻灯片源稿。
- [材料核对表](checklist.md)。
- [真实读者试用](../user-study/README.md)：受访者说明、推荐项目、观察指标与空白记录表。

从仓库根目录运行 `python3 scripts/build_submission.py --output /tmp/repopath-report`。需要已有Pandoc、XeLaTeX与Poppler；不联网、不调用模型、不执行项目示例。报告资源附件自动合并，清单记录页数、体积和摘要。

答辩 PDF 可从本目录单独构建（输出到仓库外）：

```sh
cd docs/submission
pandoc defense-slides.md --standalone --to=beamer --pdf-engine=xelatex \
  --pdf-engine-opt=-no-shell-escape --variable=documentclass:ctexbeamer \
  --variable=classoption:fontset=fandol --variable=aspectratio:169 \
  --include-in-header slides-header.tex --output /tmp/repopath-defense-slides.pdf
```

当前主页截图 `figures/repopath-home.png` 来自关闭 AI 的本机应用导入页；工作台截图 `figures/repopath-workspace.png` 来自合成浏览器夹具，使用合成项目。两者均无真实模型调用，不属于用户研究。架构图与流程图由同目录的 `repopath-architecture.svg`、`repopath-workflow.svg` 自主源图生成对应 PNG。实际用户体验在收到匿名记录后更新，未填写的反馈保持空白。

当前文字材料和所引用的新图采用「源途 · RepoPath」，PDF 可按上述命令构建。旧截图、录像和已交付文件保留原版本，可能显示旧品牌「例证 · ExampleProof」；新品牌视频仍需重新录制核验。修改源稿或完成本机构建不代表已更新外部交付文件或完成参赛提交。
