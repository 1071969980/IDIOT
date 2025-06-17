from .router_declare import router
from .data_model import *

@router.post(
    "/suggestion_merge",
)
async def suggestion_merge(request: SuggestionMergeRequest) -> SuggestionMergeResponse:
    pass


@router.get(
    "/suggestion_merge/{task_id}",
)
async def get_suggestion_merge_result(task_id: str) -> SuggestionMergeResponse:
    pass