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
    # Work and heat for the whole cycle, per kilogram of steam entering the turbine.
    # A regeneration cycle has no single-formula efficiency (part of the steam leaves
    # the turbine early, so the legs no longer carry the same mass), and these are the
    # only place that is accounted for.
    net_work: float | None = None
    heat_added: float | None = None
    turbine_work: float | None = None
    pump_work: float | None = None
    efficiency: float | None = None
    # Cycle-specific numbers a reader is asked for: bleed fraction, extraction
    # pressure, and anything else worth stating.
    extras: dict = field(default_factory=dict)
    # Legs that are not part of the closed loop. A regenerative cycle has steam that
    # leaves the turbine early and goes to the feedwater heater: that is a real line on
    # the diagram, and without it the drawing shows a boiler being fed by liquid it
    # could not have reached. Each entry is {from, to, process, description}, with
    # 1-based state numbers.
    branches: list[dict] = field(default_factory=list)


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
