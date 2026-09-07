from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        raise ValueError(f"{path}: expected a layout audit report with a findings array")
    if not isinstance(payload.get("scene_class"), str):
        raise ValueError(f"{path}: missing scene_class")
    return payload


def group_findings(findings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[object, ...], list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        key = (
            finding.get("severity"),
            finding.get("relation"),
            tuple(finding.get("objects", [])),
            bool(finding.get("accepted", False)),
            finding.get("exception_index"),
        )
        buckets[key].append(finding)

    groups: list[dict[str, Any]] = []
    for key, occurrences in buckets.items():
        severity, relation, objects, accepted, exception_index = key
        checkpoints = list(dict.fromkeys(item.get("checkpoint") for item in occurrences))
        messages = list(dict.fromkeys(str(item.get("message", "")) for item in occurrences))
        groups.append(
            {
                "severity": severity,
                "relation": relation,
                "objects": list(objects),
                "accepted": accepted,
                "exception_index": exception_index,
                "occurrence_count": len(occurrences),
                "checkpoints": checkpoints,
                "message_variant_count": len(messages),
                "representative_messages": messages[:3],
                "recommended_action": recommended_action(
                    str(severity),
                    bool(accepted),
                    str(relation),
                    len(occurrences),
                ),
            }
        )
    return sorted(
        groups,
        key=lambda item: (
            {"ERROR": 0, "WARNING": 1, "INFO": 2}.get(str(item["severity"]), 3),
            -int(item["occurrence_count"]),
            str(item["relation"]),
            tuple(item["objects"]),
        ),
    )


def recommended_action(severity: str, accepted: bool, relation: str, occurrences: int) -> str:
    if severity == "ERROR":
        return "fix-required"
    if severity == "WARNING" and accepted:
        return "review-approved-exception"
    if severity == "WARNING":
        return "fix-or-propose-exception-for-review"
    if relation == "same-graph-collinear-overlap":
        return "inspect-collinear-edge-overlap"
    if relation == "same-graph-line-contact":
        return "inspect-unsupported-edge-contact"
    if occurrences > 1:
        return "consider-fixing-persistent-best-effort-finding"
    return "no-action-unless-visually-significant"


def build_summary(report_paths: Sequence[Path]) -> dict[str, Any]:
    reports = []
    for path in report_paths:
        resolved = path.resolve()
        report = load_report(resolved)
        groups = group_findings(report["findings"])
        reports.append(
            {
                "scene_class": report["scene_class"],
                "report_path": str(resolved),
                "report_sha256": sha256(resolved),
                "source_path": report.get("source_path"),
                "source_sha256": report.get("source_sha256"),
                "gate_result": report.get("gate_result"),
                "raw_summary": report.get("summary", {}),
                "group_count": len(groups),
                "groups": groups,
            }
        )
    return {
        "schema_version": 1,
        "authority": "derived-summary-only; raw layout audit reports remain authoritative",
        "reports": reports,
    }


def render_markdown(
    summary: dict[str, Any],
    *,
    max_warning_groups: int,
    max_info_groups: int,
) -> str:
    lines = [
        "# Layout Audit Triage",
        "",
        "> Derived summary only. The raw JSON reports and their gate results remain authoritative.",
        "",
    ]
    for report in summary["reports"]:
        groups = report["groups"]
        blocking = [
            group
            for group in groups
            if group["severity"] == "ERROR"
            or (group["severity"] == "WARNING" and not group["accepted"])
        ]
        accepted = [group for group in groups if group["severity"] == "WARNING" and group["accepted"]]
        infos = [group for group in groups if group["severity"] == "INFO"]
        lines.extend(
            [
                f"## {report['scene_class']}",
                "",
                f"- Gate: `{report['gate_result']}`",
                f"- Raw report: `{report['report_path']}`",
                f"- Raw report SHA-256: `{report['report_sha256']}`",
                f"- Source SHA-256: `{report['source_sha256']}`",
                f"- Grouped findings: {len(groups)}; blocking: {len(blocking)}; accepted: {len(accepted)}; info: {len(infos)}",
                "",
            ]
        )
        append_groups(lines, "Blocking groups", blocking, max_warning_groups)
        append_groups(lines, "Accepted warning groups", accepted, max_warning_groups)
        append_groups(lines, "Best-effort INFO groups", infos, max_info_groups)
    return "\n".join(lines).rstrip() + "\n"


def append_groups(
    lines: list[str],
    title: str,
    groups: Sequence[dict[str, Any]],
    limit: int,
) -> None:
    lines.extend([f"### {title}", ""])
    if not groups:
        lines.extend(["None.", ""])
        return
    for group in groups[:limit]:
        objects = " ↔ ".join(group["objects"])
        checkpoints = format_checkpoints(group["checkpoints"])
        lines.extend(
            [
                f"- `{group['severity']} {group['relation']}` — `{objects}`",
                f"  - occurrences: {group['occurrence_count']}; message variants: {group['message_variant_count']}",
                f"  - checkpoints: {checkpoints}",
                f"  - action: `{group['recommended_action']}`",
            ]
        )
        if group["representative_messages"]:
            lines.append(f"  - sample: {group['representative_messages'][0]}")
    omitted = len(groups) - min(len(groups), limit)
    if omitted:
        lines.append(f"- {omitted} additional group(s) omitted from this triage view; inspect the summary JSON or raw report.")
    lines.append("")


def format_checkpoints(checkpoints: Sequence[object], limit: int = 8) -> str:
    shown = ", ".join(str(value) for value in checkpoints[:limit])
    omitted = len(checkpoints) - min(len(checkpoints), limit)
    if omitted:
        return f"{shown}, ... (+{omitted} more; see summary JSON)"
    return shown


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Group repeated visible layout findings without changing gate evidence.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--max-warning-groups", type=int, default=10)
    parser.add_argument("--max-info-groups", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_warning_groups < 0 or args.max_info_groups < 0:
        raise ValueError("group limits must be non-negative")
    summary = build_summary(args.reports)
    args.json_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.markdown_output.write_text(
        render_markdown(
            summary,
            max_warning_groups=args.max_warning_groups,
            max_info_groups=args.max_info_groups,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
