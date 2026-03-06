from fastapi import APIRouter

router = APIRouter(
    prefix="/juicefs",
    tags=["JuiceFS 测试接口"],
)