"""Why an image was refused, in terms every surface can show."""

from __future__ import annotations

from src.exceptions import Refusal


class ImageInputError(Refusal):
    """An image refused: `code` and `message`, rendered by the `Refusal` handler in `src/exceptions.py`."""
