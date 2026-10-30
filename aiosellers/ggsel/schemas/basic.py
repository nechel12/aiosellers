from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _parse_datetime(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return value
        if parsed is None:
            return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return value


GGselDateTime = Annotated[datetime, BeforeValidator(_parse_datetime)]


class ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )


class RetvalResponse(ApiModel):
    retval: int | None = None
    retdesc: str | None = None
    errors: list[str] | None = None
