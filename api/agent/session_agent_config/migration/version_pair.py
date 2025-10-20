from pydantic import BaseModel
from pydantic import field_validator, ValidationError
from typing import Any
        
class SessionAgentConfigMigrationVersionPair(BaseModel):
    from_version: str
    to_version: str

    @field_validator("from_version", "to_version", mode="before")
    @classmethod
    def validate_from_version(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.startswith("v"):
            raise ValidationError("from_version and to_version must start with 'v'")
        
    def __hash__(self):
        return hash((self.from_version, self.to_version))
    
    def __eq__(self, other):
        if isinstance(other, SessionAgentConfigMigrationVersionPair):
            return self.from_version == other.from_version and self.to_version == other.to_version
        return False
