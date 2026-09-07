from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations
from math import hypot
from typing import Iterable, Sequence

from manim import config


CONTAINER_TYPE_NAMES = {"Group", "VGroup"}
LINE_TYPE_NAMES = {"Arrow", "DashedLine", "DoubleArrow", "Line"}
NODE_SHAPE_TYPE_NAMES = {
    "Circle",
    "Ellipse",
    "Polygon",
    "Rectangle",
    "RoundedRectangle",
    "Square",
}
TEXT_TYPE_NAMES = {"MarkupText", "MathTex", "Paragraph", "Tex", "Text"}
VISUAL_BOUNDARY_TYPE_NAMES = {
    "Circle",
    "Ellipse",
    "Polygon",
    "Rectangle",
    "RoundedRectangle",
    "Square",
}
EPSILON = 1e-6


@dataclass(frozen=True)
class Bounds:
    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def format(self) -> str:
        return (
            f"left={self.left:.2f}, right={self.right:.2f}, "
            f"bottom={self.bottom:.2f}, top={self.top:.2f}"
        )


@dataclass
class VisibleFinding:
    severity: str
    relation: str
    objects: tuple[str, ...]
    message: str
    waivable: bool = True
    accepted: bool = False
    exception_index: int | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["objects"] = list(self.objects)
        return result


@dataclass(frozen=True)
class VisibleItem:
    name: str
    mobject: object
    bounds: Bounds
    structural_ancestors: tuple[object, ...]
    graph_roots: tuple[tuple[object, str | None], ...]
    drawing_order: int


@dataclass
class HierarchyNode:
    name: str
    mobject: object
    bounds: Bounds
    children: list["HierarchyNode"] = field(default_factory=list)
    item: VisibleItem | None = None

    @property
    def is_leaf(self) -> bool:
        return self.item is not None


@dataclass
class VisibleAuditResult:
    context: str
    findings: list[VisibleFinding]
    narrow_phase_checks: int = 0

    @property
    def errors(self) -> list[str]:
        return [finding.message for finding in self.findings if finding.severity == "ERROR"]

    @property
    def warnings(self) -> list[str]:
        return [finding.message for finding in self.findings if finding.severity == "WARNING"]

    @property
    def infos(self) -> list[str]:
        return [finding.message for finding in self.findings if finding.severity == "INFO"]

    def emit(self) -> None:
        prefix = f"[visible-layout:{self.context}]" if self.context else "[visible-layout]"
        for finding in self.findings:
            disposition = " ACCEPTED" if finding.accepted else ""
            print(f"{prefix} {finding.severity}{disposition} {finding.message}")


