from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class URLBase(BaseModel):
    url: str
    domain: Optional[str] = None
    threat: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None


class URLCreate(URLBase):
    # `date_added` is optional on create; if omitted the service/model
    # can set the current time automatically.
    date_added: Optional[datetime] = None


class URLUpdate(BaseModel):
    # All fields optional for partial updates (PATCH-like behavior).
    url: Optional[str] = None
    domain: Optional[str] = None
    threat: Optional[str] = None
    date_added: Optional[datetime] = None
    status: Optional[str] = None
    source: Optional[str] = None


class URLResponse(URLBase):
    id: int
    date_added: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class URLListResponse(BaseModel):
    items: list[URLResponse]
    total: int
    page: int
    per_page: int

    model_config = ConfigDict(from_attributes=True)



class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: Optional[bool] = False


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
