from __future__ import annotations

import grpc
from fastapi import HTTPException

from api.db import _get_session_factory
from api.models import Account
from api.proto_gen import question_pb2, question_pb2_grpc
from api.services import question_service, solution_service


def _question_to_proto(q, tags: list[str], author_name: str | None) -> question_pb2.Question:
    return question_pb2.Question(
        id=q.id,
        question_text=q.question_text or "",
        choice_a=q.choice_a or "",
        choice_b=q.choice_b or "",
        choice_c=q.choice_c or "",
        choice_d=q.choice_d or "",
        choice_e=q.choice_e or "",
        answer=q.answer if q.answer is not None else 0,
        has_answer=q.answer is not None,
        solution=q.solution or "",
        has_solution=q.solution is not None,
        flagged=bool(q.flagged),
        active=bool(q.active),
        account_id=q.account_id if q.account_id is not None else 0,
        has_account_id=q.account_id is not None,
        author_name=author_name or "",
        has_author_name=author_name is not None,
        tags=tags,
        date_created=str(q.date_created) if q.date_created else "",
    )


def _solution_to_proto(s) -> question_pb2.Solution:
    return question_pb2.Solution(
        id=s.id,
        question_id=s.question_id,
        account_id=s.account_id,
        convention=s.convention or "metric",
        blocks=s.blocks or "[]",
        date_created=str(s.date_created) if s.date_created else "",
    )


class QuestionServicer(question_pb2_grpc.QuestionServiceServicer):
    """gRPC servicer — delegates to the same service layer as HTTP routes."""

    async def ListQuestions(self, request, context):
        async with _get_session_factory()() as db:
            questions, total = await question_service.list_questions(
                db,
                search=request.search,
                tag=request.tag,
                include_inactive=request.include_inactive,
                page=request.page if request.page else 1,
                per_page=request.per_page if request.per_page else 100,
            )
            tags_map = await question_service.tags_for_questions(db, [q.id for q in questions])
            # Bulk fetch author names for efficiency
            author_ids = {q.account_id for q in questions if q.account_id}
            authors: dict[int, str] = {}
            if author_ids:
                for aid in author_ids:
                    acc = await db.get(Account, aid)
                    if acc:
                        authors[aid] = acc.name
            proto_qs = []
            for q in questions:
                tags = tags_map.get(q.id, [])
                author = authors.get(q.account_id) if q.account_id else None
                proto_qs.append(_question_to_proto(q, tags, author))
            return question_pb2.ListQuestionsResponse(
                questions=proto_qs,
                total=total,
                page=request.page if request.page else 1,
                per_page=request.per_page if request.per_page else 100,
            )

    async def GetQuestion(self, request, context):
        async with _get_session_factory()() as db:
            try:
                q = await question_service.get_question(db, request.question_id)
            except HTTPException as e:
                if e.status_code == 404:
                    await context.set_code(grpc.StatusCode.NOT_FOUND)
                    await context.set_details("Question not found")
                    return question_pb2.Question()
                raise
            tags_map = await question_service.tags_for_questions(db, [q.id])
            tags = tags_map.get(q.id, [])
            author_name = None
            if q.account_id is not None:
                acc = await db.get(Account, q.account_id)
                if acc:
                    author_name = acc.name
            return _question_to_proto(q, tags, author_name)

    async def CreateQuestion(self, request, context):
        from api.schemas import QuestionWrite

        # Validate via Pydantic
        try:
            data = QuestionWrite(
                question_text=request.question_text,
                choice_a=request.choice_a,
                choice_b=request.choice_b,
                choice_c=request.choice_c,
                choice_d=request.choice_d,
                choice_e=request.choice_e if request.has_choice_e else None,
                answer=request.answer if request.has_answer else None,
                solution=request.solution if request.has_solution else None,
                active=request.active,
                tags=list(request.tags),
            )
        except Exception as e:
            await context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            await context.set_details(str(e))
            return question_pb2.Question()
        async with _get_session_factory()() as db:
            q = await question_service.create_question(
                db, data, account_id=request.account_id if request.account_id else None
            )
            tags_map = await question_service.tags_for_questions(db, [q.id])
            tags = tags_map.get(q.id, [])
            author_name = None
            if q.account_id is not None:
                acc = await db.get(Account, q.account_id)
                if acc:
                    author_name = acc.name
            return _question_to_proto(q, tags, author_name)

    async def UpdateQuestion(self, request, context):
        from api.schemas import QuestionWrite

        if not request.question:
            await context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            await context.set_details("Missing question payload")
            return question_pb2.Question()
        src = request.question
        try:
            data = QuestionWrite(
                question_text=src.question_text,
                choice_a=src.choice_a,
                choice_b=src.choice_b,
                choice_c=src.choice_c,
                choice_d=src.choice_d,
                choice_e=src.choice_e if src.has_choice_e else None,
                answer=src.answer if src.has_answer else None,
                solution=src.solution if src.has_solution else None,
                active=src.active,
                tags=list(src.tags),
            )
        except Exception as e:
            await context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            await context.set_details(str(e))
            return question_pb2.Question()
        async with _get_session_factory()() as db:
            try:
                q = await question_service.get_question(db, request.question_id)
                # ownership check
                if request.account_id:
                    acc = await db.get(Account, request.account_id)
                    if acc is None:
                        await context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                        await context.set_details("Account not found")
                        return question_pb2.Question()
                    try:
                        question_service.check_ownership(q, acc)
                    except HTTPException as e:
                        await context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                        await context.set_details(e.detail)
                        return question_pb2.Question()
                q = await question_service.update_question(db, request.question_id, data)
            except HTTPException as e:
                if e.status_code == 404:
                    await context.set_code(grpc.StatusCode.NOT_FOUND)
                    await context.set_details("Question not found")
                    return question_pb2.Question()
                if e.status_code == 403:
                    await context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                    await context.set_details(e.detail)
                    return question_pb2.Question()
                raise
            tags_map = await question_service.tags_for_questions(db, [q.id])
            tags = tags_map.get(q.id, [])
            author_name = None
            if q.account_id is not None:
                acc = await db.get(Account, q.account_id)
                if acc:
                    author_name = acc.name
            return _question_to_proto(q, tags, author_name)

    async def DeleteQuestion(self, request, context):
        async with _get_session_factory()() as db:
            try:
                q = await question_service.get_question(db, request.question_id)
                if request.account_id:
                    acc = await db.get(Account, request.account_id)
                    if acc is None:
                        await context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                        await context.set_details("Account not found")
                        return question_pb2.DeleteQuestionResponse()
                    try:
                        question_service.check_ownership(q, acc)
                    except HTTPException as e:
                        await context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                        await context.set_details(e.detail)
                        return question_pb2.DeleteQuestionResponse()
                await question_service.delete_question(db, request.question_id)
            except HTTPException as e:
                if e.status_code == 404:
                    await context.set_code(grpc.StatusCode.NOT_FOUND)
                    await context.set_details("Question not found")
                    return question_pb2.DeleteQuestionResponse()
                if e.status_code == 403:
                    await context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                    await context.set_details(e.detail)
                    return question_pb2.DeleteQuestionResponse()
                raise
            return question_pb2.DeleteQuestionResponse()

    async def ListTags(self, request, context):
        async with _get_session_factory()() as db:
            tags = await question_service.list_tags(db)
            return question_pb2.ListTagsResponse(tags=[t.name for t in tags])


