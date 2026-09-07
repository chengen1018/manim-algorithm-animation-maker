from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import types
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


class FakeMobject:
    def __init__(
        self,
        bounds: tuple[float, float, float, float],
        *,
        fill: float = 1.0,
        stroke: float = 1.0,
        z_index: float = 0.0,
        children=(),
    ):
        self._bounds = bounds
        self._fill = fill
        self._stroke = stroke
        self.z_index = z_index
        self.submobjects = list(children)

    def _resolved_bounds(self):
        if not self.submobjects:
            return self._bounds
        child_bounds = [child._resolved_bounds() for child in self.submobjects]
        return (
            min(bounds[0] for bounds in child_bounds),
            max(bounds[1] for bounds in child_bounds),
            min(bounds[2] for bounds in child_bounds),
            max(bounds[3] for bounds in child_bounds),
        )

    def get_left(self):
        return [self._resolved_bounds()[0], 0.0, 0.0]

    def get_right(self):
        return [self._resolved_bounds()[1], 0.0, 0.0]

    def get_bottom(self):
        return [0.0, self._resolved_bounds()[2], 0.0]

    def get_top(self):
        return [0.0, self._resolved_bounds()[3], 0.0]

    def get_fill_opacity(self):
        return self._fill

    def get_stroke_opacity(self):
        return self._stroke


class VGroup(FakeMobject):
    def __init__(self, *children):
        super().__init__((0.0, 0.0, 0.0, 0.0), fill=0.0, stroke=0.0, children=children)


class Rectangle(FakeMobject):
    pass


class Ellipse(FakeMobject):
    pass


class Polygon(FakeMobject):
    pass


class RoundedRectangle(FakeMobject):
    pass


class Square(FakeMobject):
    pass


class Circle(FakeMobject):
    pass


class Text(FakeMobject):
    pass


class Dot(FakeMobject):
    pass


class Line(FakeMobject):
    def __init__(self, start, end, **kwargs):
        self.start = start
        self.end = end
        super().__init__(
            (
                min(start[0], end[0]),
                max(start[0], end[0]),
                min(start[1], end[1]),
                max(start[1], end[1]),
            ),
            fill=0.0,
            stroke=1.0,
            **kwargs,
        )

    def get_start(self):
        return [self.start[0], self.start[1], 0.0]

    def get_end(self):
        return [self.end[0], self.end[1], 0.0]


class CurvedLine(Line):
    def get_start(self):
        raise TypeError("curved geometry is unsupported")


class CountingLine(Line):
    def __init__(self, start, end, **kwargs):
        super().__init__(start, end, **kwargs)
        self.start_calls = 0
        self.end_calls = 0

    def get_start(self):
        self.start_calls += 1
        return super().get_start()

    def get_end(self):
        self.end_calls += 1
        return super().get_end()


class SceneLike:
    def __init__(self, *mobjects):
        self.mobjects = list(mobjects)


class LayoutGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_manim = sys.modules.get("manim")
        sys.modules["manim"] = types.SimpleNamespace(
            config=types.SimpleNamespace(frame_width=20.0, frame_height=12.0)
        )
        cls.visible = load_module(
            "visible_layout_audit_test",
            SKILL_ROOT / "scripts" / "visible_layout_audit.py",
        )
        cls.runner = load_module(
            "run_layout_audit_test",
            SKILL_ROOT / "scripts" / "run_layout_audit.py",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.previous_manim is None:
            sys.modules.pop("manim", None)
        else:
            sys.modules["manim"] = cls.previous_manim

    def audit(self, *mobjects, graph_roots=()):
        return self.visible.audit_scene_visible_mobjects(
            SceneLike(*mobjects),
            context="ExampleScene:final",
            graph_roots=graph_roots,
        )

    def relations(self, result, severity=None):
        return [
            finding.relation
            for finding in result.findings
            if severity is None or finding.severity == severity
        ]

    @staticmethod
    def graph_node(position, *, half_extent=0.28):
        x, y = position
        shape = Circle((x - half_extent, x + half_extent, y - half_extent, y + half_extent))
        label = Text((x - 0.11, x + 0.11, y - 0.11, y + 0.11))
        return VGroup(shape, label)

    @staticmethod
    def graph_edge_clear_of_node_boxes(first, second, *, half_extent=0.28, gap=0.06):
        dx = second[0] - first[0]
        dy = second[1] - first[1]
        length = math.hypot(dx, dy)
        unit_x, unit_y = dx / length, dy / length
        trim = (half_extent + gap) / max(abs(unit_x), abs(unit_y))
        if 2 * trim >= length:
            raise ValueError("graph nodes are too close for the requested edge clearance")
        return Line(
            (first[0] + unit_x * trim, first[1] + unit_y * trim),
            (second[0] - unit_x * trim, second[1] - unit_y * trim),
        )

    @staticmethod
    def point_to_line_segment_distance(point, line):
        start, end = line.start, line.end
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        projection = (
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
        )
        projection = max(0.0, min(1.0, projection))
        closest = (start[0] + projection * dx, start[1] + projection * dy)
        return math.hypot(point[0] - closest[0], point[1] - closest[1])

    def johnson_super_source_fixture(self):
        original_positions = [
            (0.8, 2.4),
            (3.0, 2.8),
            (4.5, 0.8),
            (3.2, -2.3),
            (0.8, -2.4),
            (-0.2, 0.0),
        ]
        super_source = (-5.0, 0.0)
        positions = original_positions + [super_source]
        original_edges = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 5),
            (5, 0),
            (0, 3),
            (1, 4),
        ]
        super_source_index = len(original_positions)
        edge_specs = original_edges + [
            (super_source_index, target_index)
            for target_index in range(len(original_positions))
        ]
        edges = [
            self.graph_edge_clear_of_node_boxes(positions[first], positions[second])
            for first, second in edge_specs
        ]
        nodes = [self.graph_node(position) for position in positions]
        return positions, edges, VGroup(VGroup(*edges), *nodes)

    def test_one_visible_warning_makes_gate_fail(self) -> None:
        failures = self.runner.gate_failures(
            visible_errors=0,
            visible_warnings=1,
            checkpoints=["initial", "beat:compare", "final"],
            require_adapter=True,
        )
        self.assertEqual(failures, ["1 unresolved visible layout warning(s)"])

    def test_proper_text_containment_has_no_finding(self) -> None:
        panel = Rectangle((-2.0, 2.0, -1.0, 1.0))
        label = Text((-1.0, 1.0, -0.4, 0.4))
        result = self.audit(VGroup(panel, label))
        self.assertEqual(result.findings, [])

    def test_heading_spilling_past_sibling_panel_warns(self) -> None:
        panel = Rectangle((-1.0, 1.0, -1.0, 1.0))
        heading = Text((-1.5, 1.5, 0.2, 0.8))
        result = self.audit(VGroup(panel, heading))
        self.assertIn("overlap", self.relations(result, "WARNING"))

    def test_non_graph_object_colliding_with_graph_remains_strict(self) -> None:
        edge = Line((-1.0, -1.0), (1.0, 1.0))
        graph = VGroup(edge)
        card = Rectangle((-0.4, 0.4, -0.4, 0.4))
        result = self.audit(graph, card, graph_roots=[(graph, "g")])
        self.assertTrue(result.warnings)

    def test_descendants_of_different_graph_roots_remain_strict(self) -> None:
        first = Line((-1.0, -1.0), (1.0, 1.0))
        second = Line((-1.0, 1.0), (1.0, -1.0))
        first_root, second_root = VGroup(first), VGroup(second)
        result = self.audit(
            first_root,
            second_root,
            graph_roots=[(first_root, "one"), (second_root, "two")],
        )
        self.assertIn("overlap", self.relations(result, "WARNING"))

    def test_same_graph_shared_endpoint_has_no_finding(self) -> None:
        first = Line((-1.0, 0.0), (0.0, 0.0))
        second = Line((0.0, 0.0), (1.0, 1.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.findings, [])
        self.assertEqual(result.narrow_phase_checks, 1)

    def test_same_graph_transverse_crossing_has_no_finding(self) -> None:
        first = Line((-1.0, -1.0), (1.0, 1.0))
        second = Line((-1.0, 1.0), (1.0, -1.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.findings, [])
        self.assertEqual(result.narrow_phase_checks, 1)

    def test_same_graph_overlapping_aabbs_without_intersection_have_no_finding(self) -> None:
        first = Line((0.0, 0.0), (2.0, 2.0))
        second = Line((0.0, 1.5), (0.4, 1.9))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.findings, [])
        self.assertEqual(result.narrow_phase_checks, 1)

    def test_same_graph_collinear_overlap_is_best_effort_info(self) -> None:
        first = Line((0.0, 0.0), (2.0, 2.0))
        second = Line((1.0, 1.0), (3.0, 3.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("same-graph-collinear-overlap", self.relations(result, "INFO"))
        self.assertEqual(result.warnings, [])

    def test_same_graph_collinear_overlap_wins_over_shared_endpoint(self) -> None:
        first = Line((0.0, 0.0), (2.0, 2.0))
        second = Line((1.0, 1.0), (2.0, 2.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("same-graph-collinear-overlap", self.relations(result, "INFO"))
        self.assertEqual(result.warnings, [])

    def test_dense_heptagon_complete_graph_has_no_line_false_positives(self) -> None:
        positions = [
            (3.6 * math.cos(2 * math.pi * index / 7), 3.6 * math.sin(2 * math.pi * index / 7))
            for index in range(7)
        ]
        edges = [
            Line(positions[first], positions[second])
            for first in range(len(positions))
            for second in range(first + 1, len(positions))
        ]
        root = VGroup(*edges)
        result = self.audit(root, graph_roots=[(root, "complete K7")])
        self.assertEqual(result.warnings, [])
        self.assertGreater(result.narrow_phase_checks, 0)

    def test_complete_bipartite_graph_with_nodes_has_no_false_positives(self) -> None:
        left = [(-4.0, y) for y in (-3.0, -1.0, 1.0, 3.0)]
        right = [(4.0, y) for y in (-3.0, -1.0, 1.0, 3.0)]
        edges = [
            self.graph_edge_clear_of_node_boxes(first, second)
            for first in left
            for second in right
        ]
        nodes = [self.graph_node(position) for position in left + right]
        root = VGroup(VGroup(*edges), *nodes)
        result = self.audit(root, graph_roots=[(root, "complete K4,4")])
        self.assertEqual(result.warnings, [])
        self.assertGreater(result.narrow_phase_checks, 0)

    def test_five_by_five_grid_with_nodes_has_no_false_positives(self) -> None:
        coordinates = (-4.0, -2.0, 0.0, 2.0, 4.0)
        positions = [(x, y) for y in coordinates for x in coordinates]
        horizontal_edges = [
            self.graph_edge_clear_of_node_boxes((coordinates[x], y), (coordinates[x + 1], y))
            for y in coordinates
            for x in range(len(coordinates) - 1)
        ]
        vertical_edges = [
            self.graph_edge_clear_of_node_boxes((x, coordinates[y]), (x, coordinates[y + 1]))
            for x in coordinates
            for y in range(len(coordinates) - 1)
        ]
        nodes = [self.graph_node(position) for position in positions]
        root = VGroup(VGroup(*(horizontal_edges + vertical_edges)), *nodes)
        result = self.audit(root, graph_roots=[(root, "5x5 grid")])
        self.assertEqual(result.warnings, [])
        self.assertNotIn("same-graph-collinear-overlap", self.relations(result))

    def test_johnson_super_source_fixture_has_real_line_node_clearance(self) -> None:
        positions, edges, _root = self.johnson_super_source_fixture()
        # This is the semantic oracle for the probe: every drawn segment has
        # real geometric clearance from every node circle, including its own
        # endpoint nodes.  Any line/node warning below is therefore an AABB
        # false positive rather than an intentional edge contact.
        for edge in edges:
            for position in positions:
                self.assertGreater(self.point_to_line_segment_distance(position, edge), 0.28)

    def test_johnson_super_source_edges_do_not_false_positive_against_unrelated_nodes(self) -> None:
        _positions, _edges, root = self.johnson_super_source_fixture()
        result = self.audit(root, graph_roots=[(root, "Johnson super-source augmentation")])
        self.assertEqual(result.warnings, [])
        self.assertIn("overlap", self.relations(result, "INFO"))
        self.assertIn("unexpected-containment", self.relations(result, "INFO"))

    def test_graph_line_versus_non_graph_line_remains_strict(self) -> None:
        graph_line = Line((-1.0, -1.0), (1.0, 1.0))
        other_line = Line((-1.0, 1.0), (1.0, -1.0))
        root = VGroup(graph_line)
        result = self.audit(root, other_line, graph_roots=[(root, "g")])
        self.assertIn("overlap", self.relations(result, "WARNING"))

    def test_same_graph_line_versus_text_is_best_effort(self) -> None:
        edge = Line((-1.0, -1.0), (1.0, 1.0))
        label = Text((-0.3, 0.3, -0.3, 0.3))
        root = VGroup(edge, label)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.warnings, [])
        self.assertIn("unexpected-containment", self.relations(result, "INFO"))

    def test_same_graph_line_versus_node_is_best_effort(self) -> None:
        edge = Line((-1.0, 0.0), (1.0, 0.0))
        node = Circle((-0.3, 0.3, -0.3, 0.3))
        root = VGroup(edge, node)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.warnings, [])
        self.assertIn("overlap", self.relations(result, "INFO"))

    def test_same_graph_overlapping_circle_nodes_warn(self) -> None:
        first = Circle((-0.7, 0.3, -0.5, 0.5))
        second = Circle((-0.3, 0.7, -0.5, 0.5))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("same-graph-node-overlap", self.relations(result, "WARNING"))
        self.assertEqual(result.narrow_phase_checks, 1)

    def test_same_graph_overlapping_common_node_shapes_warn(self) -> None:
        for shape_type in (Ellipse, Polygon, Rectangle, RoundedRectangle, Square):
            with self.subTest(shape_type=shape_type.__name__):
                first = Circle((-0.7, 0.3, -0.5, 0.5))
                second = shape_type((-0.3, 0.7, -0.5, 0.5))
                root = VGroup(first, second)
                result = self.audit(root, graph_roots=[(root, "g")])
                self.assertIn("same-graph-node-overlap", self.relations(result, "WARNING"))

    def test_same_graph_node_containment_precedes_node_overlap(self) -> None:
        highlight = Circle((-1.0, 1.0, -1.0, 1.0))
        node = Circle((-0.4, 0.4, -0.4, 0.4))
        root = VGroup(highlight, node)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertNotIn("same-graph-node-overlap", self.relations(result))
        self.assertEqual(result.findings, [])

    def test_same_graph_node_containment_across_peer_groups_warns(self) -> None:
        highlight = VGroup(Circle((-1.0, 1.0, -1.0, 1.0)))
        node = VGroup(Circle((-0.4, 0.4, -0.4, 0.4)))
        root = VGroup(highlight, node)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("unexpected-containment", self.relations(result, "WARNING"))

    def test_same_graph_circle_aabbs_can_overlap_without_node_overlap(self) -> None:
        first = Circle((-1.0, 1.0, -1.0, 1.0))
        second = Circle((0.5, 2.5, 0.5, 2.5))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertNotIn("same-graph-node-overlap", self.relations(result))
        self.assertEqual(result.narrow_phase_checks, 1)

    def test_same_graph_tangent_circle_nodes_do_not_warn(self) -> None:
        first = Circle((-1.0, 1.0, -1.0, 1.0))
        second = Circle((1.0, 3.0, -1.0, 1.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertNotIn("same-graph-node-overlap", self.relations(result))

    def test_non_circular_circle_node_falls_back_to_strict_warning(self) -> None:
        first = Circle((-1.0, 1.0, -0.5, 0.5))
        second = Circle((-0.5, 1.5, -0.5, 0.5))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("same-graph-node-overlap", self.relations(result, "WARNING"))

    def test_same_graph_text_occlusion_warns(self) -> None:
        text = Text((-1.0, 1.0, -0.4, 0.4))
        cover = Rectangle((-1.5, 1.5, -0.8, 0.8))
        root = VGroup(text, cover)
        result = self.audit(root, graph_roots=[(root, "annotated graph")])
        self.assertIn("text-occlusion", self.relations(result, "WARNING"))

    def test_sparse_graph_root_aabb_does_not_create_container_finding(self) -> None:
        first = Line((-3.0, -3.0), (-2.0, -2.0))
        second = Line((2.0, 2.0), (3.0, 3.0))
        root = VGroup(first, second)
        card = Rectangle((-0.5, 0.5, -0.5, 0.5))
        result = self.audit(root, card, graph_roots=[(root, "g")])
        self.assertEqual(result.warnings, [])

    def test_absent_registered_graph_root_is_inactive(self) -> None:
        root = VGroup(Line((-1.0, -1.0), (1.0, 1.0)))
        result = self.audit(Rectangle((2.0, 3.0, 2.0, 3.0)), graph_roots=[(root, "retired")])
        self.assertEqual(result.errors, [])
        self.assertNotIn("missing-graph-root", self.relations(result))

    def test_detached_graph_children_return_to_strict_rules(self) -> None:
        first = Line((-1.0, -1.0), (1.0, 1.0))
        second = Line((-1.0, 1.0), (1.0, -1.0))
        root = VGroup(first, second)
        result = self.audit(first, second, graph_roots=[(root, "retired")])
        self.assertIn("overlap", self.relations(result, "WARNING"))

    def test_independent_peer_containment_warns(self) -> None:
        panel = Rectangle((-2.0, 2.0, -1.0, 1.0))
        content = Text((-1.0, 1.0, -0.4, 0.4))
        result = self.audit(panel, content)
        self.assertIn("unexpected-containment", self.relations(result, "WARNING"))

    def test_independent_peer_container_containment_warns(self) -> None:
        outer = VGroup(Rectangle((-2.0, 2.0, -1.0, 1.0)))
        inner = VGroup(Text((-1.0, 1.0, -0.4, 0.4)))
        result = self.audit(outer, inner)
        self.assertIn("unexpected-containment", self.relations(result, "WARNING"))

    def test_peer_container_containment_stays_strict_under_common_wrapper(self) -> None:
        outer = VGroup(Rectangle((-2.0, 2.0, -1.0, 1.0)))
        inner = VGroup(Text((-1.0, 1.0, -0.4, 0.4)))
        result = self.audit(VGroup(outer, inner))
        self.assertIn("unexpected-containment", self.relations(result, "WARNING"))

    def test_legitimate_nested_containment_does_not_warn(self) -> None:
        panel = Rectangle((-2.0, 2.0, -1.0, 1.0))
        content = Text((-1.0, 1.0, -0.4, 0.4))
        result = self.audit(VGroup(panel, VGroup(content)))
        self.assertEqual(result.findings, [])

    def test_opaque_object_above_text_warns(self) -> None:
        text = Text((-1.0, 1.0, -0.4, 0.4))
        cover = Rectangle((-1.5, 1.5, -0.8, 0.8))
        result = self.audit(VGroup(text, cover))
        self.assertIn("text-occlusion", self.relations(result, "WARNING"))

    def test_higher_z_index_object_above_text_warns_despite_family_order(self) -> None:
        cover = Rectangle((-1.5, 1.5, -0.8, 0.8), z_index=2.0)
        text = Text((-1.0, 1.0, -0.4, 0.4), z_index=1.0)
        result = self.audit(VGroup(cover, text))
        self.assertIn("text-occlusion", self.relations(result, "WARNING"))

    def test_text_above_own_background_passes(self) -> None:
        panel = Rectangle((-2.0, 2.0, -1.0, 1.0))
        text = Text((-1.0, 1.0, -0.4, 0.4))
        result = self.audit(VGroup(panel, text))
        self.assertNotIn("text-occlusion", self.relations(result, "WARNING"))

    def test_transparent_object_does_not_occlude_text(self) -> None:
        text = Text((-1.0, 1.0, -0.4, 0.4))
        transparent = Rectangle((-1.5, 1.5, -0.8, 0.8), fill=0.0, stroke=0.0)
        result = self.audit(VGroup(text, transparent))
        self.assertNotIn("text-occlusion", self.relations(result, "WARNING"))

    def test_aabb_separated_lines_skip_narrow_phase(self) -> None:
        first = Line((-3.0, -3.0), (-2.0, -2.0))
        second = Line((2.0, 2.0), (3.0, 3.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.narrow_phase_checks, 0)

    def test_line_geometry_is_cached_within_checkpoint(self) -> None:
        shared = CountingLine((-2.0, 0.0), (2.0, 0.0))
        first = CountingLine((-1.0, -1.0), (-1.0, 1.0))
        second = CountingLine((1.0, -1.0), (1.0, 1.0))
        root = VGroup(shared, first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertEqual(result.narrow_phase_checks, 2)
        self.assertEqual((shared.start_calls, shared.end_calls), (1, 1))

    def test_ambiguous_multi_root_membership_is_error(self) -> None:
        edge = Line((-1.0, -1.0), (1.0, 1.0))
        inner = VGroup(edge)
        outer = VGroup(inner)
        result = self.audit(outer, graph_roots=[(outer, "outer"), (inner, "inner")])
        self.assertIn("ambiguous-graph-membership", self.relations(result, "ERROR"))
        self.assertTrue(
            self.runner.gate_failures(
                visible_errors=len(result.errors),
                visible_warnings=len(result.warnings),
                checkpoints=["initial", "beat:x", "final"],
                require_adapter=True,
            )
        )

    def test_shared_leaf_in_peer_graph_roots_is_ambiguous(self) -> None:
        edge = Line((-1.0, -1.0), (1.0, 1.0))
        first_root = VGroup(edge)
        second_root = VGroup(edge)
        result = self.audit(
            first_root,
            second_root,
            graph_roots=[(first_root, "first"), (second_root, "second")],
        )
        self.assertIn("ambiguous-graph-membership", self.relations(result, "ERROR"))
        self.assertIn("ambiguous-structural-parent", self.relations(result, "ERROR"))

    def test_shared_leaf_in_peer_non_graph_groups_has_ambiguous_parent(self) -> None:
        shared = Circle((-0.5, 0.5, -0.5, 0.5))
        result = self.audit(VGroup(shared), VGroup(shared))
        finding = next(
            finding for finding in result.findings if finding.relation == "ambiguous-structural-parent"
        )
        self.assertEqual(finding.severity, "ERROR")
        self.assertFalse(finding.waivable)

    def test_shared_subgroup_has_ambiguous_parent(self) -> None:
        shared = VGroup(Circle((-0.5, 0.5, -0.5, 0.5)))
        result = self.audit(VGroup(shared), VGroup(shared))
        self.assertIn("ambiguous-structural-parent", self.relations(result, "ERROR"))

    def test_nested_single_owner_structure_is_not_ambiguous(self) -> None:
        result = self.audit(VGroup(VGroup(Circle((-0.5, 0.5, -0.5, 0.5)))))
        self.assertNotIn("ambiguous-structural-parent", self.relations(result))

    def test_frame_overflow_is_non_waivable(self) -> None:
        result = self.audit(Rectangle((-11.0, -9.0, -0.5, 0.5)))
        overflow = next(finding for finding in result.findings if finding.relation == "frame-overflow-left")
        self.assertEqual(overflow.severity, "ERROR")
        self.assertFalse(overflow.waivable)

    def test_unsupported_same_graph_curve_falls_back_to_best_effort_aabb(self) -> None:
        first = CurvedLine((-1.0, -1.0), (1.0, 1.0))
        second = Line((-1.0, 1.0), (1.0, -1.0))
        root = VGroup(first, second)
        result = self.audit(root, graph_roots=[(root, "g")])
        self.assertIn("overlap", self.relations(result, "INFO"))
        self.assertEqual(result.warnings, [])

    def test_valid_exact_exception_accepts_only_matching_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "scene.py"
            source.write_text("# scene\n", encoding="utf-8")
            source_hash = self.runner.sha256(source)
            exception_path = Path(temp_dir) / "exceptions.json"
            exception_path.write_text(
                json.dumps(
                    {
                        "exceptions": [
                            {
                                "scene_class": "ExampleScene",
                                "checkpoint": "ExampleScene:final",
                                "objects": ["Rectangle[0]", "Text[1]"],
                                "relation": "overlap",
                                "explanation": "Required overlay.",
                                "supporting_reference": "confirmed_requirements.md#overlay",
                                "source_sha256": source_hash,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                visible_exceptions=str(exception_path),
                visible_final_only=False,
                visible_frame_margin=0.0,
                visible_containment_padding=1e-3,
                visible_overlap_epsilon=1e-6,
                visible_include_descendants=False,
                visible_report_level="warning",
                visible_max_reports=10,
                render_profile=None,
            )
            accumulator = self.runner.VisibleAuditAccumulator(args, "ExampleScene", source)
            accepted = self.visible.VisibleFinding(
                "WARNING",
                "overlap",
                ("Rectangle[0]", "Text[1]"),
                "collision",
            )
            remaining = self.visible.VisibleFinding(
                "WARNING",
                "overlap",
                ("Rectangle[2]", "Text[3]"),
                "other collision",
            )
            accumulator.entries = [
                {"context": "ExampleScene:final", "finding": accepted},
                {"context": "ExampleScene:final", "finding": remaining},
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                accumulator.finalize()
            report_path = Path(temp_dir) / "report.json"
            accumulator.write_report(report_path, "FAIL", [], ["1 unresolved warning"])
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertTrue(accepted.accepted)
            self.assertEqual(accepted.exception_index, 0)
            self.assertFalse(remaining.accepted)
            self.assertEqual(accumulator.accepted_warning_count, 1)
            self.assertEqual(accumulator.warning_count, 1)
            self.assertEqual(report["summary"]["accepted_warnings"], 1)
            self.assertEqual(report["summary"]["unresolved_warnings"], 1)
            self.assertEqual(report["exception_file_sha256"], self.runner.sha256(exception_path))
            self.assertTrue(report["findings"][0]["accepted"])

    def test_invalid_exceptions_fail_loud(self) -> None:
        source_hash = "a" * 64
        finding = self.visible.VisibleFinding("WARNING", "overlap", ("a", "b"), "collision")
        entries = [{"context": "ExampleScene:final", "finding": finding}]
        base = {
            "scene_class": "ExampleScene",
            "checkpoint": "ExampleScene:final",
            "objects": ["a", "b"],
            "relation": "overlap",
            "explanation": "Required.",
            "supporting_reference": "confirmed_requirements.md#item",
            "source_sha256": source_hash,
        }
        variants = [
            {**base, "source_sha256": "b" * 64},
            {**base, "objects": ["*", "b"]},
            {**base, "scene_class": "OtherScene"},
            {**base, "checkpoint": "ExampleScene:other"},
            {**base, "relation": "frame-overflow-left"},
        ]
        for record in variants:
            with self.subTest(record=record):
                errors = self.runner.apply_warning_exceptions(
                    entries,
                    [record],
                    scene_class="ExampleScene",
                    source_sha256=source_hash,
                )
                self.assertTrue(errors)
                finding.accepted = False
                finding.exception_index = None

    def test_report_cap_never_changes_gate_or_machine_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "scene.py"
            source.write_text("# scene\n", encoding="utf-8")
            report_path = Path(temp_dir) / "report.json"
            args = argparse.Namespace(
                visible_exceptions=None,
                visible_final_only=False,
                visible_frame_margin=0.0,
                visible_containment_padding=1e-3,
                visible_overlap_epsilon=1e-6,
                visible_include_descendants=False,
                visible_report_level="warning",
                visible_max_reports=1,
            )
            accumulator = self.runner.VisibleAuditAccumulator(args, "ExampleScene", source)
            accumulator.entries = [
                {
                    "context": f"ExampleScene:after-play-{index:04d}",
                    "finding": self.visible.VisibleFinding(
                        "WARNING",
                        "overlap",
                        (f"a{index}", f"b{index}"),
                        f"collision {index}",
                    ),
                }
                for index in range(3)
            ]
            accumulator.entries.append(
                {
                    "context": "ExampleScene:final",
                    "finding": self.visible.VisibleFinding(
                        "INFO",
                        "overlap",
                        ("graph-a", "graph-b"),
                        "same-graph best-effort collision",
                    ),
                }
            )
            with contextlib.redirect_stdout(io.StringIO()):
                accumulator.finalize()
            failures = self.runner.gate_failures(
                visible_errors=accumulator.error_count,
                visible_warnings=accumulator.warning_count,
                checkpoints=["initial", "beat:x", "final"],
                require_adapter=True,
            )
            accumulator.write_report(report_path, "FAIL", ["initial", "beat:x", "final"], failures)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(accumulator.warning_count, 3)
            self.assertEqual(accumulator.info_count, 1)
            self.assertEqual(len(report["findings"]), 4)
            self.assertEqual(report["summary"]["unresolved_warnings"], 3)
            self.assertEqual(report["summary"]["infos"], 1)
            self.assertEqual(report["gate_result"], "FAIL")

    def test_required_adapter_needs_initial_beat_and_final_checkpoints(self) -> None:
        failures = self.runner.gate_failures(
            visible_errors=0,
            visible_warnings=0,
            checkpoints=["initial", "final"],
            require_adapter=True,
        )
        self.assertTrue(any("beat" in failure.lower() for failure in failures))

    def test_scene_adapter_records_checkpoint_and_graph_root(self) -> None:
        adapter = load_module(
            "scene_layout_audit_test",
            SKILL_ROOT / "scripts" / "scene_layout_audit.py",
        )
        adapter.reset_layout_audit_checkpoints()
        root = object()
        adapter.register_graph_root(root, "main")
        adapter.LayoutAudit(context="beat:swap").report(raise_on_issue=True)
        self.assertEqual(adapter.get_layout_audit_checkpoints(), ["beat:swap"])
        self.assertEqual(adapter.get_layout_audit_graph_roots(), [(root, "main")])


if __name__ == "__main__":
    unittest.main()
