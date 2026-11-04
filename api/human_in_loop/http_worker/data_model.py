"""HIL HTTP 上行接口数据模型。"""

import uuid

from pydantic import BaseModel


class HILResponseRequest(BaseModel):
    """中断响应请求模型。"""

    session_task_id: uuid.UUID
    hil_msg_id: str
    msg: str | dict


class HILAckNotificationRequest(BaseModel):
    """Notification 确认请求模型。"""

    session_task_id: uuid.UUID
    hil_msg_id: str
