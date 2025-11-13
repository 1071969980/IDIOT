from .constant import LANGFUSE_CLIENT, _get_prompt_from_langfuse
from enum import Enum

NAME_SAPCE = "main_agent"

class AvailableTemplates(str, Enum):
    system = "system_prompt"

# Get production prompt
# prompt = langfuse.get_prompt("main_agent/system_prompt")

# Get by label
# You can use as many labels as you'd like to identify different deployment targets
# prompt = langfuse.get_prompt("main_agent/system_prompt", label="latest")

# Get by version number, usually not recommended as it requires code changes to deploy new prompt versions
# langfuse.get_prompt("main_agent/system_prompt", version=1)

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
