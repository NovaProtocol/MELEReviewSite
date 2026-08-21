from api.thermo.solvers import brayton, carnot, diesel, dual, otto, rankine, vapor_compression
from api.thermo.solvers.base import CycleResult, register_solver, solve

__all__ = ["CycleResult", "register_solver", "solve"]
