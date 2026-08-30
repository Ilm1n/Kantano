from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
)

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.users.dependencies import valid_avatar
from src.users.dto import (
    DeleteAvatarCommand,
    GetUserQuery,
    UpdateUserCommand,
    UpdateUserPasswordCommand,
    UploadAvatarCommand,
)
from src.users.schemas import (
    UserPasswordUpdate,
    UserPublic,
    UserRead,
    UserUpdate,
)
from src.users.storage import AvatarStorageGateway, get_avatar_storage_gateway
from src.users.use_cases import (
    DeleteAvatarUseCase,
    GetUserUseCase,
    UpdateUserPasswordUseCase,
    UpdateUserUseCase,
    UploadAvatarUseCase,
)

router = APIRouter(prefix="/users", tags=["Users"])


def get_user_use_case() -> GetUserUseCase:
    return GetUserUseCase(db_helper.async_session_maker)


def get_update_user_use_case() -> UpdateUserUseCase:
    return UpdateUserUseCase(lambda: UnitOfWork())


def get_update_user_password_use_case() -> UpdateUserPasswordUseCase:
    return UpdateUserPasswordUseCase(lambda: UnitOfWork())


def get_upload_avatar_use_case(
    storage: Annotated[AvatarStorageGateway, Depends(get_avatar_storage_gateway)],
) -> UploadAvatarUseCase:
    return UploadAvatarUseCase(lambda: UnitOfWork(), storage)


def get_delete_avatar_use_case(
    storage: Annotated[AvatarStorageGateway, Depends(get_avatar_storage_gateway)],
) -> DeleteAvatarUseCase:
    return DeleteAvatarUseCase(lambda: UnitOfWork(), storage)


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[GetUserUseCase, Depends(get_user_use_case)],
):
    query = GetUserQuery(user_id=current_user.sub)
    return await use_case.execute(query)


@router.patch("/me", response_model=UserRead)
async def update_user_me(
    user_update: UserUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateUserUseCase, Depends(get_update_user_use_case)],
):
    command = UpdateUserCommand(
        user_id=current_user.sub,
        changes=user_update.model_dump(exclude_unset=True),
    )
    return await use_case.execute(command)


@router.patch("/me/password", response_model=UserRead)
async def update_user_password(
    password_update: UserPasswordUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateUserPasswordUseCase, Depends(get_update_user_password_use_case)],
):
    command = UpdateUserPasswordCommand(
        user_id=current_user.sub,
        current_password=password_update.current_password,
        new_password=password_update.new_password,
    )
    return await use_case.execute(command)


@router.get("/{user_id}", response_model=UserPublic)
async def read_user_by_id(
    user_id: int,
    use_case: Annotated[GetUserUseCase, Depends(get_user_use_case)],
    _: Annotated[UserPayload, Depends(get_current_user)],
):
    query = GetUserQuery(user_id=user_id)
    return await use_case.execute(query)


@router.post("/me/avatar", response_model=UserRead)
async def upload_avatar(
    file_data: Annotated[tuple[bytes, str, str], Depends(valid_avatar)],
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    storage: Annotated[AvatarStorageGateway, Depends(get_avatar_storage_gateway)],
    use_case: Annotated[UploadAvatarUseCase, Depends(get_upload_avatar_use_case)],
    bg_tasks: BackgroundTasks,
):
    content, ext, mime = file_data

    command = UploadAvatarCommand(
        user_id=current_user.sub,
        file_data=content,
        extension=ext,
        mime_type=mime,
    )
    result = await use_case.execute(command)
    if result.old_avatar_object_key:
        bg_tasks.add_task(storage.delete_file, result.old_avatar_object_key)
    return result.user


@router.delete("/me/avatar", response_model=UserRead)
async def delete_avatar(
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    storage: Annotated[AvatarStorageGateway, Depends(get_avatar_storage_gateway)],
    use_case: Annotated[DeleteAvatarUseCase, Depends(get_delete_avatar_use_case)],
    bg_tasks: BackgroundTasks,
):
    command = DeleteAvatarCommand(user_id=current_user.sub)
    result = await use_case.execute(command)
    if result.old_avatar_object_key:
        bg_tasks.add_task(storage.delete_file, result.old_avatar_object_key)
    return result.user
