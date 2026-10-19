from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def api_error(status_code: int, code: str, message: str, details: Optional[dict] = None) -> HTTPException:
    """Build an HTTPException whose body matches the ErrorResponse contract."""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details},
    )


def not_found(message: str = "요청한 자원을 찾을 수 없습니다.") -> HTTPException:
    return api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", message)


def forbidden(message: str = "이 자원에 접근할 권한이 없습니다.") -> HTTPException:
    return api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", message)


def bad_request(message: str, details: Optional[dict] = None) -> HTTPException:
    return api_error(status.HTTP_400_BAD_REQUEST, "BAD_REQUEST", message, details)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "요청 값이 올바르지 않습니다.",
                "details": {"errors": errors},
            }
        },
    )
