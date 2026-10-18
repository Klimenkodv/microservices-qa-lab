from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            value = value.strip().lower()
            if len(value) > 254:
                raise ValueError("Email must be at most 254 characters")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not 8 <= len(value) <= 72:
            raise ValueError("Password must contain 8 to 72 characters")
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one letter and one digit")
        return value


class UserResponse(BaseModel):
    user_id: str
    email: str
    created_at: str


class RegisterResponse(UserResponse):
    access_token: str
    token_type: str = "bearer"


class ProfileResponse(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    birth_date: str
    city: str
    description: str
    country: str
    created_at: str
    updated_at: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    birth_date: str = ""
    city: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    country: str = Field(default="", max_length=100)
