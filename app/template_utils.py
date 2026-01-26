"""Shared template rendering utilities."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .csrf import get_csrf_token, set_csrf_cookie, CSRF_FORM_FIELD
from .utils import format_price, get_stock_status, is_sync_stale
from .services.fio_sync import get_sync_staleness


def condense_number(value: float | int | None) -> str:
    """
    Condense large numbers for narrow displays.
    1500000 → 1.5m, 250000 → 250k, 1500 → 1.5k, 150 → 150
    """
    if value is None:
        return "—"

    value = float(value)

    if value >= 1_000_000:
        condensed = value / 1_000_000
        # Show 1 decimal if needed, otherwise whole number
        if condensed == int(condensed):
            return f"{int(condensed)}m"
        return f"{condensed:.1f}m".rstrip('0').rstrip('.')  + "m" if condensed != int(condensed) else f"{int(condensed)}m"
    elif value >= 1_000:
        condensed = value / 1_000
        if condensed == int(condensed):
            return f"{int(condensed)}k"
        return f"{condensed:.1f}k".rstrip('0').rstrip('.') + "k" if condensed != int(condensed) else f"{int(condensed)}k"
    else:
        if value == int(value):
            return str(int(value))
        return f"{value:.1f}"


def _condense_number_clean(value: float | int | None) -> str:
    """
    Condense large numbers for narrow displays.
    1500000 → 1.5m, 250000 → 250k, 1500 → 1.5k, 150 → 150
    """
    if value is None:
        return "—"

    value = float(value)

    if value >= 1_000_000:
        condensed = value / 1_000_000
        if condensed == int(condensed):
            return f"{int(condensed)}m"
        return f"{condensed:.1f}m"
    elif value >= 1_000:
        condensed = value / 1_000
        if condensed == int(condensed):
            return f"{int(condensed)}k"
        return f"{condensed:.1f}k"
    else:
        if value == int(value):
            return str(int(value))
        return f"{value:.1f}"


# Replace the buggy version with the clean one
condense_number = _condense_number_clean


# CX station abbreviations (only 5 CX stations exist)
CX_ABBREVIATIONS = {
    "Antares Station": "ANT",
    "Moria Station": "MOR",
    "Benten Station": "BEN",
    "Hortus Station": "HRT",
    "Arclight Station": "ARC",
}


def abbreviate_location(location: str | None) -> str:
    """Abbreviate CX station names for narrow displays."""
    if not location:
        return "—"
    return CX_ABBREVIATIONS.get(location, location)


def get_display_context(request: Request) -> dict:
    """
    Parse URL parameters to determine display mode.
    Returns dict with display_classes and chrome_visible for templates.

    URL parameters:
    - ?embed=1 → force-narrow + no-chrome (full embed mode)
    - ?embed=0 → force-desktop + chrome visible
    - ?narrow=1 → force-narrow only
    - ?chrome=0 → no-chrome only
    """
    params = request.query_params

    classes = []
    chrome_visible = True

    embed = params.get("embed")
    narrow = params.get("narrow")
    chrome = params.get("chrome")

    if embed == "1":
        classes.append("force-narrow")
        classes.append("no-chrome")
        chrome_visible = False
    elif embed == "0":
        classes.append("force-desktop")
    else:
        # Check individual overrides
        if narrow == "1":
            classes.append("force-narrow")
        if chrome == "0":
            classes.append("no-chrome")
            chrome_visible = False

    return {
        "display_classes": " ".join(classes),
        "chrome_visible": chrome_visible,
    }


# Shared templates instance
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_price"] = format_price
templates.env.globals["get_stock_status"] = get_stock_status
templates.env.globals["get_sync_staleness"] = get_sync_staleness
templates.env.globals["is_sync_stale"] = is_sync_stale
templates.env.globals["csrf_field_name"] = CSRF_FORM_FIELD
templates.env.globals["condense_number"] = condense_number
templates.env.globals["abbreviate_location"] = abbreviate_location


def render_template(request: Request, template_name: str, context: dict, status_code: int = 200):
    """Render a template with CSRF token and display context automatically added."""
    csrf_token = get_csrf_token(request)
    context["csrf_token"] = csrf_token

    # Add display context for responsive/embed mode
    display_ctx = get_display_context(request)
    context["display_classes"] = display_ctx["display_classes"]
    context["chrome_visible"] = display_ctx["chrome_visible"]

    response = templates.TemplateResponse(template_name, context, status_code=status_code)
    set_csrf_cookie(response, csrf_token)
    return response
