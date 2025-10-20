from pydantic import BaseModel

class HILData(BaseModel):
    pass

class U2ASessionLinkData(BaseModel):
    title: str

class ToolTaskResult(BaseModel):
    text: str
    HIL_data: list[HILData] | None
    u2a_session_link_data: U2ASessionLinkData | None
