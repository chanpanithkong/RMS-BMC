from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")

# Money is serialised as a decimal string ("12.99"), never a JSON float (SRS §13.1).
MoneyOut = Annotated[Decimal, PlainSerializer(lambda v: format(v.normalize() if v == v.to_integral() else v, "f") if v is not None else None, return_type=str)]


def money_str(value: Decimal | None, places: int = 2) -> str | None:
    if value is None:
        return None
    return f"{value:.{places}f}"


class Strict(BaseModel):
    """Request bodies reject unknown fields (§13.4)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int
    page_size: int


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)


class Message(BaseModel):
    message: str
