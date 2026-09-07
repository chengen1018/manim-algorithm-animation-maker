from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any


ACTIVE_VISIBLE_AUDITOR = None
VISIBLE_LEVEL_ORDER = {"error": 3, "warning": 2, "info": 1}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a scene far enough to execute layout audits without rendering video.",
    )
    parser.add_argument("scene_file", help="Path to the generated scene file.")
    parser.add_argument("scene_class", nargs="?", help="Scene class name. Defaults to the first Scene subclass.")
    parser.add_argument("--render-profile", help="Absolute render_profile.json used by layout and final render.")
    parser.add_argument(
        "--require-adapter",
        action="store_true",
        help="Fail unless scene-specific initial, beat and final adapter checkpoints run without findings.",
    )
    parser.add_argument(
        "--audit-visible",
        action="store_true",
        help="Audit visible scene mobjects after each play() and at the end of construct().",
    )
    parser.add_argument(
        "--visible-final-only",
        action="store_true",
        help="With --audit-visible, scan only after construct() instead of after every play().",
    )
    parser.add_argument(
        "--visible-frame-margin",
        type=float,
        default=0.0,
        help="Frame margin for --audit-visible overflow checks.",
    )
    parser.add_argument(
        "--visible-containment-padding",
        type=float,
        default=1e-3,
        help="Required gap from outer boundaries before --audit-visible reports strict containment as info.",
    )
    parser.add_argument(
        "--visible-overlap-epsilon",
        type=float,
        default=1e-6,
        help="Minimum positive overlap width and height before --audit-visible reports overlap as warning.",
    )
    parser.add_argument(
        "--visible-include-descendants",
        action="store_true",
        help="Deprecated compatibility flag; structural containers are always traversed and atomic families remain leaves.",
    )
    parser.add_argument(
        "--visible-max-reports",
        type=int,
        default=250,
        help="Maximum number of visible-audit findings to print; the JSON report always contains every finding.",
    )
    parser.add_argument(
        "--visible-report-level",
        choices=("error", "warning", "info"),
        default="warning",
        help="Minimum visible-audit report level to print. Defaults to warning, which suppresses strict-containment info logs.",
    )
    parser.add_argument(
        "--visible-report",
        help="Complete JSON report path. Defaults beside the scene file, named for the Scene class.",
    )
    parser.add_argument(
        "--visible-exceptions",
        help="Optional project-local JSON file containing exact, source-bound warning dispositions.",
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        help="Print a full traceback if scene construction fails.",
    )
    return parser.parse_args()


def gate_failures(
    *,
    visible_errors: int,
    visible_warnings: int,
    checkpoints: list[str],
    require_adapter: bool,
) -> list[str]:
    failures: list[str] = []
    if visible_errors:
        failures.append(f"{visible_errors} visible layout error(s)")
    if visible_warnings:
        failures.append(f"{visible_warnings} unresolved visible layout warning(s)")
    if not require_adapter:
        return failures

    normalized = [context.strip().lower() for context in checkpoints]
    has_initial = any(context == "initial" or context.endswith(":initial") for context in normalized)
    has_beat = any(context.startswith("beat:") or ":beat:" in context for context in normalized)
    has_final = any(context == "final" or context.endswith(":final") for context in normalized)
    if not has_initial:
        failures.append("scene-specific adapter is missing an initial checkpoint")
    if not has_beat:
        failures.append("scene-specific adapter is missing a beat checkpoint")
    if not has_final:
        failures.append("scene-specific adapter is missing a final checkpoint")
    return failures


def apply_render_profile(profile_path: Path) -> dict[str, object]:
    from manim import config, __version__ as manim_version
    import manimpango

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    required = (
        "pixel_width",
        "pixel_height",
        "frame_rate",
        "renderer",
        "frame_width",
        "frame_height",
        "font",
        "python_executable",
        "manim_version",
    )
    missing = [field for field in required if field not in profile]
    if missing:
        raise RuntimeError(f"render profile is missing: {', '.join(missing)}")

    expected_python = Path(str(profile["python_executable"])).expanduser().resolve()
    current_python = Path(sys.executable).resolve()
    if current_python != expected_python:
        raise RuntimeError(f"Python mismatch: current={current_python}, profile={expected_python}")
    if str(manim_version) != str(profile["manim_version"]):
        raise RuntimeError(f"Manim version mismatch: current={manim_version}, profile={profile['manim_version']}")
    available_fonts = {str(font).casefold() for font in manimpango.list_fonts()}
    if str(profile["font"]).casefold() not in available_fonts:
        raise RuntimeError(f"profile font is unavailable: {profile['font']}")

    config.pixel_width = int(profile["pixel_width"])
    config.pixel_height = int(profile["pixel_height"])
    config.frame_rate = float(profile["frame_rate"])
    config.renderer = str(profile["renderer"])
    config.frame_width = float(profile["frame_width"])
    config.frame_height = float(profile["frame_height"])
    print(f"[layout-profile] path={profile_path}")
    print(
        "[layout-profile] "
        f"python={current_python} manim={manim_version} renderer={config.renderer} "
        f"resolution={config.pixel_width}x{config.pixel_height} fps={config.frame_rate} "
        f"frame={config.frame_width}x{config.frame_height} font={profile['font']}"
    )
    return profile


