from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.logger import board_logger
from src.shared.errors import (
    AppError,
    ConflictError,
    DatabaseError,
    NotFoundError,
)
from src.tags.dto import (
    CreateTagCommand,
    DeleteTagCommand,
    ListProjectTagsQuery,
    UpdateTagCommand,
)
from src.tags.events import TagCreated, TagDeleted, TagUpdated
from src.tags.models import Tag
from src.tags.permissions import TagPermissions
from src.tags.repository import TagRepository


class ListProjectTagsUseCase:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        permissions: TagPermissions | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._permissions = permissions or TagPermissions()

    async def execute(self, query: ListProjectTagsQuery) -> list[Tag]:
        try:
            async with self._session_factory() as session:
                repository = TagRepository(session)
                member = await repository.get_project_member(
                    project_id=query.project_id,
                    user_id=query.actor_user_id,
                )
                self._permissions.ensure_can_read_project_tags(member)
                return await repository.list_project_tags(query.project_id)
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to list tags for project %s",
                query.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class CreateTagUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: TagPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or TagPermissions()

    async def execute(self, command: CreateTagCommand) -> Tag:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = TagRepository(uow.session)
                member = await repository.get_project_member(
                    project_id=command.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_create_tag(member)

                existing = await repository.find_tag_by_name(
                    project_id=command.project_id,
                    name=command.name,
                )
                if existing is not None:
                    raise ConflictError(ErrorCode.TAG_ALREADY_EXISTS)

                tag = Tag(
                    name=command.name,
                    color=command.color,
                    project_id=command.project_id,
                )
                repository.add_tag(tag)
                await repository.touch_project(command.project_id)
                await repository.flush()
                affected_user_ids = await repository.get_project_member_user_ids(command.project_id)
                uow.collect_event(
                    TagCreated(
                        tag=tag,
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.actor_user_id,
                        project_id=command.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return tag
        except AppError:
            raise
        except IntegrityError as exc:
            raise ConflictError(ErrorCode.TAG_ALREADY_EXISTS) from exc
        except Exception as exc:
            board_logger.exception(
                "Failed to create tag in project %s",
                command.project_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateTagUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: TagPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or TagPermissions()

    async def execute(self, command: UpdateTagCommand) -> Tag:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = TagRepository(uow.session)
                tag = await repository.get_tag(command.tag_id)
                if tag is None:
                    raise NotFoundError(ErrorCode.TAG_NOT_FOUND)

                member = await repository.get_project_member(
                    project_id=tag.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_write_tag(member)

                for key, value in command.changes.items():
                    setattr(tag, key, value)

                repository.save_tag(tag)
                await repository.touch_project(tag.project_id)
                await repository.flush()
                affected_user_ids = await repository.get_project_member_user_ids(tag.project_id)
                uow.collect_event(
                    TagUpdated(
                        tag=tag,
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.actor_user_id,
                        project_id=tag.project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
                return tag
        except AppError:
            raise
        except IntegrityError as exc:
            raise ConflictError(ErrorCode.TAG_ALREADY_EXISTS) from exc
        except Exception as exc:
            board_logger.exception(
                "Failed to update tag %s",
                command.tag_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteTagUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        permissions: TagPermissions | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._permissions = permissions or TagPermissions()

    async def execute(self, command: DeleteTagCommand) -> None:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = TagRepository(uow.session)
                tag = await repository.get_tag(command.tag_id)
                if tag is None:
                    raise NotFoundError(ErrorCode.TAG_NOT_FOUND)

                member = await repository.get_project_member(
                    project_id=tag.project_id,
                    user_id=command.actor_user_id,
                )
                self._permissions.ensure_can_write_tag(member)

                project_id = tag.project_id
                tag_id = tag.id
                await repository.delete_tag(tag)
                await repository.touch_project(project_id)
                await repository.flush()
                affected_user_ids = await repository.get_project_member_user_ids(project_id)
                uow.collect_event(
                    TagDeleted(
                        tag_id=tag_id,
                        affected_user_ids=affected_user_ids,
                        actor_user_id=command.actor_user_id,
                        project_id=project_id,
                        client_mutation_id=command.client_mutation_id,
                    )
                )
        except AppError:
            raise
        except Exception as exc:
            board_logger.exception(
                "Failed to delete tag %s",
                command.tag_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc
