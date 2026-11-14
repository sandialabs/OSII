"""Library-wide file presentation, independent of persistence and transport."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class FileDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    view: Literal["thumbnails", "list"] = "thumbnails"
    show_name: bool = True
    show_size: bool = False
    metadata: Literal["none", "format", "modified", "path"] = "none"


def display_settings(value: dict | None) -> dict:
    return FileDisplay.model_validate(value or {}).model_dump()