class SolutionServicer(question_pb2_grpc.SolutionServiceServicer):
    """gRPC servicer for solution blocks."""

    async def GetSolution(self, request, context):
        async with _get_session_factory()() as db:
            sol = await solution_service.get_solution(db, request.question_id, request.account_id)
            if sol is None:
                await context.set_code(grpc.StatusCode.NOT_FOUND)
                await context.set_details("Solution not found")
                return question_pb2.Solution()
            return _solution_to_proto(sol)

    async def PutSolution(self, request, context):
        async with _get_session_factory()() as db:
            try:
                sol = await solution_service.upsert_solution(
                    db,
                    request.question_id,
                    request.account_id,
                    request.convention or "metric",
                    request.blocks or "[]",
                )
            except HTTPException as e:
                # Pydantic validation → 422 → INVALID_ARGUMENT
                code = grpc.StatusCode.INVALID_ARGUMENT
                if e.status_code == 404:
                    code = grpc.StatusCode.NOT_FOUND
                await context.set_code(code)
                await context.set_details(str(e.detail))
                return question_pb2.Solution()
            return _solution_to_proto(sol)

    async def ListMySolutions(self, request, context):
        async with _get_session_factory()() as db:
            sols = await solution_service.list_account_solutions(db, request.account_id)
            return question_pb2.ListMySolutionsResponse(
                solutions=[_solution_to_proto(s) for s in sols]
            )


async def create_grpc_server() -> grpc.aio.Server:
    server = grpc.aio.server()
    question_pb2_grpc.add_QuestionServiceServicer_to_server(QuestionServicer(), server)
    question_pb2_grpc.add_SolutionServiceServicer_to_server(SolutionServicer(), server)
    server.add_insecure_port("0.0.0.0:50051")
    return server


async def serve_grpc() -> None:
    server = await create_grpc_server()
    await server.start()
    await server.wait_for_termination()
