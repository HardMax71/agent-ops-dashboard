from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, frontend_origin: str = "") -> None:
        super().__init__(app)
        self.frontend_origin = frontend_origin

    async def dispatch(self, request: Request, call_next: object) -> Response:  # noqa: ANN401
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; connect-src 'self' {self.frontend_origin}; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
