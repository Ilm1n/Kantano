# ruff: noqa: RUF001
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from src.assistant.cleanup import CheckpointCleanup
from src.assistant.contracts import EXECUTING_RUN_STATUSES, RunStatus
from src.assistant.dto import (
    ConversationScope,
    CreateConversationCommand,
    DecideActionCommand,
    HistoryMessage,
    ProjectScope,
    RunExecution,
    RunMetadata,
    StartRunCommand,
)
from src.assistant.models import AssistantConversation, AssistantMessage, AssistantRun
from src.assistant.queries import AssistantProjectQueries
from src.assistant.repository import AssistantRepository
from src.assistant.schemas import ActionDisplay, ChatDetail, ConversationRead, MessageRead, RunRead
from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.shared.errors import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


async def ensure_project(
    repository: AssistantRepository, scope: ProjectScope, *, lock: bool = False
) -> None:
    if lock and not await repository.lock_project(scope.project_id):
        raise NotFoundError(ErrorCode.PROJECT_NOT_FOUND)
    if not await repository.is_member(scope.project_id, scope.user_id):
        raise NotFoundError(ErrorCode.PROJECT_NOT_FOUND)


async def authorized_chat(
    repository: AssistantRepository, scope: ConversationScope, *, lock: bool = False
) -> AssistantConversation:
    await ensure_project(repository, scope, lock=lock)
    conversation = await repository.get_conversation(
        scope.project_id, scope.user_id, scope.conversation_id, for_update=lock
    )
    if conversation is None:
        raise NotFoundError(ErrorCode.ASSISTANT_CHAT_NOT_FOUND)
    return conversation


def uow_repository(uow: UnitOfWork) -> AssistantRepository:
    if uow.session is None:
        raise RuntimeError("UnitOfWork has not been entered")
    return AssistantRepository(uow.session)


class ListConversationsUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, scope: ProjectScope) -> list[ConversationRead]:
        async with self._session_factory() as session:
            repository = AssistantRepository(session)
            await ensure_project(repository, scope)
            return [
                ConversationRead.model_validate(chat)
                for chat in await repository.list_conversations(scope.project_id, scope.user_id)
            ]


class CreateConversationUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreateConversationCommand) -> ConversationRead:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            await ensure_project(repository, command, lock=True)
            conversation = AssistantConversation(
                project_id=command.project_id,
                user_id=command.user_id,
                title=command.title,
                mode=command.mode,
            )
            repository.add_conversation(conversation)
            await repository.flush()
            await repository.refresh(conversation)
            result = ConversationRead.model_validate(conversation)
        return result


class GetConversationUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, scope: ConversationScope) -> ChatDetail:
        async with self._session_factory() as session:
            repository = AssistantRepository(session)
            conversation = await authorized_chat(repository, scope)
            messages = [
                MessageRead.model_validate(message)
                for message in await repository.list_messages(scope.conversation_id)
            ]
            task_ids = [ref.id for message in messages for ref in message.references]
            titles = await repository.task_titles(scope.project_id, task_ids) if task_ids else {}
            for message in messages:
                for reference in message.references:
                    reference.title = titles.get(reference.id, reference.title)
            latest_run = await repository.latest_run(scope.conversation_id)
            run_read = RunRead.model_validate(latest_run) if latest_run else None
            result = ChatDetail(
                conversation=ConversationRead.model_validate(conversation),
                messages=messages,
                latest_run=run_read,
            )
        if run_read and run_read.status == "pending" and run_read.proposed_action:
            proposal = run_read.proposed_action
            if proposal.display is None:
                queries = AssistantProjectQueries(self._session_factory, scope)
                proposal.display = ActionDisplay.model_validate(
                    await queries.describe_action(proposal.name, proposal.args)
                )
        return result


class DeleteConversationUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], cleanup: CheckpointCleanup) -> None:
        self._uow_factory = uow_factory
        self._cleanup = cleanup

    async def execute(self, scope: ConversationScope) -> None:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            conversation = await authorized_chat(repository, scope, lock=True)
            runs = await repository.list_runs(scope.conversation_id)
            if any(run.status in EXECUTING_RUN_STATUSES for run in runs):
                raise ConflictError(ErrorCode.ASSISTANT_RUN_ACTIVE)
            repository.queue_checkpoint_cleanup([run.id for run in runs])
            await repository.delete_conversation(conversation)
        await self._cleanup.drain()


class StartRunUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: StartRunCommand) -> RunExecution:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            conversation = await authorized_chat(repository, command, lock=True)
            if await repository.active_run(command.conversation_id) is not None:
                raise ConflictError(ErrorCode.ASSISTANT_RUN_ACTIVE)
            history = await repository.list_messages(command.conversation_id)
            repository.add_message(
                AssistantMessage(
                    conversation_id=command.conversation_id,
                    role="user",
                    content=command.content,
                    references=[],
                )
            )
            run = AssistantRun(conversation_id=command.conversation_id, status="running")
            repository.add_run(run)
            if not history and conversation.title == "Новый чат":
                conversation.title = command.content[:80]
            await repository.touch_conversation(conversation)
            await repository.flush()
            graph_history = [
                HistoryMessage(
                    role="user" if message.role == "user" else "assistant", content=message.content
                )
                for message in history[-20:]
            ]
            graph_history.append(HistoryMessage(role="user", content=command.content))
            execution = RunExecution(
                run_id=run.id,
                scope=ConversationScope(
                    project_id=command.project_id,
                    user_id=command.user_id,
                    conversation_id=command.conversation_id,
                ),
                history=graph_history,
            )
        return execution


class DecideActionUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: DecideActionCommand) -> RunExecution:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            await authorized_chat(repository, command, lock=True)
            run = await repository.get_run(command.run_id)
            if run is None or run.conversation_id != command.conversation_id:
                raise NotFoundError(ErrorCode.ASSISTANT_RUN_NOT_FOUND)
            if not await repository.claim_pending(
                command.run_id, command.action_id, "executing" if command.approve else "running"
            ):
                raise ConflictError(ErrorCode.ASSISTANT_ACTION_RESOLVED)
        return RunExecution(
            run_id=command.run_id,
            scope=ConversationScope(
                project_id=command.project_id,
                user_id=command.user_id,
                conversation_id=command.conversation_id,
            ),
            approve=command.approve,
        )


class AssistantRunLifecycle:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def interrupt(self, run_id: UUID | None = None) -> None:
        async with self._uow_factory() as uow:
            await uow_repository(uow).interrupt_run(run_id)

    async def pending(
        self, execution: RunExecution, action: dict[str, Any], metadata: RunMetadata
    ) -> None:
        async with self._uow_factory() as uow:
            await uow_repository(uow).update_run(
                execution.run_id, status="pending", proposed_action=action, **asdict(metadata)
            )

    async def record_results(
        self, execution: RunExecution, outcomes: list[dict[str, Any]], executing: bool
    ) -> None:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            message = await self._result_message(repository, execution)
            message.content = results_summary(outcomes)
            message.references = action_references(outcomes)
            await repository.update_run(
                execution.run_id,
                status="executing" if executing else "running",
                proposed_action=None,
                result={"actions": outcomes},
            )

    async def complete(
        self,
        execution: RunExecution,
        content: str,
        outcomes: list[dict[str, Any]],
        references: list[dict[str, Any]],
        metadata: RunMetadata,
    ) -> tuple[RunStatus, str]:
        status: RunStatus = "completed"
        if outcomes and all(outcome["status"] == "rejected" for outcome in outcomes):
            status = "rejected"
        elif any(outcome["status"] in {"failed", "skipped"} for outcome in outcomes):
            status = "failed"
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            message = await self._result_message(repository, execution)
            message.content = content or results_summary(outcomes)
            references = [*references, *action_references(outcomes)]
            message.references = list(
                {(ref["type"], ref["id"]): ref for ref in references}.values()
            )[:30]
            await repository.update_run(
                execution.run_id,
                status=status,
                proposed_action=None,
                result={"actions": outcomes} if outcomes else None,
                **asdict(metadata),
            )
        return status, message.content

    async def fail(self, execution: RunExecution) -> str:
        async with self._uow_factory() as uow:
            repository = uow_repository(uow)
            run = await repository.get_run(execution.run_id)
            if run is None:
                return "Не удалось выполнить запрос."
            result = dict(run.result or {})
            if run.status == "executing":
                run.status = "unknown"
                text = "Исход изменения неизвестен. Проверьте доску перед новой попыткой."
            else:
                run.status = "failed"
                text = (
                    "Не удалось продолжить запрос. Результаты выполненных действий сохранены."
                    if result.get("actions")
                    else "Не удалось выполнить запрос. Попробуйте ещё раз."
                )
            result["error"] = text
            run.result = result
            run.proposed_action = None
            repository.add_message(
                AssistantMessage(
                    conversation_id=execution.scope.conversation_id,
                    role="assistant",
                    content=text,
                    references=[],
                )
            )
        return text

    async def _result_message(
        self, repository: AssistantRepository, execution: RunExecution
    ) -> AssistantMessage:
        message_id = uuid5(execution.run_id, "action-results")
        message = await repository.get_message(message_id)
        if message is None:
            message = AssistantMessage(
                id=message_id, conversation_id=execution.scope.conversation_id, role="assistant"
            )
            repository.add_message(message)
        return message


def action_summary(outcome: dict[str, Any]) -> str:
    if outcome["status"] == "rejected":
        return "Действие отклонено."
    if outcome["status"] == "failed":
        return outcome.get("error", "Действие не выполнено.")
    if outcome["status"] == "skipped":
        return "Шаг пропущен после ошибки."
    title = f"«{outcome['title']}»" if outcome.get("title") else ""
    name = f"«{outcome['name']}»" if outcome.get("name") else ""
    labels = {
        "created": f"Создана задача {title}.",
        "updated": f"Изменена задача {title}.",
        "moved": f"Перемещена задача {title}.",
        "column_created": f"Создана колонка {name}.",
        "column_renamed": f"Переименована колонка {name}.",
        "column_moved": f"Перемещена колонка {name}.",
        "tag_created": f"Создан тег {name}.",
        "tag_updated": f"Изменён тег {name}.",
        "tag_added_to_task": f"Тег добавлен к задаче {title}.",
        "tag_removed_from_task": f"Тег снят с задачи {title}.",
    }
    return labels.get(outcome.get("kind", ""), "Действие выполнено.")


def action_references(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(
        {
            outcome["task_id"]: {
                "type": "task",
                "id": outcome["task_id"],
                "title": outcome.get("title"),
            }
            for outcome in outcomes
            if outcome.get("task_id") and outcome["status"] == "completed"
        }.values()
    )


def results_summary(outcomes: list[dict[str, Any]]) -> str:
    if len(outcomes) == 1:
        return action_summary(outcomes[0])
    completed = sum(outcome["status"] == "completed" for outcome in outcomes)
    return f"Выполнено действий: {completed}.\n\n" + "\n".join(
        f"- {action_summary(outcome)}" for outcome in outcomes
    )
