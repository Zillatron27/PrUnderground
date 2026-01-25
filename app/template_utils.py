"""Shared template rendering utilities."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .csrf import get_csrf_token, set_csrf_cookie, CSRF_FORM_FIELD
from .utils import format_price, get_stock_status

# Shared templates instance
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_price"] = format_price
templates.env.globals["get_stock_status"] = get_stock_status
templates.env.globals["csrf_field_name"] = CSRF_FORM_FIELD


def render_template(request: Request, template_name: str, context: dict, status_code: int = 200):
    """Render a template with CSRF token automatically added."""
    csrf_token = get_csrf_token(request)
    context["csrf_token"] = csrf_token
    response = templates.TemplateResponse(template_name, context, status_code=status_code)
    set_csrf_cookie(response, csrf_token)
    return response