class _CheckpointAudit:
    def __init__(
        self,
        scene,
        context: str,
        frame_margin: float,
        containment_padding: float,
        overlap_epsilon: float,
        graph_roots: Sequence[tuple[object, str | None]],
    ):
        self.scene = scene
        self.context = context
        self.frame_margin = frame_margin
        self.containment_padding = containment_padding
        self.overlap_epsilon = overlap_epsilon
        self.graph_roots = list(graph_roots)
        self.graph_root_ids = {id(root) for root, _name in self.graph_roots}
        self.bounds_cache: dict[int, Bounds] = {}
        self.segment_cache: dict[int, tuple[tuple[float, float], tuple[float, float]] | None] = {}
        self.membership_index: dict[int, list[tuple[object, str | None]]] = {}
        self.direct_parent_index: dict[int, dict[int | None, str]] = {}
        self.object_path_index: dict[int, str] = {}
        self.seen: set[int] = set()
        self.drawing_order = 0
        self.findings: list[VisibleFinding] = []
        self.narrow_phase_checks = 0

    def run(self) -> VisibleAuditResult:
        for index, mobject in enumerate(self.scene.mobjects):
            self._index_memberships(mobject, f"{type(mobject).__name__}[{index}]", (), set())

        roots: list[HierarchyNode] = []
        for index, mobject in enumerate(self.scene.mobjects):
            node = self._build_node(mobject, f"{type(mobject).__name__}[{index}]", ())
            if node is not None:
                roots.append(node)

        leaves = list(self._iter_leaves(roots))
        self._audit_frame(leaves)
        visible_structure_ids = {
            id(mobject)
            for leaf in leaves
            for mobject in (leaf.mobject, *leaf.structural_ancestors)
        }
        for object_id, parents in self.direct_parent_index.items():
            if object_id in visible_structure_ids and len(parents) > 1:
                name = self.object_path_index[object_id]
                self._add(
                    "ERROR",
                    "ambiguous-structural-parent",
                    (name,),
                    f"{name}: is reachable through multiple direct structural owners "
                    f"({', '.join(parents.values())})",
                    waivable=False,
                )
        for leaf in leaves:
            if len(leaf.graph_roots) > 1:
                names = [name or type(root).__name__ for root, name in leaf.graph_roots]
                self._add(
                    "ERROR",
                    "ambiguous-graph-membership",
                    (leaf.name,),
                    f"{leaf.name}: belongs to multiple registered graph roots ({', '.join(names)})",
                    waivable=False,
                )

        for root in roots:
            self._audit_internal(root)
        for first, second in combinations(roots, 2):
            self._compare_branches(first, second)

        return VisibleAuditResult(
            context=self.context,
            findings=self.findings,
            narrow_phase_checks=self.narrow_phase_checks,
        )

    def _bounds(self, mobject) -> Bounds:
        key = id(mobject)
        if key not in self.bounds_cache:
            self.bounds_cache[key] = get_bounds(mobject)
        return self.bounds_cache[key]

    def _segment(self, mobject) -> tuple[tuple[float, float], tuple[float, float]] | None:
        key = id(mobject)
        if key not in self.segment_cache:
            self.segment_cache[key] = line_segment(mobject)
        return self.segment_cache[key]

    def _index_memberships(
        self,
        mobject,
        path: str,
        structural_ancestors: tuple[object, ...],
        active_path: set[int],
    ) -> None:
        """Index every ancestry path before hierarchy de-duplication.

        Manim mobjects do not have an exclusive parent, so the same leaf or
        subgroup can be referenced by multiple graph wrappers.  A global
        de-duplication pass alone would retain only the first ancestry and
        could incorrectly grant same-graph relaxation.
        """
        object_id = id(mobject)
        if object_id in active_path:
            return

        parent = structural_ancestors[-1] if structural_ancestors else None
        parent_id = id(parent) if parent is not None else None
        parent_name = self.object_path_index.get(parent_id, "<scene>") if parent is not None else "<scene>"
        self.direct_parent_index.setdefault(object_id, {}).setdefault(parent_id, parent_name)
        self.object_path_index.setdefault(object_id, path)

        children = list(getattr(mobject, "submobjects", []) or [])
        is_container = bool(class_names(mobject) & CONTAINER_TYPE_NAMES) or object_id in self.graph_root_ids
        if not is_container:
            indexed = self.membership_index.setdefault(object_id, [])
            for registration in self.graph_roots:
                if registration[0] is mobject or any(
                    registration[0] is ancestor for ancestor in structural_ancestors
                ):
                    if not any(existing[0] is registration[0] for existing in indexed):
                        indexed.append(registration)
            return

        next_path = active_path | {object_id}
        next_ancestors = structural_ancestors + (mobject,)
        for child_index, child in enumerate(children):
            self._index_memberships(
                child,
                f"{path}.{type(child).__name__}[{child_index}]",
                next_ancestors,
                next_path,
            )

    def _build_node(
        self,
        mobject,
        path: str,
        structural_ancestors: tuple[object, ...],
    ) -> HierarchyNode | None:
        object_id = id(mobject)
        if object_id in self.seen:
            return None
        self.seen.add(object_id)

        children = list(getattr(mobject, "submobjects", []) or [])
        is_container = bool(class_names(mobject) & CONTAINER_TYPE_NAMES) or object_id in self.graph_root_ids
        if not is_container:
            if not is_visible_mobject(mobject, self._bounds):
                return None
            item = VisibleItem(
                name=path,
                mobject=mobject,
                bounds=self._bounds(mobject),
                structural_ancestors=structural_ancestors,
                graph_roots=tuple(self.membership_index.get(object_id, ())),
                drawing_order=self.drawing_order,
            )
            self.drawing_order += 1
            return HierarchyNode(path, mobject, item.bounds, item=item)

        next_ancestors = structural_ancestors + (mobject,)
        child_nodes: list[HierarchyNode] = []
        for child_index, child in enumerate(children):
            child_node = self._build_node(
                child,
                f"{path}.{type(child).__name__}[{child_index}]",
                next_ancestors,
            )
            if child_node is not None:
                child_nodes.append(child_node)
        if not child_nodes:
            return None
        return HierarchyNode(path, mobject, self._bounds(mobject), children=child_nodes)

    def _iter_leaves(self, nodes: Iterable[HierarchyNode]) -> Iterable[VisibleItem]:
        for node in nodes:
            if node.item is not None:
                yield node.item
            else:
                yield from self._iter_leaves(node.children)

    def _audit_frame(self, items: Iterable[VisibleItem]) -> None:
        half_width = config.frame_width / 2
        half_height = config.frame_height / 2
        for item in items:
            bounds = item.bounds
            checks = (
                (bounds.left < -half_width + self.frame_margin, "frame-overflow-left", "exceeds left frame"),
                (bounds.right > half_width - self.frame_margin, "frame-overflow-right", "exceeds right frame"),
                (bounds.bottom < -half_height + self.frame_margin, "frame-overflow-bottom", "exceeds bottom frame"),
                (bounds.top > half_height - self.frame_margin, "frame-overflow-top", "exceeds top frame"),
            )
            for failed, relation, text in checks:
                if failed:
                    self._add(
                        "ERROR",
                        relation,
                        (item.name,),
                        f"{item.name}: {text} ({bounds.format()})",
                        waivable=False,
                    )

    def _audit_internal(self, node: HierarchyNode) -> None:
        if node.is_leaf:
            return
        for first, second in combinations(node.children, 2):
            self._compare_branches(first, second)
        for child in node.children:
            self._audit_internal(child)

    def _compare_branches(self, first: HierarchyNode, second: HierarchyNode) -> None:
        if not aabb_intersects(first.bounds, second.bounds, self.overlap_epsilon):
            return
        if first.item is not None and second.item is not None:
            self._audit_leaf_pair(first.item, second.item)
            return
        if first.item is None:
            for child in first.children:
                self._compare_branches(child, second)
            return
        for child in second.children:
            self._compare_branches(first, child)

    def _audit_leaf_pair(self, first: VisibleItem, second: VisibleItem) -> None:
        same_graph = self._same_unambiguous_graph(first, second)
        finding_severity = "INFO" if same_graph is not None else "WARNING"
        if same_graph is not None and is_line_like(first.mobject) and is_line_like(second.mobject):
            self._audit_same_graph_lines(first, second, same_graph)
        elif same_graph is not None and is_node_shape(first.mobject) and is_node_shape(second.mobject):
            self._audit_same_graph_nodes(first, second, same_graph)
        else:
            self._audit_strict_pair(first, second, finding_severity=finding_severity)
        self._audit_text_occlusion(first, second, finding_severity="WARNING")

    @staticmethod
    def _same_unambiguous_graph(first: VisibleItem, second: VisibleItem) -> tuple[object, str | None] | None:
        if len(first.graph_roots) != 1 or len(second.graph_roots) != 1:
            return None
        if first.graph_roots[0][0] is second.graph_roots[0][0]:
            return first.graph_roots[0]
        return None

    def _audit_same_graph_lines(
        self,
        first: VisibleItem,
        second: VisibleItem,
        graph_root: tuple[object, str | None],
    ) -> None:
        first_segment = self._segment(first.mobject)
        second_segment = self._segment(second.mobject)
        if first_segment is None or second_segment is None:
            self._audit_strict_pair(first, second, finding_severity="INFO")
            return

        self.narrow_phase_checks += 1
        intersection = classify_segment_intersection(first_segment, second_segment, self.overlap_epsilon)
        if intersection in {"shared-endpoint", "transverse-crossing"}:
            return

        graph_name = graph_root[1] or type(graph_root[0]).__name__
        if intersection == "collinear-overlap":
            self._add(
                "INFO",
                "same-graph-collinear-overlap",
                (first.name, second.name),
                f"{first.name}: overlaps {second.name} collinearly in graph {graph_name!r}",
            )
        elif intersection == "unsupported-contact":
            self._add(
                "INFO",
                "same-graph-line-contact",
                (first.name, second.name),
                f"{first.name}: has unsupported line contact with {second.name} in graph {graph_name!r}",
            )

    def _audit_same_graph_nodes(
        self,
        first: VisibleItem,
        second: VisibleItem,
        graph_root: tuple[object, str | None],
    ) -> None:
        relation = classify_pair(first.bounds, second.bounds, self.containment_padding, self.overlap_epsilon)
        if relation in {"first-inside-second", "second-inside-first"}:
            if same_structural_parent(first, second):
                return
            self._audit_strict_pair(first, second, finding_severity="WARNING")
            return
        if relation != "overlap":
            return

        if not (is_circle_node(first.mobject) and is_circle_node(second.mobject)):
            self._add_same_graph_node_overlap(first, second, graph_root)
            return

        first_circle = circle_geometry(first.bounds, self.overlap_epsilon)
        second_circle = circle_geometry(second.bounds, self.overlap_epsilon)
        if first_circle is None or second_circle is None:
            self._add_same_graph_node_overlap(first, second, graph_root)
            return

        self.narrow_phase_checks += 1
        first_center, first_radius = first_circle
        second_center, second_radius = second_circle
        center_distance = hypot(
            first_center[0] - second_center[0],
            first_center[1] - second_center[1],
        )
        penetration = first_radius + second_radius - center_distance
        if penetration <= self.overlap_epsilon:
            return

        self._add_same_graph_node_overlap(
            first,
            second,
            graph_root,
            detail=f"center distance={center_distance:.3f}, radii={first_radius:.3f}+{second_radius:.3f}",
        )

    def _add_same_graph_node_overlap(
        self,
        first: VisibleItem,
        second: VisibleItem,
        graph_root: tuple[object, str | None],
        detail: str | None = None,
    ) -> None:
        graph_name = graph_root[1] or type(graph_root[0]).__name__
        detail_suffix = f" ({detail})" if detail else ""
        self._add(
            "WARNING",
            "same-graph-node-overlap",
            (first.name, second.name),
            f"{first.name}: node shape overlaps {second.name} in graph {graph_name!r}{detail_suffix}",
        )

    def _audit_strict_pair(
        self,
        first: VisibleItem,
        second: VisibleItem,
        *,
        finding_severity: str = "WARNING",
    ) -> None:
        relation = classify_pair(first.bounds, second.bounds, self.containment_padding, self.overlap_epsilon)
        if relation == "separate":
            if (is_line_like(first.mobject) or is_line_like(second.mobject)) and aabb_intersects(
                first.bounds, second.bounds, self.overlap_epsilon
            ):
                self._add(
                    finding_severity,
                    "overlap",
                    (first.name, second.name),
                    f"{first.name}: has a strict AABB collision with {second.name} "
                    f"({first.bounds.format()}; {second.bounds.format()})",
                )
            return
        if relation == "overlap":
            self._add(
                finding_severity,
                "overlap",
                (first.name, second.name),
                f"{first.name}: overlaps {second.name} ({first.bounds.format()}; {second.bounds.format()})",
            )
            return

        inner, outer = (first, second) if relation == "first-inside-second" else (second, first)
        if is_owned_containment(inner, outer, self.graph_root_ids):
            return
        else:
            self._add(
                finding_severity,
                "unexpected-containment",
                (inner.name, outer.name),
                f"{inner.name}: is unexpectedly contained by {outer.name} ({inner.bounds.format()}; {outer.bounds.format()})",
            )

    def _audit_text_occlusion(
        self,
        first: VisibleItem,
        second: VisibleItem,
        *,
        finding_severity: str = "WARNING",
    ) -> None:
        first_text = is_text_like(first.mobject)
        second_text = is_text_like(second.mobject)
        if first_text == second_text:
            return
        text_item, other = (first, second) if first_text else (second, first)
        if not is_occluding(other.mobject):
            return
        if rendered_above(text_item, other):
            return
        self._add(
            finding_severity,
            "text-occlusion",
            (text_item.name, other.name),
            f"{text_item.name}: is rendered below overlapping {other.name}",
        )

    def _add(
        self,
        severity: str,
        relation: str,
        objects: tuple[str, ...],
        message: str,
        waivable: bool = True,
    ) -> None:
        self.findings.append(VisibleFinding(severity, relation, objects, message, waivable=waivable))


