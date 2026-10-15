import argparse
import json
import math
from pathlib import Path
import sys

from . import __version__
from .pipeline import exit_code, read_project, run_project
from .providers import FileProvider, OllamaProvider, SemanticOllamaProvider
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
    parser = argparse.ArgumentParser(prog="exampleproof", description="例证：验证 Python 文档示例，复验修复补丁。")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="检查隔离执行环境，不调用模型")
    doctor.add_argument("--json", action="store_true", help="输出结构化环境检查结果")
    scan = commands.add_parser("scan", help="只提取示例，不执行")
    scan.add_argument("project", type=Path)
    for name in ("check", "repair", "benchmark"):
        command = commands.add_parser(name, help={"check": "隔离执行示例", "repair": "提出并复验修复",
                                                  "benchmark": "按 metadata.json 评测并在临时副本应用补丁复查"}[name])
        command.add_argument("project", type=Path)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--quiet", action="store_true", help="关闭进度提示，保留结果与错误")
        if name in {"repair", "benchmark"}:
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument("--proposals", type=Path, help="导入候选补丁 JSON；非实时模型推理")
            group.add_argument("--model", help="本机 Ollama 中已安装的模型名称")
            command.add_argument("--endpoint", default="http://127.0.0.1:11434")
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
        if getattr(args, "proposals", None) and args.repair_policy != "legacy":
            raise ValueError("--repair-policy applies only to live model calls, not candidate replay")
        model_provider = SemanticOllamaProvider if getattr(args, "repair_policy", "legacy") == "semantic-v2" else OllamaProvider
        if args.command == "scan":
            _, _, _, examples = read_project(args.project)
            print(json.dumps([{"id": x.id, "line": x.start_line, "code": x.code} for x in examples], ensure_ascii=False, indent=2))
            return 0
        root = args.project.resolve()
        output = args.output.resolve()
        progress = None if args.quiet else show_progress
        if args.command == "benchmark":
            from .benchmark import run_benchmark
            provider = FileProvider(args.proposals) if args.proposals else model_provider(
                args.model, args.endpoint, timeout=args.model_timeout)
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
            provider = FileProvider(args.proposals) if args.proposals else model_provider(
                args.model, args.endpoint, timeout=args.model_timeout)
        report, patch = run_project(root, provider, max_attempts=getattr(args, "max_attempts", 1), progress=progress)
        write_report(output, report, patch)
        print(json.dumps(report["summary"], ensure_ascii=False))
        print(f"报告：{output / 'report.html'}")
        print(f"通过检查的补丁：{output / 'verified.patch'}")
        return exit_code(report)
    except (ValueError, OSError, SyntaxError) as exc:
        print(f"exampleproof: {exc}", file=sys.stderr)
        return 2
