"""CLI entrypoint for evaluation workflow."""

import argparse
import sys
from typing import Optional, Sequence

from evaluation.ground_truth import cmd_templates, cmd_check_gt
from evaluation.variants import cmd_variants
from evaluation.scoring import cmd_score, cmd_diff
from evaluation.report import (
    cmd_report,
    cmd_compare,
    cmd_timing,
    cmd_causes_template,
    cmd_item_math_diag,
)
from evaluation.pipeline_runner import cmd_plan, cmd_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluation.cli",
        description="Evaluation CLI for AI Document-to-Data Extractor",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to run")

    # templates
    tpl_parser = subparsers.add_parser("templates", help="Generate ground truth templates for unannotated documents")
    tpl_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to process (dev or holdout)")

    # check-gt
    cgt_parser = subparsers.add_parser("check-gt", help="Validate ground truth files for syntax, schema, and verified status")
    cgt_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to validate (dev or holdout)")

    # variants
    subparsers.add_parser("variants", help="Generate degraded image variants for all documents in eval/data/")

    # plan
    plan_parser = subparsers.add_parser("plan", help="Dry-run case matrix, token estimates, and runtime without API calls")
    plan_parser.add_argument("--only", type=str, default=None, help="Document ID to plan for")
    plan_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to plan for (dev or holdout)")
    plan_parser.add_argument("--cases", type=str, default=None, help="Comma-separated case types to include (e.g. text,image)")

    # run
    run_parser = subparsers.add_parser("run", help="Execute evaluation cases")
    run_parser.add_argument("--limit", type=int, default=None, help="Maximum number of cases to execute")
    run_parser.add_argument("--only", type=str, default=None, help="Run only cases for this document ID")
    run_parser.add_argument("--force", action="store_true", help="Re-run cases even if cached results exist")
    run_parser.add_argument("--repeats", type=int, default=1, help="Number of repetitions for text cases (default 1)")
    run_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to evaluate (dev or holdout)")
    run_parser.add_argument("--label", type=str, default="v1", help="Results label (v1 or custom like v2)")
    run_parser.add_argument("--cases", type=str, default=None, help="Comma-separated case types to run (e.g. text,image)")
    run_parser.add_argument("--version", type=str, default=None, choices=["v1", "v2"], help="Pipeline version override (v1 or v2)")

    # score
    score_parser = subparsers.add_parser("score", help="Score raw extraction outputs against verified ground truth")
    score_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to score")
    score_parser.add_argument("--label", type=str, default="v1", help="Results label to score (default: v1)")

    # report
    report_parser = subparsers.add_parser("report", help="Generate aggregate summary markdown report")
    report_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset for report")
    report_parser.add_argument("--label", type=str, default="v1", help="Results label for report (default: v1)")

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare two evaluation runs (e.g. v1 vs v2)")
    compare_parser.add_argument("--a", type=str, default="v1", help="First results label (default: v1)")
    compare_parser.add_argument("--b", type=str, default="v2", help="Second results label (default: v2)")
    compare_parser.add_argument("--dataset", type=str, default="dev", choices=["dev", "holdout"], help="Dataset to compare on (default: dev)")

    # timing
    subparsers.add_parser("timing", help="Analyze manual vs reviewed timing comparison")

    # diff
    diff_parser = subparsers.add_parser("diff", help="Detailed field-by-field diff for a single evaluation case")
    diff_parser.add_argument("--case", type=str, required=True, help="Case ID to inspect (e.g. inv01__text)")

    # causes-template
    subparsers.add_parser("causes-template", help="Generate error causes template for silent error cases")

    # item-math-diag
    subparsers.add_parser("item-math-diag", help="Print ITEM_MATH_MISMATCH diagnostic output to terminal")

    return parser


def main(args: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "templates":
        return cmd_templates(dataset=parsed.dataset)
    elif parsed.command == "check-gt":
        return cmd_check_gt(dataset=parsed.dataset)
    elif parsed.command == "variants":
        return cmd_variants()
    elif parsed.command == "plan":
        return cmd_plan(only_doc=parsed.only, dataset=parsed.dataset, cases=parsed.cases)
    elif parsed.command == "run":
        return cmd_run(
            limit=parsed.limit,
            only=parsed.only,
            force=parsed.force,
            repeats=parsed.repeats,
            dataset=parsed.dataset,
            label=parsed.label,
            cases=parsed.cases,
            version=parsed.version,
        )
    elif parsed.command == "score":
        return cmd_score(label=parsed.label, dataset=parsed.dataset)
    elif parsed.command == "report":
        return cmd_report(label=parsed.label, dataset=parsed.dataset)
    elif parsed.command == "compare":
        return cmd_compare(label_a=parsed.a, label_b=parsed.b, dataset=parsed.dataset)
    elif parsed.command == "timing":
        return cmd_timing()
    elif parsed.command == "diff":
        return cmd_diff(case_id=parsed.case)
    elif parsed.command == "causes-template":
        return cmd_causes_template()
    elif parsed.command == "item-math-diag":
        return cmd_item_math_diag()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
