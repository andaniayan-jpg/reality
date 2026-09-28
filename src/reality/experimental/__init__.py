"""Explicitly optional experimental accelerators.

Experimental modules never replace Reality's exact predicate or physics validation.
"""

from .predictor import CandidatePrioritizer, PredictorUnavailableError

__all__ = ["CandidatePrioritizer", "PredictorUnavailableError"]
