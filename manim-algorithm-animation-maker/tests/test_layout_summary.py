from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class LayoutSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = load_module(
            "summarize_layout_audit_test",
            SKILL_ROOT / "scripts" / "summarize_layout_audit.py",
        )

    def test_groups_repeated_pair_and_preserves_checkpoints_and_variants(self) -> None:
        findings = [
            {
                "severity": "WARNING",
                "relation": "overlap",
                "objects": ["Circle[0]", "Circle[1]"],
                "message": "first geometry",
                "checkpoint": "Scene:after-play-0001",
                "accepted": False,
            },
            {
                "severity": "WARNING",
                "relation": "overlap",
                "objects": ["Circle[0]", "Circle[1]"],
                "message": "second geometry",
                "checkpoint": "Scene:after-play-0002",
                "accepted": False,
            },
        ]
        groups = self.summary.group_findings(findings)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["occurrence_count"], 2)
        self.assertEqual(groups[0]["message_variant_count"], 2)
        self.assertEqual(groups[0]["checkpoints"], ["Scene:after-play-0001", "Scene:after-play-0002"])

    def test_summary_keeps_raw_report_identity_and_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "scene_class": "Scene",
                        "source_path": "scene.py",
                        "source_sha256": "source-hash",
                        "gate_result": "FAIL",
                        "summary": {"unresolved_warnings": 1},
                        "findings": [],
                    }
                ),
                encoding="utf-8",
            )
            result = self.summary.build_summary([report_path])
        self.assertIn("raw layout audit reports remain authoritative", result["authority"])
        self.assertEqual(result["reports"][0]["source_sha256"], "source-hash")
        self.assertEqual(len(result["reports"][0]["report_sha256"]), 64)

    def test_main_writes_grouped_json_and_bounded_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "scene_class": "Scene",
                        "gate_result": "FAIL",
                        "summary": {"unresolved_warnings": 2},
                        "findings": [
                            {
                                "severity": "WARNING",
                                "relation": "overlap",
                                "objects": ["Circle[0]", "Circle[1]"],
                                "message": "overlap",
                                "checkpoint": f"Scene:after-play-{index:04d}",
                                "accepted": False,
                            }
                            for index in (1, 2)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            json_output = root / "summary.json"
            markdown_output = root / "triage.md"
            exit_code = self.summary.main(
                [
                    str(report_path),
                    "--json-output",
                    str(json_output),
                    "--markdown-output",
                    str(markdown_output),
                ]
            )
            payload = json.loads(json_output.read_text(encoding="utf-8"))
            markdown = markdown_output.read_text(encoding="utf-8")
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["reports"][0]["groups"][0]["occurrence_count"], 2)
        self.assertIn("occurrences: 2", markdown)

    def test_markdown_compacts_long_checkpoint_lists(self) -> None:
        checkpoints = [f"Scene:after-play-{index:04d}" for index in range(20)]
        rendered = self.summary.format_checkpoints(checkpoints)
        self.assertIn("(+12 more; see summary JSON)", rendered)
        self.assertNotIn("after-play-0019", rendered)


if __name__ == "__main__":
    unittest.main()
