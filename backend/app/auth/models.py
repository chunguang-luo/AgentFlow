from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class CurrentUser(BaseModel):
    id: str
    username: str
    email: str | None
    display_name: str | None
    role: str


class LoginResponse(CurrentUser):
    token: str
    token_type: str = "Bearer"
