# 源途 · RepoPath：品牌与升级说明

中文名为「源途」，英文名为「RepoPath」，组合写作「源途 · RepoPath」。产品定位为「面向开源项目的 AI 学习工作台」，标语为「从读懂源码，到动手完成。」名称表达围绕真实开源项目，从目标出发，沿着有原文依据的任务逐步学习。

## 界面与文档

页面标题、导航品牌、页脚、导入说明和当前产品材料使用新名称。标识以路径与节点表达连续学习，沿用象牙白纸面、浅青绿和深绿主操作色。图形由项目内的内联 SVG 与 CSS 实现，使用系统字体；没有新增第三方图标、字体、图像或前端依赖。

学习任务、原文阅读和下一步行动保持界面中心。品牌图形用于识别产品和提示学习过程，不替代按钮文字、完成标志或错误反馈；窄屏保留可读名称与操作入口。

## 安装与升级

新安装包名称为 `aic-repopath`，当前 wheel 文件名为 `aic_repopath-0.1.0-py3-none-any.whl`。推荐使用 `repopath` 命令；源码目录或已安装环境也可运行 `python3 -m repopath`。

如果当前虚拟环境已安装 `aic-exampleproof`，先停止正在运行的服务，再在同一环境内按顺序升级：

```sh
python -m pip uninstall aic-exampleproof
python -m pip install /path/to/aic_repopath-0.1.0-py3-none-any.whl
repopath learn --provider none
```

也可在卸载旧包后，从当前源码目录执行 `python -m pip install .`。两种分发包共享兼容内部模块，因此不要把新旧包并存安装；若已经并存，卸载两者后重新安装新包，避免后续卸载删除共享文件。新建独立虚拟环境安装也可避免这个问题。

## 兼容约定

| 项目 | 本次处理 |
| --- | --- |
| 产品品牌 | 源途 · RepoPath |
| Python 分发包 | `aic-repopath` |
| 推荐启动入口 | `repopath`、`python3 -m repopath` |
| 兼容入口与内部实现 | 保留 `exampleproof` 命令、`python3 -m exampleproof` 和内部 `exampleproof` 包 |
| 项目配置 | 继续读取 `exampleproof.json` |
| 环境变量 | 保留 `EXAMPLEPROOF_*`；模型供应商自己的变量保持原名 |
| 学习记录 | 默认继续使用 `~/.local/share/exampleproof-learning`；自定义 `--data` 目录继续使用原路径 |
| 浏览器偏好与草稿 | 继续读取原有本地存储键，避免因更名丢失布局、草稿或阅读偏好 |
| 共享代理 | 既有数据目录、环境文件和 systemd 模板路径继续兼容 |

卸载 Python 安装包不会删除上述学习数据目录。已有用户应以原 `--data` 参数重启服务；更名不重建学习路线，也不修改笔记、进度或历史模型调用记录。

## 历史材料

历史版本中的「例证 · ExampleProof」、旧 wheel 名称、文件摘要、冻结协议、评测记录和许可证归属保留原样。当前文字稿与新图采用新名称；[主页](submission/figures/repopath-home.png)来自关闭 AI 的本机应用，[工作台](submission/figures/repopath-workspace.png)预览来自合成浏览器夹具，没有真实模型调用，不属于用户研究。架构与流程图保留自主 SVG 源文件。旧截图和录像仍属于原版本的实际记录，新品牌视频仍需重新录制核验。品牌更新不代表新增真实模型结果、用户研究结论或参赛结果。
