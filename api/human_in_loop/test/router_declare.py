from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.human_in_loop.context import HILMessageStreamContext
from api.human_in_loop.interrupt import interrupt

# 创建API路由器
router = APIRouter(
    prefix="/hil/test",
    tags=["human-in-loop-test"]
)

class SimpleMsg(BaseModel):
    msg: str

@router.get("/")
async def test_hil():
    """测试HIL"""
    async with HILMessageStreamContext(["test"]) as ctx:
        res = await interrupt(SimpleMsg(msg="this is a test msg"), "test")
    
    return {"msg": "success", "data": res}