def audit_scene_visible_mobjects(
    scene,
    context: str = "visible",
    frame_margin: float = 0.0,
    containment_padding: float = 1e-3,
    overlap_epsilon: float = EPSILON,
    include_descendants: bool = False,
    graph_roots: Sequence[tuple[object, str | None]] = (),
) -> VisibleAuditResult:
    # Structural containers are always traversed. Non-container families
    # (notably Text glyphs and Arrow tips) deliberately remain atomic leaves.
    del include_descendants
    return _CheckpointAudit(
        scene,
        context,
        frame_margin,
        containment_padding,
        overlap_epsilon,
        graph_roots,
    ).run()


def collect_visible_items(mobjects: Iterable[object], include_descendants: bool = False) -> list[VisibleItem]:
    del include_descendants
    scene = type("SceneLike", (), {"mobjects": list(mobjects)})()
    auditor = _CheckpointAudit(scene, "collect", 0.0, 1e-3, EPSILON, [])
    hierarchy = [
        node
        for index, mob in enumerate(scene.mobjects)
        if (node := auditor._build_node(mob, f"{type(mob).__name__}[{index}]", ())) is not None
    ]
    return list(auditor._iter_leaves(hierarchy))


def is_visible_mobject(mobject, bounds_getter=None) -> bool:
    try:
        bounds = bounds_getter(mobject) if bounds_getter is not None else get_bounds(mobject)
    except Exception:
        return False
    if bounds.width <= EPSILON and bounds.height <= EPSILON:
        return False
    return is_occluding(mobject)


