from pydantic import BaseModel

class HILData(BaseModel):
    pass

class U2ASessionLinkData(BaseModel):
    title: str
    session_id: str

class A2ASessionLinkData(BaseModel):
    goal: str
    session_id: str
    

class ToolTaskResult(BaseModel):
    text: str
    occur_error: bool = False
    HIL_data: list[HILData] | None = None
    u2a_session_link_data: U2ASessionLinkData | None = None
    a2a_session_link_data: A2ASessionLinkData | None = None
