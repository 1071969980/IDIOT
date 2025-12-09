from enum import Enum

from .constant import _get_prompt_from_langfuse

NAME_SAPCE = "main_agent_explicitily_assert"


class AvailableTemplates(str, Enum):
    concluding_prompt_template = "concluding_prompt_template"
    concluding_guidebook_test = "concluding_guidebook_test"
    guidence_system_prompt = "guidence_system_prompt"
    guidence_template = "guidence_template"
    conversation_script_test = "conversation_script_test"

def get_concluding_guidebook_test(
    production: bool = True,
    label: str | None = None,
    version: int | None = None,
) -> str:
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.concluding_guidebook_test.value}",
        production=production,
        label=label,
        version=version,
    )
    if prompt is None:
        raise Exception(f"langfuse prompt {NAME_SAPCE}/{AvailableTemplates.concluding_guidebook_test.value} not found")
    return prompt.prompt

def get_concluding_prompt(
    concluding_guidebook: str,
    tool_name: str,
    production: bool = True,
    label: str | None = None,
    version: int | None = None,
) -> str:
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.concluding_prompt_template.value}",
        production=production,
        label=label,
        version=version,
    )
    if prompt is None:
        raise Exception(f"langfuse prompt {NAME_SAPCE}/{AvailableTemplates.concluding_prompt_template.value} not found")

    return prompt.compile(
        concluding_guidebook=concluding_guidebook,
        tool_name=tool_name,
    )

def get_guidence_system_prompt(
    production: bool = True,
    label: str | None = None,
    version: int | None = None,
) -> str:
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.guidence_system_prompt.value}",
        production=production,
        label=label,
        version=version,
    )
    if prompt is None:
        raise Exception(f"langfuse prompt {NAME_SAPCE}/{AvailableTemplates.guidence_system_prompt.value} not found")
    
    return prompt.prompt

def get_guidence_prompt(
    conversation_script: str,
    conclusion: str,
    tool_name: str,
    production: bool = True,
    label: str | None = None,
    version: int | None = None,
) -> str:
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.guidence_template.value}",
        production=production,
        label=label,
        version=version,
    )
    if prompt is None:
        raise Exception(f"langfuse prompt {NAME_SAPCE}/{AvailableTemplates.guidence_template.value} not found")
    
    return prompt.compile(
        conversation_script=conversation_script,
        conclusion=conclusion,
        tool_name=tool_name,
    )

def get_conversation_script_test(
    production: bool = True,
    label: str | None = None,
    version: int | None = None,
) -> str:
    prompt = _get_prompt_from_langfuse(
        prompt_path=f"{NAME_SAPCE}/{AvailableTemplates.conversation_script_test.value}",
        production=production,
        label=label,
        version=version,
    )
    if prompt is None:
        raise Exception(f"langfuse prompt {NAME_SAPCE}/{AvailableTemplates.conversation_script_test.value} not found")
    
    return prompt.prompt