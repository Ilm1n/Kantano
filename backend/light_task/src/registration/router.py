from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from src.errors import ErrorCode
from src.registration.dependencies import (
    get_confirm_registration_use_case,
    get_resend_verification_use_case,
    get_start_registration_use_case,
    get_validate_registration_token_use_case,
)
from src.registration.dto import (
    ConfirmRegistrationCommand,
    ResendVerificationCommand,
    StartRegistrationCommand,
    ValidateRegistrationTokenCommand,
)
from src.registration.schemas import (
    ConfirmRegistrationRequest,
    EmailConfirmed,
    RegistrationAccepted,
    RegistrationRequest,
    ResendVerificationRequest,
    VerificationTokenRequest,
)
from src.registration.use_cases import (
    ConfirmRegistrationUseCase,
    ResendVerificationUseCase,
    StartRegistrationUseCase,
    ValidateRegistrationTokenUseCase,
)
from src.shared.errors import BadRequestError

router = APIRouter(prefix="/registration", tags=["Registration"])


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.rsplit(",", maxsplit=1)[-1].strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=RegistrationAccepted, status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegistrationRequest,
    request: Request,
    use_case: Annotated[StartRegistrationUseCase, Depends(get_start_registration_use_case)],
) -> RegistrationAccepted:
    await use_case.execute(
        StartRegistrationCommand(
            username=payload.username,
            email=str(payload.email).lower(),
            client_ip=_client_ip(request),
        )
    )
    return RegistrationAccepted()


@router.post("/resend", response_model=RegistrationAccepted, status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    use_case: Annotated[ResendVerificationUseCase, Depends(get_resend_verification_use_case)],
) -> RegistrationAccepted:
    await use_case.execute(
        ResendVerificationCommand(
            email=str(payload.email).lower(),
            client_ip=_client_ip(request),
        )
    )
    return RegistrationAccepted()


@router.post("/confirm", response_model=EmailConfirmed)
async def confirm(
    payload: ConfirmRegistrationRequest,
    use_case: Annotated[ConfirmRegistrationUseCase, Depends(get_confirm_registration_use_case)],
) -> EmailConfirmed:
    ok = await use_case.execute(
        ConfirmRegistrationCommand(token=payload.token, password=payload.password)
    )
    if not ok:
        raise BadRequestError(ErrorCode.INVALID_OR_EXPIRED_VERIFICATION_TOKEN)
    return EmailConfirmed()


@router.post("/validate", status_code=status.HTTP_204_NO_CONTENT)
async def validate_token(
    payload: VerificationTokenRequest,
    use_case: Annotated[
        ValidateRegistrationTokenUseCase,
        Depends(get_validate_registration_token_use_case),
    ],
) -> None:
    if not await use_case.execute(ValidateRegistrationTokenCommand(token=payload.token)):
        raise BadRequestError(ErrorCode.INVALID_OR_EXPIRED_VERIFICATION_TOKEN)
