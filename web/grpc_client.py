from __future__ import annotations

import os

import grpc

from web.proto_gen import question_pb2, question_pb2_grpc

GRPC_ADDR = os.getenv("API_GRPC_ADDR", "melereview_api:50051")


async def _channel() -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(GRPC_ADDR)


async def list_questions_via_grpc(
    search: str = "",
    tag: str = "",
    include_inactive: bool = False,
    page: int = 1,
    per_page: int = 100,
):
    """Call api:50051 from web container via gRPC. Returns ListQuestionsResponse or None."""
    async with grpc.aio.insecure_channel(GRPC_ADDR) as channel:
        stub = question_pb2_grpc.QuestionServiceStub(channel)
        try:
            resp = await stub.ListQuestions(
                question_pb2.ListQuestionsRequest(
                    search=search,
                    tag=tag,
                    include_inactive=include_inactive,
                    page=page,
                    per_page=per_page,
                )
            )
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return resp


async def get_question_via_grpc(question_id: int):
    """Call api:50051 from web container. Returns Question proto or None on 404."""
    async with grpc.aio.insecure_channel(GRPC_ADDR) as channel:
        stub = question_pb2_grpc.QuestionServiceStub(channel)
        try:
            resp = await stub.GetQuestion(question_pb2.GetQuestionRequest(question_id=question_id))
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return resp


async def list_tags_via_grpc():
    async with grpc.aio.insecure_channel(GRPC_ADDR) as channel:
        stub = question_pb2_grpc.QuestionServiceStub(channel)
        resp = await stub.ListTags(question_pb2.ListTagsRequest())
        return list(resp.tags)


async def get_solution_via_grpc(question_id: int, account_id: int):
    async with grpc.aio.insecure_channel(GRPC_ADDR) as channel:
        stub = question_pb2_grpc.SolutionServiceStub(channel)
        try:
            resp = await stub.GetSolution(
                question_pb2.GetSolutionRequest(question_id=question_id, account_id=account_id)
            )
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return resp
