from api.agent.session_agent_config.config_data_model import (
    SessionSystemPromptConfig,
    SessionSystemPromptDef,
    SessionSystemPromptDefByJinja,
    SessionSystemPromptDefByJinjaString,
    SessionSystemPromptDefByLangFuse,
    SessionSystemPromptDefByPlainText,
    SessionSystemPromptDefByVariable,
)
from api.app.chat.exception import SystemPromptRenderError
from api.prompt_template.jinja_prompt_template import JINJA_ENV
from api.prompt_template.langfuse_prompt_template import get_prompt_from_langfuse


def _render_params(
    params: dict[str, SessionSystemPromptDef | object] | None,
    variables: dict[str, str],
) -> dict[str, str | object]:
    """递归渲染 params 中值为 SessionSystemPromptDef 的条目，其他值原样传入。"""
    if params is None:
        return {}
    rendered = {}
    for key, value in params.items():
        if isinstance(value, SessionSystemPromptDef):
            rendered[key] = _render_single_def(value, variables)
        else:
            rendered[key] = value
    return rendered


def _render_single_def(defn: SessionSystemPromptDef, variables: dict[str, str]) -> str:
    """渲染单个 SessionSystemPromptDef 为字符串。"""
    if isinstance(defn, SessionSystemPromptDefByPlainText):
        return defn.text

    if isinstance(defn, SessionSystemPromptDefByVariable):
        value = variables.get(defn.variable_name)
        if value is None:
            raise SystemPromptRenderError(f"Variable not provided: {defn.variable_name}")
        return value

    if isinstance(defn, SessionSystemPromptDefByLangFuse):
        prompt_client = get_prompt_from_langfuse(
            prompt_path=str(defn.prompt_path),
            production=defn.production,
            label=defn.label,
            version=defn.version,
        )
        if prompt_client is None:
            raise SystemPromptRenderError(f"Langfuse prompt not found: {defn.prompt_path}")
        rendered_params = _render_params(defn.params, variables)
        if rendered_params:
            return prompt_client.compile(**rendered_params)
        return prompt_client.prompt

    if isinstance(defn, SessionSystemPromptDefByJinja):
        rendered_params = _render_params(defn.params, variables)
        template = JINJA_ENV.get_template(str(defn.template_rel_path))
        return template.render(**rendered_params)

    if isinstance(defn, SessionSystemPromptDefByJinjaString):
        rendered_params = _render_params(defn.params, variables)
        template = JINJA_ENV.from_string(defn.template)
        return template.render(**rendered_params)

    raise SystemPromptRenderError(f"Unknown SessionSystemPromptDef type: {type(defn).__name__}")


def render_system_prompt(config: SessionSystemPromptConfig, **variables: str) -> str:
    """
    将 SessionSystemPromptConfig 渲染为最终的系统提示词字符串。

    处理逻辑：
    1. 应用白名单或黑名单（同时存在仅应用白名单）
    2. 按 index 排序
    3. 递归渲染每个 PromptDef
    4. 拼接返回

    Args:
        config: 系统提示配置
        **variables: 传递给 SessionSystemPromptDefByVariable 的动态变量
    """
    defs = list(config.prompt_defs)

    if config.white_list is not None:
        allowed = set(config.white_list)
        defs = [d for d in defs if d.index in allowed]
    elif config.black_list is not None:
        blocked = set(config.black_list)
        defs = [d for d in defs if d.index not in blocked]

    defs.sort(key=lambda d: d.index)

    rendered_parts = [_render_single_def(d, variables) for d in defs]
    return "\n".join(rendered_parts)