def reset_adapter_checkpoints() -> None:
    module = sys.modules.get("scene_layout_audit")
    reset = getattr(module, "reset_layout_audit_checkpoints", None)
    if callable(reset):
        reset()


def adapter_checkpoints() -> list[str]:
    module = sys.modules.get("scene_layout_audit")
    get_checkpoints = getattr(module, "get_layout_audit_checkpoints", None)
    if callable(get_checkpoints):
        return list(get_checkpoints())
    return []


def registered_graph_roots() -> list[tuple[object, str | None]]:
    module = sys.modules.get("scene_layout_audit")
    get_roots = getattr(module, "get_layout_audit_graph_roots", None)
    if callable(get_roots):
        return list(get_roots())
    return []


REQUIRED_EXCEPTION_FIELDS = {
    "scene_class",
    "checkpoint",
    "objects",
    "relation",
    "explanation",
    "supporting_reference",
    "source_sha256",
}
NON_WAIVABLE_RELATIONS = {
    "ambiguous-graph-membership",
    "ambiguous-structural-parent",
    "exception-error",
    "frame-overflow-bottom",
    "frame-overflow-left",
    "frame-overflow-right",
    "frame-overflow-top",
    "tool-failure",
    "unclassified",
}


def load_exception_file(path: Path | None) -> tuple[list[dict[str, Any]], list[str], str | None]:
    if path is None:
        return [], [], None
    file_hash = None
    try:
        if path.is_file():
            file_hash = sha256(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"cannot read exception file {path}: {exc}"], file_hash
    if not isinstance(payload, dict) or not isinstance(payload.get("exceptions"), list):
        return [], ["exception file must be an object with an exceptions array"], file_hash
    records = payload["exceptions"]
    errors: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"exception[{index}] must be an object")
            continue
        missing = REQUIRED_EXCEPTION_FIELDS - set(record)
        if missing:
            errors.append(f"exception[{index}] is missing: {', '.join(sorted(missing))}")
    return records, errors, file_hash


def apply_warning_exceptions(
    entries: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    *,
    scene_class: str,
    source_sha256: str,
) -> list[str]:
    errors: list[str] = []
    seen_exception_keys: set[tuple[object, ...]] = set()
    current_scene_exceptions: list[tuple[int, dict[str, Any]]] = []
    for index, record in enumerate(exceptions):
        if not isinstance(record, dict) or REQUIRED_EXCEPTION_FIELDS - set(record):
            continue
        scalar_fields = (
            "scene_class",
            "checkpoint",
            "relation",
            "explanation",
            "supporting_reference",
            "source_sha256",
        )
        if any(not isinstance(record[field], str) or not record[field].strip() for field in scalar_fields):
            errors.append(f"exception[{index}] requires non-empty string fields")
            continue
        objects = record["objects"]
        if (
            not isinstance(objects, list)
            or len(objects) != 2
            or any(not isinstance(value, str) or not value.strip() for value in objects)
        ):
            errors.append(f"exception[{index}] objects must contain exactly two non-empty names")
            continue
        match_values = (
            record["scene_class"],
            record["checkpoint"],
            record["relation"],
            record["source_sha256"],
            *objects,
        )
        if any("*" in value or "?" in value for value in match_values):
            errors.append(f"exception[{index}] contains a wildcard")
            continue
        if record["source_sha256"].lower() != source_sha256.lower():
            errors.append(f"exception[{index}] has a stale source SHA-256")
            continue
        if record["scene_class"] != scene_class:
            errors.append(
                f"exception[{index}] scene_class {record['scene_class']!r} "
                f"does not match audited scene {scene_class!r}"
            )
            continue
        if record["relation"] in NON_WAIVABLE_RELATIONS:
            errors.append(f"exception[{index}] targets non-waivable relation {record['relation']}")
            continue
        if record["relation"] == "text-occlusion" and not any(
            marker in record["supporting_reference"]
            for marker in ("confirmed_requirements.md", "animation_design.md")
        ):
            errors.append(
                f"exception[{index}] text occlusion requires a confirmed_requirements.md "
                "or animation_design.md reference"
            )
            continue
        key = (
            record["scene_class"],
            record["checkpoint"],
            tuple(objects),
            record["relation"],
            record["source_sha256"].lower(),
        )
        if key in seen_exception_keys:
            errors.append(f"exception[{index}] duplicates another exact exception")
            continue
        seen_exception_keys.add(key)
        current_scene_exceptions.append((index, record))

    for index, record in current_scene_exceptions:
        matches = [
            entry
            for entry in entries
            if entry["context"] == record["checkpoint"]
            and entry["finding"].severity == "WARNING"
            and entry["finding"].waivable
            and list(entry["finding"].objects) == record["objects"]
            and entry["finding"].relation == record["relation"]
        ]
        if len(matches) != 1:
            errors.append(f"exception[{index}] matches {len(matches)} warning findings; expected exactly one")
            continue
        finding = matches[0]["finding"]
        finding.accepted = True
        finding.exception_index = index
    return errors


