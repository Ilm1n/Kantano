from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.unit_of_work import UnitOfWork
from src.errors import ErrorCode
from src.logger import user_logger
from src.shared.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    ServiceUnavailableError,
)
from src.users.dto import (
    AvatarMutationResult,
    DeleteAvatarCommand,
    GetUserQuery,
    RegisterUserCommand,
    UpdateUserCommand,
    UpdateUserPasswordCommand,
    UploadAvatarCommand,
)
from src.users.models import User
from src.users.passwords import hash_password, validate_password
from src.users.repository import UserRepository
from src.users.storage import AvatarStorageError, AvatarStorageGateway


class GetUserUseCase:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def execute(self, query: GetUserQuery) -> User:
        try:
            async with self._session_factory() as session:
                repository = UserRepository(session)
                user = await repository.get_user(query.user_id)
                if user is None:
                    raise NotFoundError(ErrorCode.USER_NOT_FOUND)
                return user
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to read user %s",
                query.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class RegisterUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: RegisterUserCommand) -> User:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = UserRepository(uow.session)
                user = repository.add_user(
                    email=command.email,
                    username=command.username,
                    hashed_password=hash_password(command.password),
                )
                await repository.flush()
                await repository.refresh_user(user)
                return user
        except IntegrityError as exc:
            user_logger.warning("Failed to create user - username/email already exists")
            raise ConflictError(ErrorCode.USERNAME_OR_EMAIL_EXISTS) from exc
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to create user %s",
                command.username,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: UpdateUserCommand) -> User:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = UserRepository(uow.session)
                user = await repository.get_user(command.user_id)
                if user is None:
                    raise NotFoundError(ErrorCode.USER_NOT_FOUND)

                if not command.changes:
                    return user

                for key, value in command.changes.items():
                    setattr(user, key, value)

                repository.save_user(user)
                await repository.flush()
                await repository.refresh_user(user)
                return user
        except IntegrityError as exc:
            user_logger.warning("Failed to update user - username already taken")
            raise ConflictError(ErrorCode.USERNAME_TAKEN) from exc
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to update user %s",
                command.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UpdateUserPasswordUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: UpdateUserPasswordCommand) -> User:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = UserRepository(uow.session)
                user = await repository.get_user(command.user_id)
                if user is None:
                    raise NotFoundError(ErrorCode.USER_NOT_FOUND)

                if user.hashed_password:
                    if not command.current_password:
                        raise BadRequestError(ErrorCode.CURRENT_PASSWORD_REQUIRED)
                    if not validate_password(
                        command.current_password,
                        user.hashed_password,
                    ):
                        raise BadRequestError(ErrorCode.INVALID_CURRENT_PASSWORD)

                user.hashed_password = hash_password(command.new_password)
                repository.save_user(user)
                await repository.flush()
                await repository.refresh_user(user)
                return user
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to update password for user %s",
                command.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class UploadAvatarUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        storage: AvatarStorageGateway,
        object_name_factory: Callable[[int, str], str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._object_name_factory = object_name_factory or (
            lambda user_id, extension: f"avatars/user_{user_id}_{uuid4()}.{extension}"
        )

    async def execute(self, command: UploadAvatarCommand) -> AvatarMutationResult:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = UserRepository(uow.session)
                user = await repository.get_user(command.user_id)
                if user is None:
                    raise NotFoundError(ErrorCode.USER_NOT_FOUND)

                old_avatar_object_key = self._storage.object_key_from_url(user.avatar_url)
                object_name = self._object_name_factory(user.id, command.extension)

                try:
                    public_url = await self._storage.upload_file(
                        file_data=command.file_data,
                        object_name=object_name,
                        content_type=command.mime_type,
                    )
                except AvatarStorageError as exc:
                    raise ServiceUnavailableError(ErrorCode.FILE_UPLOAD_FAILED) from exc

                try:
                    user.avatar_url = public_url
                    repository.save_user(user)
                    await repository.flush()
                    await repository.refresh_user(user)
                    await uow.commit()
                except Exception as exc:
                    await self._storage.delete_file(object_name)
                    user_logger.exception(
                        "Failed to commit avatar upload for user %s",
                        command.user_id,
                        exc_info=exc,
                    )
                    raise DatabaseError(ErrorCode.DB_COMMIT_FAILED) from exc

                return AvatarMutationResult(
                    user=user,
                    old_avatar_object_key=old_avatar_object_key,
                )
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to upload avatar for user %s",
                command.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc


class DeleteAvatarUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        storage: AvatarStorageGateway,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    async def execute(self, command: DeleteAvatarCommand) -> AvatarMutationResult:
        try:
            async with self._uow_factory() as uow:
                if uow.session is None:
                    raise RuntimeError("UnitOfWork has not been entered")

                repository = UserRepository(uow.session)
                user = await repository.get_user(command.user_id)
                if user is None:
                    raise NotFoundError(ErrorCode.USER_NOT_FOUND)

                old_avatar_object_key = self._storage.object_key_from_url(user.avatar_url)
                if old_avatar_object_key is None:
                    return AvatarMutationResult(user=user)

                try:
                    user.avatar_url = None
                    repository.save_user(user)
                    await repository.flush()
                    await repository.refresh_user(user)
                    await uow.commit()
                except Exception as exc:
                    user_logger.exception(
                        "Failed to commit avatar deletion for user %s",
                        command.user_id,
                        exc_info=exc,
                    )
                    raise DatabaseError(ErrorCode.DB_COMMIT_FAILED) from exc

                return AvatarMutationResult(
                    user=user,
                    old_avatar_object_key=old_avatar_object_key,
                )
        except AppError:
            raise
        except Exception as exc:
            user_logger.exception(
                "Failed to delete avatar for user %s",
                command.user_id,
                exc_info=exc,
            )
            raise DatabaseError() from exc
