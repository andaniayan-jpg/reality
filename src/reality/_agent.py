"""Safe, provider-neutral orchestration for inspecting and editing Reality models.

This module is intentionally an *agent layer*, not a geometry implementation.
Every measurement and edit is delegated to :class:`RealityModel` and its
transactional editor.  A language-model provider can choose a tool and resolve
words to source part names, but it cannot assert dimensions or geometry facts:
numeric edit values are accepted only when they occur in the user's request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, cast

import trimesh

from ._editing import EditOperationError
from ._file_model import ModelAssembly, ModelPart, ModelResult, RealityModel, _model_from_parts
from ._models import Bounds, Transform

AgentToolName = Literal["inspect", "measure", "edit", "create"]
_UNITS_TO_METRES = {"m": 1.0, "mm": 0.001, "cm": 0.01, "in": 0.0254, "ft": 0.3048}


class AgentPlanError(ValueError):
    """Raised when a request cannot be made unambiguous and safe to execute."""


class AgentProvider(Protocol):
    """Optional provider interface for intent/part-name disambiguation only.

    Providers receive no geometry authority.  Their response may contain a
    ``tool`` and source ``target`` string, but numeric edit arguments are
    deliberately ignored; numbers are parsed from the user's request below.
    """

    def choose_tool(self, request: str, *, parts: Sequence[str]) -> Mapping[str, str]: ...


@dataclass(frozen=True, slots=True)
class AgentAction:
    """A typed, reviewable tool call in an agent plan."""

    tool: AgentToolName
    target: str | None = None
    operation: str | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class AgentPlan:
    """A validated or rejected plan that is safe to display before execution."""

    request: str
    actions: tuple[AgentAction, ...]
    valid: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentExecution:
    """Result of preview/execute.  Failed validation always leaves input unchanged."""

    plan: AgentPlan
    executed: bool
    rolled_back: bool
    model: RealityModel | None
    validation: Mapping[str, object]
    results: tuple[ModelResult[Mapping[str, object]], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation", MappingProxyType(dict(self.validation)))


class RealityAgent:
    """Plan, validate, preview, and execute source-backed model tools.

    The built-in parser intentionally covers a small auditable command subset:
    ``inspect [part]``, ``measure <part>``, and ``move <part> x=1 mm``.
    Applications may provide an :class:`AgentProvider` to select the tool or
    resolve a source part name, while all model evidence remains deterministic.
    """

    def __init__(self, model: RealityModel, *, provider: AgentProvider | None = None) -> None:
        self.model = model
        self.provider = provider

    def inspect(self, target: str | None = None) -> Mapping[str, object]:
        """Return source-backed summary or one source part; no semantic guesses."""
        if target is None:
            return self.model.summary()
        part = self._part(target)
        return MappingProxyType(
            {
                "id": part.id,
                "name": part.name,
                "bounds": part.bounds,
                "volume": part.volume,
                "surface_area": part.surface_area,
                "topology": part.topology(),
                "units": self.model.units,
            }
        )

    def measure(self, target: str) -> ModelResult[Mapping[str, object]]:
        """Measure a source part through Reality's deterministic engine."""
        return self.model.measure(self._part(target))

    def create_box(
        self, name: str, *, width: float, height: float, depth: float, units: str = "m"
    ) -> RealityModel:
        """Create actual Trimesh box geometry; this is not an inferred CAD fact."""
        if not name.strip() or min(width, height, depth) <= 0.0:
            raise AgentPlanError("box name and all dimensions must be positive")
        if units not in _UNITS_TO_METRES:
            raise AgentPlanError(f"unsupported creation unit {units!r}")
        mesh = trimesh.creation.box(extents=(float(width), float(height), float(depth)))
        part = ModelPart(
            name=name,
            id="part-1",
            transform=Transform(),
            bounds=Bounds.from_points(mesh.bounds),
            _mesh=mesh,
            metadata={"created_by": "RealityAgent.create_box", "dimensions_user_supplied": True},
        )
        return _model_from_parts(
            Path(f"{name}.glb"),
            "glb",
            units,
            (part,),
            (ModelAssembly(name=name, id="assembly-root", part_ids=(part.id,)),),
            {"backend": "trimesh", "created": True, "agent": "reality"},
        )

    def plan(self, request: str) -> AgentPlan:
        """Turn a request into a typed plan without executing it."""
        normalized = " ".join(request.strip().split())
        if not normalized:
            return AgentPlan(request, (), False, ("request is empty",))
        chosen: Mapping[str, str] = {}
        if self.provider is not None:
            chosen = self.provider.choose_tool(
                normalized, parts=[part.name for part in self.model.parts]
            )
        lowered = normalized.lower()
        tool = chosen.get("tool", "") or (
            "measure"
            if lowered.startswith("measure ")
            else "inspect"
            if lowered.startswith("inspect")
            else "edit"
            if lowered.startswith(("move ", "translate "))
            else ""
        )
        try:
            if tool == "inspect":
                target = chosen.get("target") or _suffix(normalized, "inspect")
                if target:
                    target = self._part(target).id
                return AgentPlan(normalized, (AgentAction("inspect", target),), True)
            if tool == "measure":
                target = chosen.get("target") or _suffix(normalized, "measure")
                part = self._part(target)
                return AgentPlan(normalized, (AgentAction("measure", part.id),), True)
            if tool == "edit":
                return self._plan_translate(normalized, chosen)
        except AgentPlanError as error:
            return AgentPlan(normalized, (), False, (str(error),))
        return AgentPlan(
            normalized,
            (),
            False,
            ("unsupported request; use inspect, measure, or move <part> x=<number> <unit>",),
        )

    def preview(self, plan: AgentPlan) -> AgentExecution:
        """Apply edit actions only to an isolated editor and validate the result."""
        return self._run(plan, commit=False)

    def execute(self, plan: AgentPlan) -> AgentExecution:
        """Commit a plan only after preview geometry validation passes."""
        return self._run(plan, commit=True)

    def _run(self, plan: AgentPlan, *, commit: bool) -> AgentExecution:
        if not plan.valid:
            return AgentExecution(
                plan, False, False, None, {"valid": False, "errors": plan.diagnostics}
            )
        measurements: list[ModelResult[Mapping[str, object]]] = []
        edits = [action for action in plan.actions if action.tool == "edit"]
        for action in plan.actions:
            if action.tool == "measure" and action.target is not None:
                measurements.append(self.model.measure(action.target))
        if not edits:
            return AgentExecution(
                plan, True, False, self.model, {"valid": True}, tuple(measurements)
            )
        session = self.model.edit()
        completed = False
        try:
            for action in edits:
                if action.operation != "translate" or action.target is None:
                    raise AgentPlanError("only validated translate actions are executable")
                session.translate(
                    action.target,
                    x=cast(float, action.parameters["x"]),
                    y=cast(float, action.parameters["y"]),
                    z=cast(float, action.parameters["z"]),
                )
            candidate = session.preview()
            validation = candidate.edit().commit().validate()
            detail = {
                "valid": validation.valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
            }
            if not validation.valid:
                session.rollback()
                return AgentExecution(plan, False, True, self.model, detail, tuple(measurements))
            if not commit:
                session.rollback()
                return AgentExecution(plan, False, False, candidate, detail, tuple(measurements))
            result = session.commit()
            completed = True
            return AgentExecution(plan, True, False, result.model, detail, tuple(measurements))
        except (AgentPlanError, EditOperationError, LookupError, TypeError, ValueError) as error:
            if not completed:  # rollback is the only mutation path on rejected geometry.
                session.rollback()
            return AgentExecution(
                plan,
                False,
                True,
                self.model,
                {"valid": False, "errors": (str(error),)},
                tuple(measurements),
            )

    def _plan_translate(self, request: str, chosen: Mapping[str, str]) -> AgentPlan:
        match = re.match(r"(?:move|translate)\s+(.+?)\s+(?:(?:by\s+)?)x\s*=\s*", request, re.I)
        if match is None:
            raise AgentPlanError("move requests require x=<user-supplied number> <unit>")
        target = self._part(chosen.get("target") or match.group(1))
        numbers = re.findall(r"([xyz])\s*=\s*(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", request, re.I)
        if not numbers:
            raise AgentPlanError("move request has no user-supplied axis values")
        delta = {"x": 0.0, "y": 0.0, "z": 0.0}
        supplied: dict[str, str] = {}
        for axis, raw, unit in numbers:
            source_unit = (unit or self.model.units).lower()
            if self.model.units not in _UNITS_TO_METRES or source_unit not in _UNITS_TO_METRES:
                raise AgentPlanError("source or requested unit is unknown; specify supported units")
            delta[axis.lower()] = (
                float(raw) * _UNITS_TO_METRES[source_unit] / _UNITS_TO_METRES[self.model.units]
            )
            supplied[axis.lower()] = f"{raw} {source_unit}"
        return AgentPlan(
            request,
            (
                AgentAction(
                    "edit",
                    target.id,
                    "translate",
                    delta,
                    {
                        "numeric_parameters": supplied,
                        "numeric_source": "user_request",
                        "units": self.model.units,
                    },
                ),
            ),
            True,
        )

    def _part(self, reference: str | None) -> ModelPart:
        if not reference:
            raise AgentPlanError("a source part name is required")
        matches = [
            part
            for part in self.model.parts
            if part.id == reference or part.name.casefold() == reference.casefold()
        ]
        if not matches:
            available = [part.name for part in self.model.parts]
            raise AgentPlanError(f"unknown part {reference!r}; available: {available!r}")
        if len(matches) != 1:
            raise AgentPlanError(f"ambiguous part {reference!r}; use a unique source part id")
        return matches[0]


def _suffix(value: str, prefix: str) -> str | None:
    suffix = value[len(prefix) :].strip()
    return suffix or None
