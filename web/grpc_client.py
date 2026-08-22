"""gRPC client for web -> api internal communication.

Uses grpc.aio to call Review service on melereview_api:50051.
HTTP remains the public path via caddy; this client is for
container-to-container only.
"""

from __future__ import annotations

import logging
from typing import Any

import grpc  # type: ignore[import-untyped]
import grpc.aio  # type: ignore[import-untyped]

logger = logging.getLogger("melereview-web.grpc")

GRPC_TARGET = "melereview_api:50051"

# Try to import generated stubs
try:
    from api.proto import (
        api_pb2,  # type: ignore[import-untyped]
        api_pb2_grpc,  # type: ignore[import-untyped]
    )
except ImportError:
    try:
        import api_pb2  # type: ignore[import-untyped, no-redef]
        import api_pb2_grpc  # type: ignore[import-untyped, no-redef]
    except ImportError:
        api_pb2 = None  # type: ignore[assignment]
        api_pb2_grpc = None  # type: ignore[assignment]


async def get_questions_grpc() -> list[dict[str, Any]]:
    """Fetch questions via gRPC (internal). Falls back to HTTP on failure."""
    if api_pb2 is None or api_pb2_grpc is None:
        logger.warning("gRPC stubs not generated; cannot call GetQuestions")
        return []
    try:
        async with grpc.aio.insecure_channel(GRPC_TARGET) as channel:
            stub = api_pb2_grpc.ReviewStub(channel)  # type: ignore[attr-defined]
            resp = await stub.GetQuestions(api_pb2.Empty())  # type: ignore[attr-defined]
            # Convert protobuf to dicts compatible with HTTP shapes
            out: list[dict[str, Any]] = []
            for q in resp.questions:  # type: ignore[attr-defined]
                out.append(
                    {
                        "id": q.id,
                        "question_text": q.question_text,
                        "choice_a": q.choice_a,
                        "choice_b": q.choice_b,
                        "choice_c": q.choice_c,
                        "choice_d": q.choice_d,
                        "choice_e": q.choice_e or None,
                        "answer": q.answer or None,
                        "solution": q.solution or None,
                        "flagged": bool(q.flagged),
                        "active": bool(q.active),
                        "tags": list(q.tags),
                        "author_name": getattr(q, "author_name", ""),
                    }
                )
            return out
    except grpc.aio.AioRpcError as e:  # type: ignore[attr-defined]
        logger.warning("gRPC GetQuestions failed (%s): %s", e.code(), e.details())  # type: ignore[attr-defined]
        return []
    except Exception as e:
        logger.exception("gRPC GetQuestions unexpected error: %s", e)
        return []


def get_questions_grpc_sync() -> list[dict[str, Any]]:
    """Synchronous variant using blocking channel (for non-async contexts)."""
    if api_pb2 is None or api_pb2_grpc is None:
        logger.warning("gRPC stubs not generated; cannot call GetQuestions (sync)")
        return []
    try:
        with grpc.insecure_channel(GRPC_TARGET) as channel:
            stub = api_pb2_grpc.ReviewStub(channel)  # type: ignore[attr-defined]
            resp = stub.GetQuestions(api_pb2.Empty())  # type: ignore[attr-defined]
            out: list[dict[str, Any]] = []
            for q in resp.questions:
                out.append(
                    {
                        "id": q.id,
                        "question_text": q.question_text,
                        "choice_a": q.choice_a,
                        "choice_b": q.choice_b,
                        "choice_c": q.choice_c,
                        "choice_d": q.choice_d,
                        "choice_e": q.choice_e or None,
                        "answer": q.answer or None,
                        "solution": q.solution or None,
                        "flagged": bool(q.flagged),
                        "active": bool(q.active),
                        "tags": list(q.tags),
                    }
                )
            return out
    except grpc.RpcError as e:  # type: ignore[attr-defined]
        logger.warning("gRPC sync GetQuestions failed: %s", e)
        return []
    except Exception as e:
        logger.exception("gRPC sync error: %s", e)
        return []


async def health_check_grpc() -> bool:
    """Check api gRPC health."""
    if api_pb2 is None or api_pb2_grpc is None:
        return False
    try:
        async with grpc.aio.insecure_channel(GRPC_TARGET) as channel:
            stub = api_pb2_grpc.ReviewStub(channel)  # type: ignore[attr-defined]
            resp = await stub.HealthCheck(api_pb2.Empty())  # type: ignore[attr-defined]
            return getattr(resp, "status", "") == "ok"
    except Exception:
        return False
