from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.thermo.props import StatePoint


@dataclass
class CycleResult:
    cycle: str
    states: list[StatePoint]
    solved: bool
    missing: list[str] = field(default_factory=list)
    # The thermodynamic process of each leg, from a fixed vocabulary the sampler
    # switches on: isentropic, isobaric, isochoric, isothermal, isenthalpic.
    processes: list[str] = field(default_factory=list)
    # What each leg is, in words, for the table and the diagram. Kept apart from
    # `processes` because that one is a key and this one is a sentence: writing the
    # sentence into the key made every leg fall through the sampler to a straight line.
    descriptions: list[str] = field(default_factory=list)
    fluid: str = ""
    ideal_gas: bool = False


SolverFunc = Callable[[str, dict], CycleResult]

_REGISTRY: dict[str, SolverFunc] = {}


def register_solver(name: str) -> Callable:
    def decorator(func: SolverFunc) -> SolverFunc:
        _REGISTRY[name] = func
        return func

    return decorator


def solve(cycle: str, fluid: str, parameters: dict) -> CycleResult:
    if cycle not in _REGISTRY:
        raise ValueError(f"Unknown cycle: {cycle}. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[cycle](fluid, parameters)
