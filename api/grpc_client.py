"""Compatibility shim: api grpc client mirrors web client.

Provides same interface for api-side or tests that import api.grpc_client.
"""

from web.grpc_client import (
    GRPC_TARGET,
    get_questions_grpc,
    get_questions_grpc_sync,
    health_check_grpc,
)

__all__ = ["GRPC_TARGET", "get_questions_grpc", "get_questions_grpc_sync", "health_check_grpc"]
