from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.realtimev1.dependencies import get_client_mutation_id, get_event_publisher
from src.realtimev1.publisher import DomainEventPublisher
from src.tags.dto import (
    CreateTagCommand,
    DeleteTagCommand,
    ListProjectTagsQuery,
    UpdateTagCommand,
)
from src.tags.events import TagsDomainEventDispatcher
from src.tags.schemas import TagCreate, TagRead, TagUpdate
from src.tags.use_cases import (
    CreateTagUseCase,
    DeleteTagUseCase,
    ListProjectTagsUseCase,
    UpdateTagUseCase,
)

router = APIRouter(tags=["Tags"])


def get_list_project_tags_use_case() -> ListProjectTagsUseCase:
    return ListProjectTagsUseCase(db_helper.async_session_maker)


def get_create_tag_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> CreateTagUseCase:
    dispatcher = TagsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return CreateTagUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_update_tag_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> UpdateTagUseCase:
    dispatcher = TagsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return UpdateTagUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_delete_tag_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> DeleteTagUseCase:
    dispatcher = TagsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return DeleteTagUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


@router.get("/projects/{project_id}/tags", response_model=list[TagRead])
async def get_project_tags(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[ListProjectTagsUseCase, Depends(get_list_project_tags_use_case)],
):
    query = ListProjectTagsQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.post(
    "/projects/{project_id}/tags",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tag(
    project_id: int,
    tag_in: TagCreate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[CreateTagUseCase, Depends(get_create_tag_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = CreateTagCommand(
        project_id=project_id,
        actor_user_id=current_user.sub,
        name=tag_in.name,
        color=tag_in.color,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.patch("/tags/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: int,
    tag_update: TagUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateTagUseCase, Depends(get_update_tag_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = UpdateTagCommand(
        tag_id=tag_id,
        actor_user_id=current_user.sub,
        changes=tag_update.model_dump(exclude_unset=True),
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[DeleteTagUseCase, Depends(get_delete_tag_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = DeleteTagCommand(
        tag_id=tag_id,
        actor_user_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)
