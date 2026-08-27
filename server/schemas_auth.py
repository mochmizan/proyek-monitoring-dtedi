# schemas_auth.py
# Validasi Payload & Skema Respons Autentikasi HubGate V5

from pydantic import BaseModel, ConfigDict

class UserLoginPayload(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)
