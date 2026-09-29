from pydantic import BaseModel, EmailStr, field_validator


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
