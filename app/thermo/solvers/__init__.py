"""One module per cycle; importing them registers each solver with the registry.

The names below are imported for that side effect rather than for use here, which
is why they are marked. Adding a cycle means adding its module to this list.
"""

from app.thermo.solvers import (
    brayton,  # noqa: F401
    carnot,  # noqa: F401
    diesel,  # noqa: F401
    dual,  # noqa: F401
    otto,  # noqa: F401
    rankine,  # noqa: F401
    vapor_compression,  # noqa: F401
)
from app.thermo.solvers.base import CycleResult, register_solver, solve

__all__ = ["CycleResult", "register_solver", "solve"]