def get_bounds(mobject) -> Bounds:
    return Bounds(
        left=float(mobject.get_left()[0]),
        right=float(mobject.get_right()[0]),
        bottom=float(mobject.get_bottom()[1]),
        top=float(mobject.get_top()[1]),
    )


def classify_pair(first: Bounds, second: Bounds, containment_padding: float, overlap_epsilon: float) -> str:
    if is_strictly_inside(first, second, containment_padding):
        return "first-inside-second"
    if is_strictly_inside(second, first, containment_padding):
        return "second-inside-first"
    x_overlap = min(first.right, second.right) - max(first.left, second.left)
    y_overlap = min(first.top, second.top) - max(first.bottom, second.bottom)
    return "overlap" if x_overlap > overlap_epsilon and y_overlap > overlap_epsilon else "separate"


def aabb_intersects(first: Bounds, second: Bounds, epsilon: float) -> bool:
    return not (
        first.right < second.left - epsilon
        or second.right < first.left - epsilon
        or first.top < second.bottom - epsilon
        or second.top < first.bottom - epsilon
    )


def is_strictly_inside(inner: Bounds, outer: Bounds, padding: float) -> bool:
    return (
        inner.area < outer.area
        and inner.left > outer.left + padding
        and inner.right < outer.right - padding
        and inner.bottom > outer.bottom + padding
        and inner.top < outer.top - padding
    )


