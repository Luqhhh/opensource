import argparse
import json
import math
from pathlib import Path
import sys

from . import __version__
from .pipeline import exit_code, read_project, run_project
from .providers import DeepSeekProvider, FileProvider, OllamaProvider, SemanticOllamaProvider
from .report import LABELS, write_report
from .runner import environment_report


def show_progress(event):
    """Send progress to stderr without mixing it with existing stdout results."""
    stage = event["stage"]
    if stage == "phase_start":
        label = {"baseline": "检查原始示例", "repair": "修复与复验", "patched": "应用补丁后复查"}[event["phase"]]
        message = f"评测阶段：{label}"
    elif stage == "project_start":
        message = f"共发现 {event['total']} 个示例。"
    elif stage == "example_start":
        message = f"[{event['index']}/{event['total']}] {event['example_id']}：开始检查"
    elif stage == "attempt_start":
        message = f"  第 {event['attempt']}/{event['max_attempts']} 轮：获取修复候选"
    elif stage == "attempt_complete":
        message = f"  第 {event['attempt']} 轮：{LABELS.get(event['status'], event['status'])}"
    elif stage == "example_complete":
        message = f"  结果：{LABELS.get(event['status'], event['status'])}"
    else:
        return
    print(message, file=sys.stderr, flush=True)


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(prog="exampleproof", description="例证：分析开源项目教程质量，验证 Python 示例与修复。")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="检查隔离执行环境，不调用模型")
    doctor.add_argument("--json", action="store_true", help="输出结构化环境检查结果")
    analyze = commands.add_parser("analyze", help="分析完整项目教程；默认 Flash＋规则检索，不执行代码")
    analyze.add_argument("project", help="GitHub URL、OWNER/REPO 或本地项目目录")
    analyze.add_argument("--ref", help="GitHub 分支、标签或提交；默认仓库 HEAD")
    analyze.add_argument("--output", type=Path, required=True, help="必须是尚不存在的新目录")
    analysis_mode = analyze.add_mutually_exclusive_group()
    analysis_mode.add_argument("--provider", choices=("deepseek", "ollama"),
                               help="默认 deepseek；读取 DEEPSEEK_API_KEY，可切换本地 ollama")
    analysis_mode.add_argument("--static", action="store_true", help="仅静态检查；无需密钥，不调用模型")
    analyze.add_argument("--model", help="DeepSeek 默认 deepseek-flash；Ollama 需指定本地模型")
    analyze.add_argument("--endpoint", help="官方 DeepSeek HTTPS 或本地 Ollama 回环地址")
    analyze.add_argument("--model-timeout", type=positive_seconds, default=60)
    analyze.add_argument("--context-strategy", choices=("lexical", "ai"), default="lexical",
                         help="默认 lexical（AST＋关键词规则检索）；ai 额外调用模型选择上下文")
    analyze.add_argument("--context-chars", type=int, default=12000, help="最终证据字符预算 2000..48000")
    compare = commands.add_parser("compare", help="固定同一项目快照，对照两种上下文策略（最多三次模型请求）")
    compare.add_argument("project", help="GitHub URL、OWNER/REPO 或本地项目目录")
    compare.add_argument("--ref")
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--provider", choices=("deepseek", "ollama"), default="deepseek",
                         help="默认 deepseek；可切换本地 ollama")
    compare.add_argument("--model", help="DeepSeek 默认 deepseek-flash；Ollama 需指定模型")
    compare.add_argument("--endpoint")
    compare.add_argument("--model-timeout", type=positive_seconds, default=60)
    compare.add_argument("--context-chars", type=int, default=12000)
    audit = commands.add_parser("compare-audit", help="核对已保存对照的快照、代码及用量；不调用模型")
    audit.add_argument("output", type=Path)
    scan = commands.add_parser("scan", help="只提取示例，不执行")
    scan.add_argument("project", type=Path)
    for name in ("check", "repair", "benchmark"):
        command = commands.add_parser(name, help={"check": "隔离执行示例", "repair": "提出并复验修复",
                                                  "benchmark": "按 metadata.json 评测并在临时副本应用补丁复查"}[name])
        command.add_argument("project", type=Path)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--quiet", action="store_true", help="关闭进度提示，保留结果与错误")
        if name in {"repair", "benchmark"}:
            group = command.add_mutually_exclusive_group()
            group.add_argument("--proposals", type=Path, help="导入候选补丁 JSON；非实时模型推理")
            group.add_argument("--model", help="模型名；Ollama 必填，DeepSeek 默认 deepseek-flash")
            command.add_argument("--provider", choices=("ollama", "deepseek"), default="ollama")
            command.add_argument("--endpoint", help="模型 API 地址；默认使用所选服务地址")
            command.add_argument("--repair-policy", choices=("legacy", "semantic-v2"), default="legacy",
                                 help="模型修复策略；semantic-v2 使用 6000 字符源码检索和分类反馈（默认 legacy）")
            command.add_argument("--model-timeout", type=positive_seconds, default=60,
                                 help="Ollama 连接/读取空闲超时秒数（默认 60），冷启动模型可调高")
            command.add_argument("--max-attempts", type=int, choices=range(1, 6), default=1,
                                 help="每个失败示例的候选轮数上限（1–5，默认 1）；失败反馈用于下一轮")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = environment_report()
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print("隔离执行环境可用。" if report["ready"] else "隔离执行环境尚未就绪。")
                for check in report["checks"]:
                    print(f"[{'通过' if check['ready'] else '待处理'}] {check['name']}：{check['detail']}")
                    if not check["ready"]:
                        print(f"  建议：{check['hint']}")
                print("帮助与 scan 可在 Windows 使用；执行示例需要 Linux 隔离环境。")
            return 0 if report["ready"] else 2
        if args.command == "compare-audit":
            from .tutorial_study import audit_comparison
            result = audit_comparison(args.output)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["status"] == "passed" else 2
        if args.command in {"analyze", "compare"}:
            from .model_api import JSONClient
            from .project_input import project_input
            from .tutorial import analyze_project, write_analysis
            if args.output.exists() or args.output.is_symlink():
                raise ValueError("Analysis output must be a new directory")
            static = getattr(args, "static", False)
            if static and (args.model or args.endpoint or args.context_strategy == "ai"):
                raise ValueError("--static cannot be combined with --model, --endpoint or --context-strategy ai")
            if not 2000 <= args.context_chars <= 48000:
                raise ValueError("Context budget must be 2000..48000 characters")
            provider = args.provider or "deepseek"
            client = None if static else JSONClient(
                provider, args.model or ("deepseek-flash" if provider == "deepseek" else ""),
                endpoint=args.endpoint, timeout=args.model_timeout)
            with project_input(args.project, ref=args.ref) as (root, provenance):
                # Keep generated artifacts entirely outside analyzed input trees.
                if args.output.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Analysis output must be outside the input project")
                if args.command == "compare":
                    from .tutorial_study import run_comparison
                    result = run_comparison(root, provenance, args.output, client, context_chars=args.context_chars)
                    print(f"上下文对照报告：{args.output / 'comparison.html'}")
                    return 0 if result["run_status"] == "completed" else 2
                report = analyze_project(root, provenance, client=client,
                                         strategy=args.context_strategy, context_chars=args.context_chars)
            write_analysis(args.output, report)
            print(f"教程质量报告：{args.output / 'analysis.html'}")
            print(f"发现 {len(report['findings'])} 项；项目代码未执行。")
            return 2 if any(c["status"] == "error" for c in report["calls"]) or report["warnings"] else 0
        if getattr(args, "proposals", None) and args.repair_policy != "legacy":
            raise ValueError("--repair-policy applies only to live model calls, not candidate replay")
        if args.command in {"repair", "benchmark"}:
            if args.proposals and (args.provider != "ollama" or args.endpoint):
                raise ValueError("--provider/--endpoint cannot be combined with candidate replay")
            if not args.proposals and not args.model and args.provider == "ollama":
                raise ValueError("Select --model, --proposals or --provider deepseek")
        def create_provider():
            if args.proposals:
                return FileProvider(args.proposals)
            if args.provider == "deepseek":
                return DeepSeekProvider(args.model or "deepseek-flash", args.endpoint or "https://api.deepseek.com",
                                        timeout=args.model_timeout, semantic=args.repair_policy == "semantic-v2")
            model_provider = SemanticOllamaProvider if args.repair_policy == "semantic-v2" else OllamaProvider
            return model_provider(args.model, args.endpoint or "http://127.0.0.1:11434", timeout=args.model_timeout)
        if args.command == "scan":
            _, _, _, examples = read_project(args.project)
            print(json.dumps([{"id": x.id, "line": x.start_line, "code": x.code} for x in examples], ensure_ascii=False, indent=2))
            return 0
        root = args.project.resolve()
        output = args.output.resolve()
        progress = None if args.quiet else show_progress
        if args.command == "benchmark":
            from .benchmark import run_benchmark
            provider = create_provider()
            summary, code = run_benchmark(root, output, provider, max_attempts=args.max_attempts, progress=progress)
            print(json.dumps(summary["metrics"], ensure_ascii=False))
            print(f"评测证据：{output / 'benchmark.json'}")
            return code
        # Outputs must not overwrite selected input files. Report directories
        # are otherwise allowed within the project for ordinary CI usage.
        config, _, _, _ = read_project(root)
        inputs = {root / p for p in config["documents"] + config["source_files"] + ["exampleproof.json"]}
        if args.command == "repair" and args.proposals:
            inputs.add(args.proposals.resolve())
        for name in ("report.json", "report.html", "verified.patch"):
            destination = output / name
            if destination in inputs or destination.is_symlink():
                raise ValueError(f"Output would overwrite an input or symlink: {destination}")
        provider = None
        if args.command == "repair":
            provider = create_provider()
        report, patch = run_project(root, provider, max_attempts=getattr(args, "max_attempts", 1), progress=progress)
        write_report(output, report, patch)
        print(json.dumps(report["summary"], ensure_ascii=False))
        print(f"报告：{output / 'report.html'}")
        print(f"通过检查的补丁：{output / 'verified.patch'}")
        return exit_code(report)
    except (ValueError, OSError, SyntaxError) as exc:
        print(f"exampleproof: {exc}", file=sys.stderr)
        return 2
