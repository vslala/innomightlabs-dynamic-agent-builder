"""Automation domain exceptions."""


class AutomationNotFoundError(Exception):
    """Raised when an automation does not exist or is not owned by the user."""


class AutomationValidationError(Exception):
    """Raised when an automation graph or state transition is invalid."""
