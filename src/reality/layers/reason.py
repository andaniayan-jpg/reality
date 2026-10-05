"""Evidence-bounded predictions from parsed physical objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reality._core.router import ModelRouter
from reality._physics_object import PhysicsObject
from reality._providers.base import AITask

from .copilot import _default_router


@dataclass(frozen=True, slots=True)
class Prediction:
    """An explicit unknown until loads, supports and constitutive data exist."""

    question: str
    outcome: Literal["unknown"]
    reason: str
    objects: tuple[PhysicsObject, ...]
    advisory: str | None = None

    def __str__(self) -> str:
        return f"{self.outcome}: {self.reason}" + (
            f" Advisory: {self.advisory}" if self.advisory else ""
        )


def predict(
    question: str,
    obj: PhysicsObject,
    *,
    use_ai: bool = False,
    router: ModelRouter | None = None,
) -> Prediction:
    """Discuss a question, without claiming unperformed simulation or FEA.

    ``use_ai=True`` requests advisory text from a configured local model. The
    physical outcome remains unknown even when the model produces plausible prose.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if not isinstance(obj, PhysicsObject):
        raise TypeError("predict expects a PhysicsObject from perceive.from_3d()")
    advisory = None
    if use_ai or router is not None:
        selected = router or _default_router()
        prompt = (
            f"Question: {question}\nMeasured object facts: {obj.summary}\n"
            f"Limits: {obj.limitations}\n"
            "Give hypotheses and missing inputs only. Do not answer yes/no on failure "
            "without loads, supports, material strength and verified analysis."
        )
        advisory = selected.route_feature("reason.predict", AITask(prompt=prompt)).text
    return Prediction(
        question=question,
        outcome="unknown",
        reason=(
            "A geometry file alone cannot establish failure under a load; provide material "
            "strength, support conditions, load direction/distribution and validated analysis."
        ),
        objects=(obj,),
        advisory=advisory,
    )