class VisibleAuditAccumulator:
    def __init__(self, args: argparse.Namespace, scene_class_name: str, source_path: Path):
        self.args = args
        self.scene_class_name = scene_class_name
        self.source_path = source_path
        self.source_sha256 = sha256(source_path)
        self.render_profile_path = (
            Path(args.render_profile).expanduser().resolve() if getattr(args, "render_profile", None) else None
        )
        self.render_profile_sha256 = (
            sha256(self.render_profile_path)
            if self.render_profile_path is not None and self.render_profile_path.is_file()
            else None
        )
        self.play_index = 0
        self.entries: list[dict[str, Any]] = []
        self.exception_path = Path(args.visible_exceptions).expanduser().resolve() if args.visible_exceptions else None
        self.exception_sha256: str | None = None
        self.error_count = 0
        self.warning_count = 0
        self.accepted_warning_count = 0
        self.info_count = 0

    def after_play(self, scene) -> None:
        if self.args.visible_final_only:
            return
        self.play_index += 1
        self.audit(scene, f"{self.scene_class_name}:after-play-{self.play_index:04d}")

    def final(self, scene) -> None:
        self.audit(scene, f"{self.scene_class_name}:final")

    def audit(self, scene, context: str) -> None:
        from visible_layout_audit import audit_scene_visible_mobjects

        result = audit_scene_visible_mobjects(
            scene,
            context=context,
            frame_margin=self.args.visible_frame_margin,
            containment_padding=self.args.visible_containment_padding,
            overlap_epsilon=self.args.visible_overlap_epsilon,
            include_descendants=self.args.visible_include_descendants,
            graph_roots=registered_graph_roots(),
        )
        self.entries.extend({"context": result.context, "finding": finding} for finding in result.findings)

    def add_tool_error(self, message: str) -> None:
        from visible_layout_audit import VisibleFinding

        self.entries.append(
            {
                "context": f"{self.scene_class_name}:tool",
                "finding": VisibleFinding("ERROR", "tool-failure", (), message, waivable=False),
            }
        )

    def finalize(self) -> None:
        exceptions, errors, exception_hash = load_exception_file(self.exception_path)
        self.exception_sha256 = exception_hash
        errors.extend(
            apply_warning_exceptions(
                self.entries,
                exceptions,
                scene_class=self.scene_class_name,
                source_sha256=self.source_sha256,
            )
        )
        for message in errors:
            self.add_tool_error(message)

        self.error_count = sum(entry["finding"].severity == "ERROR" for entry in self.entries)
        self.accepted_warning_count = sum(
            entry["finding"].severity == "WARNING" and entry["finding"].accepted for entry in self.entries
        )
        self.warning_count = sum(
            entry["finding"].severity == "WARNING" and not entry["finding"].accepted for entry in self.entries
        )
        self.info_count = sum(entry["finding"].severity == "INFO" for entry in self.entries)
        self._print_findings()

    def _print_findings(self) -> None:
        printable = [
            entry
            for entry in self.entries
            if VISIBLE_LEVEL_ORDER[entry["finding"].severity.lower()]
            >= VISIBLE_LEVEL_ORDER[self.args.visible_report_level]
        ]
        for entry in printable[: self.args.visible_max_reports]:
            finding = entry["finding"]
            disposition = " ACCEPTED" if finding.accepted else ""
            print(
                f"[visible-layout:{entry['context']}] "
                f"{finding.severity}{disposition} {finding.message}"
            )
        if len(printable) > self.args.visible_max_reports:
            print(
                f"[layout-runner] visible report limit reached ({self.args.visible_max_reports}); "
                f"{len(printable) - self.args.visible_max_reports} finding(s) omitted from human output only"
            )

    def write_report(self, path: Path, gate_result: str, checkpoints: list[str], gate_failures: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        findings = []
        for entry in self.entries:
            finding = entry["finding"].to_dict()
            finding["scene_class"] = self.scene_class_name
            finding["checkpoint"] = entry["context"]
            findings.append(finding)
        report = {
            "schema_version": 1,
            "scene_class": self.scene_class_name,
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "render_profile_path": str(self.render_profile_path) if self.render_profile_path else None,
            "render_profile_sha256": self.render_profile_sha256,
            "exception_file": str(self.exception_path) if self.exception_path else None,
            "exception_file_sha256": self.exception_sha256,
            "adapter_checkpoints": checkpoints,
            "summary": {
                "total_findings": len(findings),
                "accepted_warnings": self.accepted_warning_count,
                "unresolved_warnings": self.warning_count,
                "errors": self.error_count,
                "infos": self.info_count,
            },
            "gate_failures": gate_failures,
            "gate_result": gate_result,
            "findings": findings,
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_module(scene_file: Path) -> ModuleType:
    module_name = f"_layout_audit_target_{scene_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, scene_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load scene file: {scene_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def find_scene_class(module: ModuleType, requested_name: str | None):
    from manim import Scene

    if requested_name:
        scene_class = getattr(module, requested_name, None)
        if scene_class is None:
            raise RuntimeError(f"Scene class not found: {requested_name}")
        if not isinstance(scene_class, type) or not issubclass(scene_class, Scene):
            raise RuntimeError(f"{requested_name} is not a Scene subclass")
        return scene_class

    scene_classes = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type) and issubclass(value, Scene) and value is not Scene and value.__module__ == module.__name__
    ]
    if not scene_classes:
        raise RuntimeError("No Manim Scene subclass found in scene file")
    if len(scene_classes) > 1:
        names = ", ".join(cls.__name__ for cls in scene_classes)
        raise RuntimeError(f"Multiple Scene subclasses found; pass one explicitly: {names}")
    return scene_classes[0]


