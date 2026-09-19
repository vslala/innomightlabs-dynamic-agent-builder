"""DynamoDB utility functions."""

from decimal import Decimal
from typing import Any


def convert_decimals(obj: Any) -> Any:
    """
    Recursively convert Decimal objects to int or float.

    DynamoDB returns all numeric values as Decimal. This helper converts them
    to native Python types for JSON serialization.

    Args:
        obj: Object to convert (can be dict, list, Decimal, or any other type)

    Returns:
        Object with all Decimals converted to int or float
    """
    if isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        # Convert to int if no decimal places, otherwise float
        return int(obj) if obj % 1 == 0 else float(obj)
    else:
        return obj


def convert_floats_to_decimals(obj: Any) -> Any:
    """Recursively convert floats to Decimal.

    The inverse of `convert_decimals`: DynamoDB rejects Python floats on write,
    so anything derived from `model_dump(mode="json")` has to be converted back
    before it can be stored.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    if isinstance(obj, dict):
        return {key: convert_floats_to_decimals(value) for key, value in obj.items()}
    return obj