def is_owned_containment(inner: VisibleItem, outer: VisibleItem, graph_root_ids: set[int]) -> bool:
    if not is_visual_boundary(outer.mobject):
        return False
    common = [
        ancestor
        for ancestor in inner.structural_ancestors
        if any(ancestor is candidate for candidate in outer.structural_ancestors)
    ]
    if not common or id(common[-1]) in graph_root_ids or not rendered_above(inner, outer):
        return False

    owner = common[-1]
    inner_below_owner = _ancestors_below(inner.structural_ancestors, owner)
    outer_below_owner = _ancestors_below(outer.structural_ancestors, owner)
    # Two distinct structural branches are peer containers, even when an
    # umbrella VGroup makes them share a higher ancestor.  Containment across
    # those branches must remain strict.  One nested content branch is allowed
    # so an expected boundary/content containment can be ignored.
    return not (inner_below_owner and outer_below_owner)


def same_structural_parent(first: VisibleItem, second: VisibleItem) -> bool:
    return bool(
        first.structural_ancestors
        and second.structural_ancestors
        and first.structural_ancestors[-1] is second.structural_ancestors[-1]
    )


def _ancestors_below(ancestors: tuple[object, ...], owner: object) -> tuple[object, ...]:
    for index in range(len(ancestors) - 1, -1, -1):
        if ancestors[index] is owner:
            return ancestors[index + 1 :]
    return ()


def class_names(mobject) -> set[str]:
    return {cls.__name__ for cls in type(mobject).__mro__}


def is_line_like(mobject) -> bool:
    return bool(class_names(mobject) & LINE_TYPE_NAMES)


