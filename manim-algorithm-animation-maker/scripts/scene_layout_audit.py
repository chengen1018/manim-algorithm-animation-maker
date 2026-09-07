from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from manim import config


_LAYOUT_AUDIT_CHECKPOINTS: list[str] = []
_LAYOUT_GRAPH_ROOTS: list[tuple[object, str | None]] = []


def reset_layout_audit_checkpoints() -> None:
    _LAYOUT_AUDIT_CHECKPOINTS.clear()
    _LAYOUT_GRAPH_ROOTS.clear()


def get_layout_audit_checkpoints() -> list[str]:
    return list(_LAYOUT_AUDIT_CHECKPOINTS)


def record_layout_audit_checkpoint(context: str) -> None:
    _LAYOUT_AUDIT_CHECKPOINTS.append(context)


def register_graph_root(root: object, name: str | None = None) -> None:
    """Register one stable structural wrapper as a graph for visible layout audit."""
    if root is None:
        raise ValueError("graph root must be an object")
    if name is not None and not name.strip():
        raise ValueError("graph name must be non-empty when provided")
    for registered_root, registered_name in _LAYOUT_GRAPH_ROOTS:
        if registered_root is root:
            if registered_name != name:
                raise ValueError("graph root is already registered with a different name")
            return
    _LAYOUT_GRAPH_ROOTS.append((root, name))


def get_layout_audit_graph_roots() -> list[tuple[object, str | None]]:
    return list(_LAYOUT_GRAPH_ROOTS)


@dataclass(frozen=True)
class LayoutBounds:
    left: float
    right: float
    bottom: float
    top: float

    def format(self) -> str:
        return (
            f"left={self.left:.2f}, right={self.right:.2f}, "
            f"bottom={self.bottom:.2f}, top={self.top:.2f}"
        )


class LayoutAudit:
    """Reusable bounding-box checks for Manim scenes."""

    def __init__(self, context: str = "", enabled: bool = True):
        self.context = context
        self.enabled = enabled
        self.issues: list[str] = []

    @staticmethod
    def bounds(mobject) -> LayoutBounds:
        return LayoutBounds(
            left=float(mobject.get_left()[0]),
            right=float(mobject.get_right()[0]),
            bottom=float(mobject.get_bottom()[1]),
            top=float(mobject.get_top()[1]),
        )

    def check_inside_frame(self, name: str, mobject, margin: float = 0.1) -> None:
        if not self.enabled:
            return

        bounds = self.bounds(mobject)
        half_width = config.frame_width / 2
        half_height = config.frame_height / 2

        if bounds.left < -half_width + margin:
            self._add(name, f"exceeds left frame ({bounds.format()})")
        if bounds.right > half_width - margin:
            self._add(name, f"exceeds right frame ({bounds.format()})")
        if bounds.bottom < -half_height + margin:
            self._add(name, f"exceeds bottom frame ({bounds.format()})")
        if bounds.top > half_height - margin:
            self._add(name, f"exceeds top frame ({bounds.format()})")

    def check_fits(
        self,
        inner_name: str,
        inner_mobject,
        outer_name: str,
        outer_mobject,
        padding: float = 0.0,
    ) -> None:
        if not self.enabled:
            return

        inner = self.bounds(inner_mobject)
        outer = self.bounds(outer_mobject)
        fits = (
            inner.left >= outer.left + padding
            and inner.right <= outer.right - padding
            and inner.bottom >= outer.bottom + padding
            and inner.top <= outer.top - padding
        )

        if not fits:
            self._add(
                inner_name,
                f"does not fit in {outer_name} with padding {padding:.2f} "
                f"(inner: {inner.format()}; outer: {outer.format()})",
            )

    def check_no_overlap(
        self,
        first_name: str,
        first_mobject,
        second_name: str,
        second_mobject,
        min_gap: float = 0.0,
    ) -> None:
        if not self.enabled:
            return

        first = self.bounds(first_mobject)
        second = self.bounds(second_mobject)
        overlaps = not (
            first.right <= second.left
            or second.right <= first.left
            or first.top <= second.bottom
            or second.top <= first.bottom
        )
        separated = (
            first.right + min_gap <= second.left
            or second.right + min_gap <= first.left
            or first.top + min_gap <= second.bottom
            or second.top + min_gap <= first.bottom
        )

        if separated:
            return

        relation = "overlaps" if overlaps else "is too close to"
        self._add(
            first_name,
            f"{relation} {second_name} with min_gap {min_gap:.2f} "
            f"({first_name}: {first.format()}; {second_name}: {second.format()})",
        )

    def check_no_overlaps_between(
        self,
        first_items: Iterable[tuple[str, object]],
        second_items: Iterable[tuple[str, object]],
        min_gap: float = 0.0,
    ) -> None:
        for first_name, first_mobject in first_items:
            for second_name, second_mobject in second_items:
                self.check_no_overlap(first_name, first_mobject, second_name, second_mobject, min_gap)

    def check_no_internal_overlaps(
        self,
        items: Sequence[tuple[str, object]],
        min_gap: float = 0.0,
    ) -> None:
        for (first_name, first_mobject), (second_name, second_mobject) in combinations(items, 2):
            self.check_no_overlap(first_name, first_mobject, second_name, second_mobject, min_gap)

    def report(self, raise_on_issue: bool = False) -> list[str]:
        if not self.enabled:
            return []

        record_layout_audit_checkpoint(self.context)
        if not self.issues:
            return []

        prefix = f"[layout:{self.context}]" if self.context else "[layout]"
        for issue in self.issues:
            print(f"{prefix} {issue}")

        if raise_on_issue:
            raise AssertionError("\n".join(self.issues))

        return self.issues

    def _add(self, name: str, message: str) -> None:
        self.issues.append(f"{name}: {message}")
