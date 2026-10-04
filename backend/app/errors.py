"""RFC 7807 problem responses. ``key`` is an i18n message key the frontend translates."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ProblemError(Exception):
    # positional-only so params may themselves be called ``key`` or ``status``
    def __init__(self, status: int, key: str, detail: str = "", /, **params: Any) -> None:
        super().__init__(detail or key)
        self.status = status
        self.key = key
        self.detail = detail or key
        self.params = params


def problem(status: int, key: str, detail: str, params: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": key,
            "status": status,
            "detail": detail,
            "key": key,
            "params": params,
        },
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_req: Request, exc: ProblemError) -> JSONResponse:
        return problem(exc.status, exc.key, exc.detail, exc.params)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem(422, "error.validation", "Request validation failed", {"errors": errors})
