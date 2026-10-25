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


def main(argv=None, *, prog="exampleproof"):
    # Start the CLI deadline before input acquisition/indexing as well as HTTP.
    from .tutorial_budget import deadline
    preflight = argparse.ArgumentParser(prog=prog, add_help=False)
    preflight.add_argument("--deadline-seconds", type=positive_seconds)
    known, _ = preflight.parse_known_args(argv)
    try:
        with deadline(known.deadline_seconds):
            return _main(argv, prog=prog)
    except ValueError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return 2


def _main(argv=None, *, prog="exampleproof"):
    parser = argparse.ArgumentParser(prog=prog, description="源途 · RepoPath：面向开源项目的 AI 学习工作台。按目标逐步阅读、实践与记录，也提供教程分析和受限示例验证。")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    learn = commands.add_parser("learn", help="启动本机项目学习入口：上传 ZIP、导入 GitHub、生成入门路线")
    learn.add_argument("--port", type=int, default=8765)
    learn.add_argument("--data", type=Path, default=Path.home() / ".local/share/exampleproof-learning")
    learn.add_argument("--provider", choices=("auto", "none", "deepseek", "ollama", "gateway"), default="auto")
    learn.add_argument("--model")
    learn.add_argument("--gateway-url", help="维护者共享服务 HTTPS 地址；也可设置 EXAMPLEPROOF_GATEWAY_URL")
    gateway = commands.add_parser("gateway", help="启动共享 AI 代理，由维护者统一提供调用额度")
    gateway.add_argument("--port", type=int, default=8787)
    gateway.add_argument("--data", type=Path, default=Path.home()/".local/share/exampleproof-gateway")
    gateway.add_argument("--model", default="deepseek-flash")
    gateway.add_argument("--public", action="store_true", help="显式开放公共额度，不要求邀请码")
    gateway.add_argument("--daily-limit", type=int, default=50)
    gateway.add_argument("--hourly-limit", type=int, default=10)
    gateway.add_argument("--total-limit", type=int, default=500)
    gateway.add_argument("--concurrency", type=int, default=2)
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
    analyze.add_argument("--context-strategy", choices=("lexical", "ai", "iterative"), default="lexical",
                         help="lexical 规则检索；ai 一次选择；iterative 按证据缺口继续检索")
    analyze.add_argument("--task", help="iterative 的具体读者任务，最多 2000 字符")
    analyze.add_argument("--max-retrieval-rounds", type=int, choices=range(1, 6), default=3,
                         help="iterative 最多补充检索轮数（1–5，默认 3）；模型请求最多轮数＋1")
    analyze.add_argument("--max-total-tokens", type=int, help="累计输入＋输出 token 停止阈值；单次请求可能超出")
    analyze.add_argument("--deadline-seconds", type=positive_seconds, help="分析端到端硬时限；需要 POSIX 主线程")
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
    for command in (analyze, compare):
        command.add_argument("--include-tests", action="store_true", help="将普通 test/tests 目录纳入教程证据")
        command.add_argument("--include-path", action="append", default=[], help="显式纳入相对路径或 glob；可重复")
        command.add_argument("--exclude-path", action="append", default=[], help="排除相对路径或 glob；可重复，优先于纳入")
        command.add_argument("--evidence-requirements", type=Path, help="冻结快照的必要证据标注 JSON；仅测覆盖")
        command.add_argument("--cloud-review", type=Path, help="云端清单 JSON；默认 OUTPUT-cloud-review.json")
        command.add_argument("--approve-cloud", help="审阅清单后显式传入其中 sha256，允许发送所列脱敏证据")
        command.add_argument("--redact-values", type=Path, help="额外脱敏值的 JSON 字符串数组；仅在本地读取")
    audit = commands.add_parser("compare-audit", help="核对已保存对照的快照、代码及用量；不调用模型")
    audit.add_argument("output", type=Path)
    task_check = commands.add_parser("task-check", help="按冻结的读者任务验证明确候选，并导出待审阅文档补丁")
    task_check.add_argument("project", type=Path)
    task_check.add_argument("--contract", type=Path, required=True)
    task_check.add_argument("--candidate", type=Path, required=True)
    task_check.add_argument("--output", type=Path, required=True)
    improve_parser = commands.add_parser("task-improve", help="把已有建议转换为候选，按冻结任务验证并导出补丁")
    improve_parser.add_argument("project", type=Path)
    improve_parser.add_argument("--analysis", type=Path, required=True)
    finding_group = improve_parser.add_mutually_exclusive_group(required=True)
    finding_group.add_argument("--finding", type=int, help="兼容旧记录的从 0 开始索引；优先使用稳定 ID")
    finding_group.add_argument("--finding-id", help="analysis.json 中 f- 开头的稳定建议 ID")
    improve_parser.add_argument("--contract", type=Path, required=True)
    improve_parser.add_argument("--output", type=Path, required=True)
    improve_parser.add_argument("--proposal", type=Path, help="回放 original/replacement/rationale JSON；不调用模型")
    improve_parser.add_argument("--provider", choices=("deepseek", "ollama"), default="deepseek")
    improve_parser.add_argument("--model")
    improve_parser.add_argument("--endpoint")
    improve_parser.add_argument("--model-timeout", type=positive_seconds, default=60)
    improve_parser.add_argument("--cloud-review", type=Path)
    improve_parser.add_argument("--approve-cloud")
    improve_parser.add_argument("--redact-values", type=Path)
    task_init = commands.add_parser("task-init", help="生成待评测者填写的任务合同模板；不执行代码")
    task_init.add_argument("project", type=Path)
    task_init.add_argument("--document", required=True)
    task_init.add_argument("--block", type=int, required=True)
    task_init.add_argument("--task", required=True)
    task_init.add_argument("--import-root", default=".")
    task_init.add_argument("--output", required=True, type=Path)
    task_diagnose = commands.add_parser("task-diagnose", help="隔离检查任务导入前提；不生成候选或修改原件")
    task_diagnose.add_argument("project", type=Path)
    task_diagnose.add_argument("--contract", type=Path, required=True)
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
        if args.command == "learn":
            from .learn_server import serve
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535")
            serve(args.data, args.port, args.provider, args.model, gateway_endpoint=args.gateway_url)
            return 0
        elif args.command == "gateway":
            from .gateway import serve_gateway
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535")
            serve_gateway(args.data, port=args.port, model=args.model, public=args.public,
                          daily_limit=args.daily_limit, hourly_limit=args.hourly_limit,
                          total_limit=args.total_limit, concurrency=args.concurrency)
            return 0
        if args.command == "task-improve":
            from .tutorial_improve import SYSTEM, improve, prepare_improvement
            from .model_api import JSONClient
            from .tutorial_privacy import review_payload
            if args.output.exists() or args.output.resolve().is_relative_to(args.project.resolve()):
                raise ValueError("Improvement output must be new and outside the input project")
            finding = args.finding_id if args.finding_id is not None else args.finding
            prepared = prepare_improvement(args.project, args.analysis, args.contract, finding)
            client = None
            if args.proposal:
                if args.model or args.endpoint or args.approve_cloud or args.cloud_review or args.redact_values:
                    raise ValueError("Recorded proposals cannot be mixed with model or cloud options")
            else:
                client = JSONClient(args.provider, args.model or ("deepseek-flash" if args.provider == "deepseek" else ""),
                                    endpoint=args.endpoint, timeout=args.model_timeout)
                if args.provider == "deepseek":
                    path = args.cloud_review or args.output.with_name(args.output.name + "-cloud-review.json")
                    if path.resolve().is_relative_to(args.project.resolve()):
                        raise ValueError("Cloud review must be outside the input project")
                    values = json.loads(args.redact_values.read_text()) if args.redact_values else ()
                    client = review_payload(client, SYSTEM, prepared["payload"], prepared["binding"], path,
                                            args.approve_cloud, redact_values=values)
                elif args.cloud_review or args.approve_cloud or args.redact_values:
                    raise ValueError("Cloud review applies only to DeepSeek")
            result = improve(args.project, args.analysis, args.contract, finding, args.output,
                             client=client, proposal_path=args.proposal, prepared=prepared)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["status"] == "task_validation_passed" else 2
        if args.command == "task-init":
            from .tutorial_task_tools import create_template
            print(json.dumps(create_template(args.project, args.document, args.block, args.task, args.output,
                                             import_root=args.import_root), ensure_ascii=False))
            return 0
        if args.command == "task-diagnose":
            from .tutorial_task import prepare_task_inputs
            from .tutorial_task_tools import runtime_sources, prerequisite_check
            _, contract, raw, _, code = prepare_task_inputs(args.project, args.contract)
            result = prerequisite_check(code, runtime_sources(contract, raw), contract.get("timeout_seconds", 5))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] in {"ready", "not_required"} else 2
        if args.command == "task-check":
            from .tutorial_task import validate_tutorial_task
            report = validate_tutorial_task(args.project, args.contract, args.candidate, args.output)
            print(json.dumps({"status": report["status"], "adoption_status": report["adoption_status"]}, ensure_ascii=False))
            print(f"教程任务验证：{args.output / 'task-report.html'}")
            return 0 if report["status"] == "task_validation_passed" else 2
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
            if static and (args.model or args.endpoint or args.context_strategy != "lexical"):
                raise ValueError("--static cannot be combined with model options or AI/iterative context strategies")
            task = getattr(args, "task", None)
            iterative = args.command == "analyze" and args.context_strategy == "iterative"
            if task is not None and not iterative:
                raise ValueError("--task requires --context-strategy iterative")
            if task is not None and (not task.strip() or len(task) > 2000):
                raise ValueError("Task must be a non-empty string of at most 2000 characters")
            limits = {"max_total_tokens": getattr(args, "max_total_tokens", None),
                      "deadline_seconds": getattr(args, "deadline_seconds", None)}
            from .tutorial_budget import validate_limits
            validate_limits(**limits)
            if args.command == "analyze" and args.context_strategy == "ai" and any(v is not None for v in limits.values()):
                raise ValueError("Budget controls currently support lexical and iterative analysis")
            iterative_options = {"task": task, **limits}
            if iterative:
                iterative_options["max_retrieval_rounds"] = args.max_retrieval_rounds
            if not 2000 <= args.context_chars <= 48000:
                raise ValueError("Context budget must be 2000..48000 characters")
            provider = args.provider or "deepseek"
            if (static or provider != "deepseek") and (args.cloud_review or args.approve_cloud or args.redact_values):
                raise ValueError("Cloud review options apply only to DeepSeek tutorial analysis")
            from .tutorial_scope import EvidenceScope
            scope = EvidenceScope(args.include_tests, tuple(args.include_path), tuple(args.exclude_path))
            requirements = json.loads(args.evidence_requirements.read_text(encoding="utf-8")) if args.evidence_requirements else None
            client = None if static else JSONClient(
                provider, args.model or ("deepseek-flash" if provider == "deepseek" else ""),
                endpoint=args.endpoint, timeout=args.model_timeout)
            with project_input(args.project, ref=args.ref, scope=scope) as (root, provenance):
                # Keep generated artifacts entirely outside analyzed input trees.
                if args.output.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Analysis output must be outside the input project")
                snapshot = None
                if getattr(client, "provider", None) == "deepseek":
                    from .tutorial import prepare_project
                    from .tutorial_privacy import review_cloud
                    snapshot = prepare_project(root, provenance, scope=scope, task=task)
                    if requirements is not None:
                        from .tutorial_coverage import validate_requirements
                        validate_requirements(requirements, snapshot)
                    review_path = args.cloud_review or args.output.with_name(args.output.name + "-cloud-review.json")
                    if review_path.resolve().is_relative_to(root.resolve()):
                        raise ValueError("Cloud review must be outside the input project")
                    values = json.loads(args.redact_values.read_text(encoding="utf-8")) if args.redact_values else ()
                    client = review_cloud(snapshot, client, review_path, args.approve_cloud,
                                          context_chars=args.context_chars, redact_values=values, **limits,
                                          **({"max_retrieval_rounds": args.max_retrieval_rounds} if iterative else {}),
                                          strategies=("lexical", "ai") if args.command == "compare" else (args.context_strategy,))
                if args.command == "compare":
                    from .tutorial_study import run_comparison
                    result = run_comparison(root, provenance, args.output, client, context_chars=args.context_chars,
                                            scope=scope, snapshot=snapshot, evidence_requirements=requirements)
                    print(f"上下文对照报告：{args.output / 'comparison.html'}")
                    return 0 if result["run_status"] == "completed" else 2
                if snapshot is not None:
                    from .tutorial import analyze_snapshot
                    report = analyze_snapshot(snapshot, client=client, strategy=args.context_strategy,
                                              context_chars=args.context_chars, evidence_requirements=requirements, **limits,
                                              **({"max_retrieval_rounds": args.max_retrieval_rounds} if iterative else {}))
                else:
                    report = analyze_project(root, provenance, client=client, scope=scope,
                                             strategy=args.context_strategy, context_chars=args.context_chars,
                                             evidence_requirements=requirements, **iterative_options)
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
        print(f"{prog}: {exc}", file=sys.stderr)
        return 2
