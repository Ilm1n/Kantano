import filetype
from fastapi import HTTPException, UploadFile, status

from src.errors import ErrorCode


class FileValidator:
    def __init__(self, max_size: int, allowed_mimes: list[str]):
        self.max_size = max_size
        self.allowed_mimes = allowed_mimes

    async def __call__(self, file: UploadFile) -> tuple[bytes, str, str]:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > self.max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": ErrorCode.FILE_TOO_LARGE,
                    "params": {"max_size_mb": self.max_size / 1024 / 1024},
                },
            )

        content = await file.read()

        kind = filetype.guess(content)

        if kind is None or kind.mime not in self.allowed_mimes:
            allowed_exts = [m.split("/")[-1] for m in self.allowed_mimes]
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={
                    "code": ErrorCode.INVALID_FILE_TYPE,
                    "params": {"allowed": allowed_exts},
                },
            )

        return content, kind.extension, kind.mime
