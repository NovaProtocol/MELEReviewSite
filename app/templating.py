from __future__ import annotations

from pathlib import Path

from fastapi import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from app import permissions
from app.auth import CSRF_COOKIE
from app.config import get_config
from app.security import new_csrf_token

ROOT = Path(__file__).resolve().parent
_TEMPLATES_DIR = ROOT / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

templates.env.globals["permissions"] = permissions
templates.env.globals["permission_labels"] = permissions.LABELS
templates.env.globals["permission_short"] = permissions.SHORT
templates.env.globals["permission_order"] = permissions.ORDER


def _tool_catalogue() -> list[dict]:
    from app.routes.tools import TOOLS

    return list(TOOLS)


templates.env.globals["tool_catalogue"] = _tool_catalogue


def render(
    request: Request,
    name: str,
    context: dict | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> Response:
    """Render a page, minting the CSRF cookie when the visitor does not have one.

    The cookie is readable by the page's own JavaScript on purpose: the client
    echoes it back in a header, and the two are compared server side. Minting it
    here means every rendered page can post, including the sign-in form.
    """
    token = request.cookies.get(CSRF_COOKIE)
    minted = token is None
    if token is None:
        token = new_csrf_token()
    payload = dict(context or {})
    payload.setdefault("csrf_token", token)
    response = templates.TemplateResponse(
        request, name, payload, status_code=status_code, headers=headers
    )
    if minted:
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=False,
            samesite="lax",
            secure=get_config().secure_cookies,
            max_age=30 * 24 * 3600,
            path="/",
        )
    return response