def is_circle_node(mobject) -> bool:
    return "Circle" in class_names(mobject)


def is_node_shape(mobject) -> bool:
    return bool(class_names(mobject) & NODE_SHAPE_TYPE_NAMES)


def circle_geometry(
    bounds: Bounds,
    tolerance: float,
) -> tuple[tuple[float, float], float] | None:
    if bounds.width <= tolerance or bounds.height <= tolerance:
        return None
    if abs(bounds.width - bounds.height) > tolerance:
        return None
    return (
        ((bounds.left + bounds.right) / 2, (bounds.bottom + bounds.top) / 2),
        (bounds.width + bounds.height) / 4,
    )


def is_text_like(mobject) -> bool:
    return bool(class_names(mobject) & TEXT_TYPE_NAMES)


def is_visual_boundary(mobject) -> bool:
    return bool(class_names(mobject) & VISUAL_BOUNDARY_TYPE_NAMES)


def rendered_above(text: VisibleItem, other: VisibleItem) -> bool:
    text_z = float(getattr(text.mobject, "z_index", 0.0))
    other_z = float(getattr(other.mobject, "z_index", 0.0))
    return text_z > other_z or (text_z == other_z and text.drawing_order > other.drawing_order)


def line_segment(mobject) -> tuple[tuple[float, float], tuple[float, float]] | None:
    try:
        start = mobject.get_start()
        end = mobject.get_end()
        return ((float(start[0]), float(start[1])), (float(end[0]), float(end[1])))
    except Exception:
        return None


def classify_segment_intersection(first, second, epsilon: float) -> str:
    a, b = first
    c, d = second
    ab_c = _cross(a, b, c)
    ab_d = _cross(a, b, d)
    cd_a = _cross(c, d, a)
    cd_b = _cross(c, d, b)
    collinear = all(abs(value) <= epsilon for value in (ab_c, ab_d, cd_a, cd_b))
    if collinear:
        if _collinear_overlap_length(a, b, c, d) > epsilon:
            return "collinear-overlap"
        if any(_points_close(p, q, epsilon) for p in (a, b) for q in (c, d)):
            return "shared-endpoint"
        return "none"
    if any(_points_close(p, q, epsilon) for p in (a, b) for q in (c, d)):
        return "shared-endpoint"
    if ab_c * ab_d < -epsilon and cd_a * cd_b < -epsilon:
        return "transverse-crossing"
    if any(
        abs(cross) <= epsilon and _point_on_segment(point, start, end, epsilon)
        for cross, point, start, end in (
            (ab_c, c, a, b),
            (ab_d, d, a, b),
            (cd_a, a, c, d),
            (cd_b, b, c, d),
        )
    ):
        return "unsupported-contact"
    return "none"


def _cross(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _points_close(first, second, epsilon: float) -> bool:
    return hypot(first[0] - second[0], first[1] - second[1]) <= epsilon


def _point_on_segment(point, start, end, epsilon: float) -> bool:
    return (
        min(start[0], end[0]) - epsilon <= point[0] <= max(start[0], end[0]) + epsilon
        and min(start[1], end[1]) - epsilon <= point[1] <= max(start[1], end[1]) + epsilon
    )


def _collinear_overlap_length(a, b, c, d) -> float:
    axis = 0 if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else 1
    overlap = min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(
        min(a[axis], b[axis]), min(c[axis], d[axis])
    )
    if overlap <= 0:
        return 0.0
    axis_span = abs(b[axis] - a[axis])
    length = hypot(b[0] - a[0], b[1] - a[1])
    return overlap * length / axis_span if axis_span > EPSILON else overlap


def call_zero_arg(mobject, method_name: str, default):
    method = getattr(mobject, method_name, None)
    if method is None:
        return default
    try:
        return method()
    except Exception:
        return default


def max_opacity(value) -> float:
    try:
        if isinstance(value, (str, bytes)):
            return 0.0
        return float(max(value))
    except TypeError:
        try:
            return float(value)
        except Exception:
            return 0.0
    except ValueError:
        return 0.0


def is_occluding(mobject) -> bool:
    fill_opacity = max_opacity(call_zero_arg(mobject, "get_fill_opacity", 0.0))
    stroke_opacity = max_opacity(call_zero_arg(mobject, "get_stroke_opacity", 0.0))
    return fill_opacity > EPSILON or stroke_opacity > EPSILON
