from .constant import LANGFUSE_CLIENT, _get_prompt_from_langfuse
from enum import Enum

NAME_SAPCE = "main_agent"

class AvailableTemplates(str, Enum):
    system = "system_prompt"

def get_system_prompt(
        production: bool = True,
        label: str | None = None,
        version: int | None  = None
):
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.system.value}",
        production=production,
        label=label,
        version=version
    )
    return prompt.prompt if prompt else None