def flatten_animations(animation):
    children = getattr(animation, "animations", None)
    if children:
        for child in children:
            yield from flatten_animations(child)
    else:
        yield animation


def finish_animation(scene, animation) -> None:
    from manim import Animation

    if not isinstance(animation, Animation):
        raise TypeError(f"Scene.play expected Animation instances; got {type(animation).__name__}")

    mobject = getattr(animation, "mobject", None)
    if mobject is not None:
        scene.add(mobject)

    animation.begin()
    animation.interpolate(1)
    animation.finish()
    animation.clean_up_from_scene(scene)


def dry_play(scene, *animations, **kwargs):
    animations = scene.compile_animations(*animations, **kwargs)
    for animation in animations:
        for child in flatten_animations(animation):
            finish_animation(scene, child)
    if ACTIVE_VISIBLE_AUDITOR is not None:
        ACTIVE_VISIBLE_AUDITOR.after_play(scene)
    return scene


def dry_wait(scene, *args, **kwargs):
    return scene


def dry_add_sound(scene, *args, **kwargs):
    return scene


@contextmanager
def patched_scene_methods(visible_auditor=None):
    from manim import Scene

    global ACTIVE_VISIBLE_AUDITOR

    original_play = Scene.play
    original_wait = Scene.wait
    original_add_sound = getattr(Scene, "add_sound", None)
    original_visible_auditor = ACTIVE_VISIBLE_AUDITOR

    Scene.play = dry_play
    Scene.wait = dry_wait
    if original_add_sound is not None:
        Scene.add_sound = dry_add_sound
    ACTIVE_VISIBLE_AUDITOR = visible_auditor

    try:
        yield
    finally:
        ACTIVE_VISIBLE_AUDITOR = original_visible_auditor
        Scene.play = original_play
        Scene.wait = original_wait
        if original_add_sound is not None:
            Scene.add_sound = original_add_sound


