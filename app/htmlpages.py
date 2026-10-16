"""Input validation and presentation helpers.

The validation rules exist to satisfy FR11: the system returns a
human-readable error message when invalid employee input data is submitted,
and NFR04: end users never see a raw technical exception.

Presentation helpers keep currency and escaping consistent across every page.
"""

from __future__ import annotations

import html
import re
from typing import Any

# --------------------------------------------------------------------------
# Validation limits
# --------------------------------------------------------------------------

NAME_MIN, NAME_MAX = 2, 60
ADDRESS_MIN, ADDRESS_MAX = 5, 120
WAGE_MIN, WAGE_MAX = 1.0, 1000.0
PHONE_MAX, EMAIL_MAX = 30, 80

#: Deliberately permissive: the shop only needs an obvious typo guard.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{6,30}$")
#: ISO calendar date, which is also the format the date input submits.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def escape_html(value: Any) -> str:
    """Escape a value for HTML output (used by every template expression)."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def format_wage(value: Any) -> str:
    """Render an hourly wage as ``12.50``; empty string when unavailable."""
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def format_currency(value: Any) -> str:
    """Render an hourly wage with the currency suffix used in the GUI."""
    rendered = format_wage(value)
    return f"{rendered} CNY/hour" if rendered else "Not set"


# --------------------------------------------------------------------------
# Employee validation
# --------------------------------------------------------------------------


class ValidationError(Exception):
    """One or more user-correctable field problems."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("Invalid employee input")
        self.errors = errors


def validate_employee(form: dict[str, str]) -> dict[str, Any]:
    """Validate an employee form submission.

    Returns the cleaned values ready for the database. Raises
    :class:`ValidationError` carrying a message per offending field so the
    form can be redisplayed with the user's input preserved
    (URS Use Case 1, extension 1A).
    """
    errors: dict[str, str] = {}

    name = (form.get("name") or "").strip()
    if not name:
        errors["name"] = "Employee name is required."
    elif len(name) < NAME_MIN:
        errors["name"] = f"Employee name must be at least {NAME_MIN} characters."
    elif len(name) > NAME_MAX:
        errors["name"] = f"Employee name must be at most {NAME_MAX} characters."

    address = (form.get("address") or "").strip()
    if not address:
        errors["address"] = "Address is required."
    elif len(address) < ADDRESS_MIN:
        errors["address"] = f"Address must be at least {ADDRESS_MIN} characters."
    elif len(address) > ADDRESS_MAX:
        errors["address"] = f"Address must be at most {ADDRESS_MAX} characters."

    wage_text = (form.get("hourly_wage") or "").strip()
    wage: float | None = None
    if not wage_text:
        errors["hourly_wage"] = "Hourly wage is required."
    else:
        try:
            wage = float(wage_text)
        except ValueError:
            errors["hourly_wage"] = "Hourly wage must be a number, for example 32.50."
        else:
            if wage != wage or wage in (float("inf"), float("-inf")):
                errors["hourly_wage"] = "Hourly wage must be a real number."
            elif wage <= 0:
                errors["hourly_wage"] = "Hourly wage must be greater than zero."
            elif wage < WAGE_MIN:
                errors["hourly_wage"] = f"Hourly wage must be at least {WAGE_MIN:.2f}."
            elif wage > WAGE_MAX:
                errors["hourly_wage"] = f"Hourly wage must be at most {WAGE_MAX:.2f}."

    phone = (form.get("phone") or "").strip()
    if phone and not PHONE_RE.match(phone):
        errors["phone"] = "Phone may contain digits, spaces and + ( ) - . only."
    elif len(phone) > PHONE_MAX:
        errors["phone"] = f"Phone must be at most {PHONE_MAX} characters."

    email = (form.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        errors["email"] = "Email must look like name@example.com."
    elif len(email) > EMAIL_MAX:
        errors["email"] = f"Email must be at most {EMAIL_MAX} characters."

    hired_on = (form.get("hired_on") or "").strip()
    if hired_on and not DATE_RE.match(hired_on):
        errors["hired_on"] = "Hire date must use the format YYYY-MM-DD."

    if errors:
        raise ValidationError(errors)

    return {
        "name": name,
        "address": address,
        "hourly_wage": wage,
        "phone": phone,
        "email": email,
        "hired_on": hired_on,
    }


def validate_wage_range(low_text: str | None, high_text: str | None) -> tuple[float | None, float | None, str | None]:
    """Validate the optional hourly-wage filter used on the overview page (FR12).

    Returns ``(low, high, problem)``; ``problem`` is a user-facing message when
    the range is unusable, in which case the caller ignores both bounds rather
    than failing the whole page.
    """
    low: float | None = None
    high: float | None = None

    if low_text:
        try:
            low = float(low_text)
        except ValueError:
            return None, None, "Minimum wage filter must be a number."
        if low < 0:
            return None, None, "Minimum wage filter cannot be negative."

    if high_text:
        try:
            high = float(high_text)
        except ValueError:
            return None, None, "Maximum wage filter must be a number."
        if high < 0:
            return None, None, "Maximum wage filter cannot be negative."

    if low is not None and high is not None and low > high:
        return None, None, "Minimum wage filter cannot be greater than the maximum."

    return low, high, None
