import uuid

from pydantic import BaseModel


class PermissionMatrixEntry(BaseModel):
    id: uuid.UUID
    code: str
    label: str
    category: str
    granted_roles: list[str]


class SetRolePermissionRequest(BaseModel):
    role: str
    permission_id: uuid.UUID
    granted: bool