def main() -> int:
    args = parse_args()
    scene_file = Path(args.scene_file).resolve()
    if not scene_file.exists():
        print(f"[layout-runner] scene file not found: {scene_file}", file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(script_dir))
    sys.path.insert(0, str(scene_file.parent))

    os.environ.setdefault("MANIM_LAYOUT_AUDIT", "1")
    if args.require_adapter:
        os.environ["MANIM_LAYOUT_AUDIT_FAIL"] = "1"
    os.environ["MANIM_LAYOUT_DRY_RUN"] = "1"

    visible_auditor = None
    scene_class_name = args.scene_class or scene_file.stem
    try:
        if args.visible_max_reports < 0:
            raise RuntimeError("--visible-max-reports must be zero or greater")
        if args.visible_exceptions and not args.audit_visible:
            raise RuntimeError("--visible-exceptions requires --audit-visible")
        if args.audit_visible:
            visible_auditor = VisibleAuditAccumulator(args, scene_class_name, scene_file)
        if args.require_adapter and not args.render_profile:
            raise RuntimeError("--require-adapter requires --render-profile")
        if args.render_profile:
            profile_path = Path(args.render_profile).expanduser().resolve()
            if not profile_path.is_file():
                raise RuntimeError(f"render profile not found: {profile_path}")
            apply_render_profile(profile_path)
        module = load_module(scene_file)
        scene_class = find_scene_class(module, args.scene_class)
        scene_class_name = scene_class.__name__
        if visible_auditor is not None:
            visible_auditor.scene_class_name = scene_class_name
        reset_adapter_checkpoints()
        with patched_scene_methods(visible_auditor):
            scene = scene_class()
            scene.construct()
            if visible_auditor is not None:
                visible_auditor.final(scene)
    except Exception as exc:
        print(f"[layout-runner] failed: {exc}", file=sys.stderr)
        if visible_auditor is not None:
            visible_auditor.add_tool_error(str(exc))
            visible_auditor.finalize()
            report_path = (
                Path(args.visible_report).expanduser().resolve()
                if args.visible_report
                else scene_file.parent / f"layout_audit_report.{scene_class_name}.json"
            )
            visible_auditor.write_report(report_path, "FAIL", adapter_checkpoints(), [str(exc)])
            print(f"[layout-runner] complete visible report: {report_path} SHA-256={sha256(report_path)}")
            print("[layout-runner] final gate result: FAIL")
        if args.traceback:
            traceback.print_exc()
        return 1

    print(f"[layout-runner] completed dry-run for {scene_class.__name__}")
    checkpoints = adapter_checkpoints()
    print(f"[layout-runner] adapter checkpoints ({len(checkpoints)}): {', '.join(checkpoints) or 'none'}")
    if visible_auditor is not None:
        visible_auditor.finalize()
        print(
            "[layout-runner] visible summary: "
            f"total={len(visible_auditor.entries)} "
            f"accepted_warnings={visible_auditor.accepted_warning_count} "
            f"unresolved_warnings={visible_auditor.warning_count} "
            f"errors={visible_auditor.error_count} "
            f"infos={visible_auditor.info_count} "
            f"exception_file={visible_auditor.exception_path or 'none'} "
            f"exception_SHA-256={visible_auditor.exception_sha256 or 'none'}"
        )
    failures = gate_failures(
        visible_errors=visible_auditor.error_count if visible_auditor is not None else 0,
        visible_warnings=visible_auditor.warning_count if visible_auditor is not None else 0,
        checkpoints=checkpoints,
        require_adapter=args.require_adapter,
    )
    for failure in failures:
        print(f"[layout-runner] gate failure: {failure}", file=sys.stderr)
    if visible_auditor is not None:
        report_path = (
            Path(args.visible_report).expanduser().resolve()
            if args.visible_report
            else scene_file.parent / f"layout_audit_report.{scene_class.__name__}.json"
        )
        visible_auditor.write_report(report_path, "FAIL" if failures else "PASS", checkpoints, failures)
        print(f"[layout-runner] complete visible report: {report_path} SHA-256={sha256(report_path)}")
    print(f"[layout-runner] final gate result: {'FAIL' if failures else 'PASS'}")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
