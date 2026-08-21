from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from api.thermo.props import StatePoint


@dataclass
class CycleResult:
    cycle: str
    states: list[StatePoint]
    solved: bool
    missing: list[str] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
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
