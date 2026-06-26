from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.auth.dependencies import get_current_user
from src.auth.schemas import UserPayload
from src.boards.dto import (
    CreateColumnCommand,
    CreateTaskCommand,
    DeleteColumnCommand,
    DeleteTaskCommand,
    GetProjectBoardQuery,
    GetTaskDetailsQuery,
    ListProjectTasksQuery,
    MoveTaskCommand,
    ReorderColumnsCommand,
    UpdateColumnCommand,
    UpdateTaskCommand,
)
from src.boards.events import BoardsDomainEventDispatcher
from src.boards.schemas import (
    ColumnCreate,
    ColumnRead,
    ColumnReorderRequest,
    ColumnUpdate,
    TaskCreate,
    TaskMove,
    TaskMoveResponse,
    TaskPreview,
    TaskRead,
    TaskUpdate,
)
from src.boards.use_cases import (
    CreateColumnUseCase,
    CreateTaskUseCase,
    DeleteColumnUseCase,
    DeleteTaskUseCase,
    GetProjectBoardUseCase,
    GetTaskDetailsUseCase,
    ListProjectTasksUseCase,
    MoveTaskUseCase,
    ReorderColumnsUseCase,
    UpdateColumnUseCase,
    UpdateTaskUseCase,
)
from src.db.database import db_helper
from src.db.unit_of_work import UnitOfWork
from src.projects.dependencies import check_project_member
from src.realtimev1.dependencies import get_client_mutation_id, get_event_publisher
from src.realtimev1.publisher import DomainEventPublisher

router = APIRouter(tags=["Boards"])


def get_project_board_use_case() -> GetProjectBoardUseCase:
    return GetProjectBoardUseCase(db_helper.async_session_maker)


def get_list_project_tasks_use_case() -> ListProjectTasksUseCase:
    return ListProjectTasksUseCase(db_helper.async_session_maker)


def get_task_details_use_case() -> GetTaskDetailsUseCase:
    return GetTaskDetailsUseCase(db_helper.async_session_maker)


def get_create_column_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> CreateColumnUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return CreateColumnUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_update_column_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> UpdateColumnUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return UpdateColumnUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_delete_column_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> DeleteColumnUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return DeleteColumnUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_reorder_columns_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> ReorderColumnsUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return ReorderColumnsUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_create_task_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> CreateTaskUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return CreateTaskUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_move_task_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> MoveTaskUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return MoveTaskUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_update_task_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> UpdateTaskUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return UpdateTaskUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


def get_delete_task_use_case(
    event_publisher: Annotated[DomainEventPublisher, Depends(get_event_publisher)],
) -> DeleteTaskUseCase:
    dispatcher = BoardsDomainEventDispatcher(
        db_helper.async_session_maker,
        event_publisher,
    )
    return DeleteTaskUseCase(lambda: UnitOfWork(event_dispatcher=dispatcher))


@router.get("/projects/{project_id}/columns", response_model=list[ColumnRead])
async def get_project_board(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[GetProjectBoardUseCase, Depends(get_project_board_use_case)],
):
    query = GetProjectBoardQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.post(
    "/projects/{project_id}/columns",
    response_model=ColumnRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_column(
    project_id: int,
    column_in: ColumnCreate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[CreateColumnUseCase, Depends(get_create_column_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = CreateColumnCommand(
        project_id=project_id,
        actor_user_id=current_user.sub,
        name=column_in.name,
        tasks_limit=column_in.tasks_limit,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.patch(
    "/projects/{project_id}/columns/{column_id}",
    response_model=ColumnRead,
)
async def update_column(
    project_id: int,
    column_id: int,
    column_update: ColumnUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateColumnUseCase, Depends(get_update_column_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = UpdateColumnCommand(
        project_id=project_id,
        column_id=column_id,
        actor_user_id=current_user.sub,
        changes=column_update.model_dump(exclude_unset=True),
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.delete(
    "/projects/{project_id}/columns/{column_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_column(
    project_id: int,
    column_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[DeleteColumnUseCase, Depends(get_delete_column_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = DeleteColumnCommand(
        project_id=project_id,
        column_id=column_id,
        actor_user_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)


@router.post(
    "/projects/{project_id}/columns/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reorder_columns(
    project_id: int,
    reorder_data: ColumnReorderRequest,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[ReorderColumnsUseCase, Depends(get_reorder_columns_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = ReorderColumnsCommand(
        project_id=project_id,
        actor_user_id=current_user.sub,
        column_ids=reorder_data.column_ids,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)


@router.post(
    "/projects/{project_id}/columns/{column_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    project_id: int,
    column_id: int,
    task_in: TaskCreate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    _: Annotated[None, Depends(check_project_member)],
    use_case: Annotated[CreateTaskUseCase, Depends(get_create_task_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = CreateTaskCommand(
        project_id=project_id,
        author_id=current_user.sub,
        column_id=column_id,
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        assignee_id=task_in.assignee_id,
        deadline_at=task_in.deadline_at,
        tag_ids=task_in.tag_ids,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskPreview])
async def get_project_tasks(
    project_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[ListProjectTasksUseCase, Depends(get_list_project_tasks_use_case)],
    assignee_id: Annotated[int | None, Query()] = None,
    tag_ids: Annotated[list[int] | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=3)] = None,
):
    query = ListProjectTasksQuery(
        project_id=project_id,
        actor_user_id=current_user.sub,
        assignee_id=assignee_id,
        tag_ids=tag_ids,
        search=search,
    )
    return await use_case.execute(query)


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task_details(
    task_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[GetTaskDetailsUseCase, Depends(get_task_details_use_case)],
):
    query = GetTaskDetailsQuery(
        task_id=task_id,
        actor_user_id=current_user.sub,
    )
    return await use_case.execute(query)


@router.patch("/tasks/{task_id}/move", response_model=TaskMoveResponse)
async def move_task(
    task_id: int,
    move_data: TaskMove,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[MoveTaskUseCase, Depends(get_move_task_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = MoveTaskCommand(
        task_id=task_id,
        actor_user_id=current_user.sub,
        new_column_id=move_data.new_column_id,
        after_task_id=move_data.after_task_id,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[UpdateTaskUseCase, Depends(get_update_task_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    changes = task_update.model_dump(exclude_unset=True, exclude={"tag_ids"})
    command = UpdateTaskCommand(
        task_id=task_id,
        actor_user_id=current_user.sub,
        changes=changes,
        tag_ids=task_update.tag_ids,
        client_mutation_id=client_mutation_id,
    )
    return await use_case.execute(command)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    current_user: Annotated[UserPayload, Depends(get_current_user)],
    use_case: Annotated[DeleteTaskUseCase, Depends(get_delete_task_use_case)],
    client_mutation_id: Annotated[str | None, Depends(get_client_mutation_id)],
):
    command = DeleteTaskCommand(
        task_id=task_id,
        actor_user_id=current_user.sub,
        client_mutation_id=client_mutation_id,
    )
    await use_case.execute(command)
