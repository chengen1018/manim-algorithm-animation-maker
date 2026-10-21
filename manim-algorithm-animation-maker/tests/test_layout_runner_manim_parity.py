from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from manim import (
    Animation,
    AnimationGroup,
    Dot,
    FadeOut,
    Rectangle,
    ReplacementTransform,
    RIGHT,
    Scene,
    Square,
    Succession,
    Text,
    Transform,
    UpdateFromAlphaFunc,
    VGroup,
    tempconfig,
)


RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_layout_audit.py"
SPEC = importlib.util.spec_from_file_location("layout_runner_parity", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

AUDITOR_PATH = RUNNER_PATH.with_name("visible_layout_audit.py")
AUDITOR_SPEC = importlib.util.spec_from_file_location("visible_layout_manim_parity", AUDITOR_PATH)
assert AUDITOR_SPEC is not None and AUDITOR_SPEC.loader is not None
auditor = importlib.util.module_from_spec(AUDITOR_SPEC)
sys.modules[AUDITOR_SPEC.name] = auditor
AUDITOR_SPEC.loader.exec_module(auditor)


class LayoutRunnerManimParityTests(unittest.TestCase):
    def test_transform_of_group_child_does_not_readd_or_dissolve_group(self) -> None:
        scene = Scene()
        child = Square()
        graph = VGroup(child)
        scene.add(graph)

        runner.dry_play(scene, Transform(child, child.copy().shift(RIGHT)))

        self.assertEqual(scene.mobjects, [graph])
        self.assertIn(child, graph.submobjects)
        self.assertAlmostEqual(child.get_center()[0], 1.0)

    def test_remover_cleanup_still_follows_real_scene_restructuring(self) -> None:
        scene = Scene()
        departing, remaining = Square(), Square().shift(RIGHT)
        graph = VGroup(departing, remaining)
        scene.add(graph)

        runner.dry_play(scene, FadeOut(departing))

        self.assertNotIn(departing, scene.get_mobject_family_members())
        self.assertIn(remaining, scene.get_mobject_family_members())
        self.assertNotIn(graph, scene.mobjects)

    def test_composition_is_not_flattened_into_independent_scene_adds(self) -> None:
        scene = Scene()
        first, second = Square(), Square().shift(RIGHT)
        graph = VGroup(first, second)
        scene.add(graph)

        runner.dry_play(
            scene,
            AnimationGroup(
                Transform(first, first.copy().shift(RIGHT)),
                Transform(second, second.copy().shift(RIGHT)),
            ),
        )

        self.assertAlmostEqual(first.get_center()[0], 1.0)
        self.assertAlmostEqual(second.get_center()[0], 2.0)
        self.assertEqual(len(scene.get_mobject_family_members()), len(set(scene.get_mobject_family_members())))

    def test_replacement_and_succession_match_native_play(self) -> None:
        with tempconfig({"dry_run": True, "frame_rate": 10, "progress_bar": "none"}):
            native = Scene()
            native_start = Square()
            native_end = Square().shift(2 * RIGHT)
            native.add(native_start)
            native.play(
                Succession(
                    Transform(native_start, native_start.copy().shift(RIGHT)),
                    ReplacementTransform(native_start, native_end),
                )
            )

            dry = Scene()
            dry_start = Square()
            dry_end = Square().shift(2 * RIGHT)
            dry.add(dry_start)
            runner.dry_play(
                dry,
                Succession(
                    Transform(dry_start, dry_start.copy().shift(RIGHT)),
                    ReplacementTransform(dry_start, dry_end),
                ),
            )

        self.assertEqual(len(native.mobjects), len(dry.mobjects))
        self.assertAlmostEqual(native.mobjects[0].get_center()[0], dry.mobjects[0].get_center()[0])

    def test_update_from_alpha_endpoint_matches_native_play(self) -> None:
        def build():
            scene = Scene()
            square = Square()
            scene.add(square)

            def update(mobject, alpha):
                mobject.move_to(2 * alpha * RIGHT)

            return scene, square, UpdateFromAlphaFunc(square, update, run_time=0.2)

        with tempconfig({"dry_run": True, "frame_rate": 10, "progress_bar": "none"}):
            native, native_square, native_animation = build()
            native.play(native_animation)
            dry, dry_square, dry_animation = build()
            runner.dry_play(dry, dry_animation)

        self.assertAlmostEqual(native_square.get_center()[0], dry_square.get_center()[0])

    def test_wait_with_time_updater_matches_native_play(self) -> None:
        def build():
            scene = Scene()
            dot = Dot()
            dot.add_updater(lambda mobject, dt: mobject.shift(dt * RIGHT))
            scene.add(dot)
            return scene, dot

        with tempconfig({"dry_run": True, "frame_rate": 10, "progress_bar": "none"}):
            native, native_dot = build()
            native.wait(0.3, frozen_frame=False)
            dry, dry_dot = build()
            with runner.patched_scene_methods():
                dry.wait(0.3, frozen_frame=False)

        self.assertAlmostEqual(native_dot.get_center()[0], dry_dot.get_center()[0])
        self.assertAlmostEqual(native.time, dry.time)

    def test_wait_until_matches_native_updater_endpoint(self) -> None:
        def build():
            scene = Scene()
            dot = Dot()
            dot.add_updater(lambda mobject, dt: mobject.shift(dt * RIGHT))
            scene.add(dot)
            return scene, dot

        with tempconfig({"dry_run": True, "frame_rate": 10, "progress_bar": "none"}):
            native, native_dot = build()
            native.wait(1.0, stop_condition=lambda: native_dot.get_center()[0] >= 0.2)
            dry, dry_dot = build()
            with runner.patched_scene_methods():
                dry.wait(1.0, stop_condition=lambda: dry_dot.get_center()[0] >= 0.2)

        self.assertAlmostEqual(native_dot.get_center()[0], dry_dot.get_center()[0])
        self.assertAlmostEqual(native.time, dry.time)

    def test_updater_that_reads_scene_time_matches_native_play(self) -> None:
        def build():
            scene = Scene()
            dot = Dot()
            dot.add_updater(lambda mobject: mobject.set_x(scene.time))
            scene.add(dot)
            return scene, dot

        with tempconfig({"dry_run": True, "frame_rate": 10, "progress_bar": "none"}):
            native, native_dot = build()
            native.wait(0.3, frozen_frame=False)
            dry, dry_dot = build()
            with runner.patched_scene_methods():
                dry.wait(0.3, frozen_frame=False)

        self.assertAlmostEqual(native_dot.get_center()[0], dry_dot.get_center()[0])
        self.assertAlmostEqual(native.time, dry.time)

    def test_audit_runs_once_after_native_cleanup(self) -> None:
        class AuditSpy:
            calls = 0
            departing_present = True

            def after_play(self, scene):
                self.calls += 1
                self.departing_present = departing in scene.get_mobject_family_members()

        scene = Scene()
        departing = Square()
        scene.add(departing)
        audit = AuditSpy()

        with runner.patched_scene_methods(audit):
            scene.play(FadeOut(departing))

        self.assertEqual(audit.calls, 1)
        self.assertFalse(audit.departing_present)

    def test_static_wait_advances_time_without_audit_or_render(self) -> None:
        class AuditSpy:
            calls = 0

            def after_play(self, _scene):
                self.calls += 1

        scene = Scene()
        audit = AuditSpy()
        original_render = scene.renderer.render
        scene.renderer.render = lambda *_args, **_kwargs: self.fail("static wait rendered a frame")
        try:
            with runner.patched_scene_methods(audit):
                scene.wait(0.25)
        finally:
            scene.renderer.render = original_render

        self.assertAlmostEqual(scene.time, 0.25)
        self.assertEqual(audit.calls, 0)

    def test_play_uses_native_scene_state_without_rendering_pixels(self) -> None:
        scene = Scene()
        square = Square()
        scene.add(square)
        original_render = scene.renderer.render
        scene.renderer.render = lambda *_args, **_kwargs: self.fail("dry play rendered a frame")
        try:
            runner.dry_play(scene, Transform(square, square.copy().shift(RIGHT), run_time=0.25))
        finally:
            scene.renderer.render = original_render

        self.assertIsNotNone(scene.animations)
        self.assertAlmostEqual(scene.duration, 0.25)
        self.assertAlmostEqual(scene.time, 0.25)
        self.assertEqual(scene.renderer.num_plays, 1)

    def test_renderer_skip_flag_is_restored_when_animation_fails(self) -> None:
        class FailingAnimation(Animation):
            def interpolate_mobject(self, alpha):
                if alpha >= 1:
                    raise RuntimeError("expected failure")

        scene = Scene()
        square = Square()
        scene.add(square)
        original_skip = scene.renderer.skip_animations

        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            runner.dry_play(scene, FailingAnimation(square))

        self.assertEqual(scene.renderer.skip_animations, original_skip)
        self.assertEqual(scene.renderer.num_plays, 0)

    def test_framewise_render_override_is_removed_after_play(self) -> None:
        scene = Scene()
        square = Square()
        scene.add(square)
        self.assertNotIn("render", vars(scene.renderer))

        runner.dry_play(
            scene,
            UpdateFromAlphaFunc(square, lambda mobject, alpha: mobject.set_x(alpha), run_time=0.1),
        )

        self.assertNotIn("render", vars(scene.renderer))

    def test_existing_renderer_override_is_restored_after_play(self) -> None:
        scene = Scene()
        square = Square()
        scene.add(square)
        original_override = lambda *_args, **_kwargs: None
        scene.renderer.render = original_override

        runner.dry_play(
            scene,
            UpdateFromAlphaFunc(square, lambda mobject, alpha: mobject.set_x(alpha), run_time=0.1),
        )

        self.assertIs(scene.renderer.render, original_override)

    def test_real_text_glyphs_require_strictly_higher_z_index(self) -> None:
        scene = Scene()
        panel = Rectangle(width=2, height=1).set_fill(opacity=1)
        label = Text("A")
        scene.add(VGroup(panel, label))

        equal_z = auditor.audit_scene_visible_mobjects(scene)
        self.assertIn("text-occlusion", [finding.relation for finding in equal_z.findings])

        label.set_z_index(1)
        higher_z = auditor.audit_scene_visible_mobjects(scene)
        self.assertNotIn("text-occlusion", [finding.relation for finding in higher_z.findings])


if __name__ == "__main__":
    unittest.main()
