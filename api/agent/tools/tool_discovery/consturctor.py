import re
from typing import Any

import bm25s
import ujson
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition
from pydantic import ValidationError

from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.xml_marks_constant import TOOL_DISCOVERY_RESULT_BLOCK_START, TOOL_DISCOVERY_RESULT_BLOCK_END 

from .bm25_tokenizer import BM25MultilingualTokenizer
from .config_data_model import (TOOL_NAME,
                                TOOL_DESCRIPTION,
                                ToolDiscoveryToolParamDefine)

_DESC_TRUNCATE_LEN = 200

class ToolDiscoveryTool:

    def __init__(self,
                 tool_params: list[ChatCompletionToolParam],
                 bm25_index: bm25s.BM25,
                 tokenizer: BM25MultilingualTokenizer) -> None:
        self._tool_params = tool_params
        self._bm25_index = bm25_index
        self._tokenizer = tokenizer

    # ---- helpers ----

    def _tool_name(self, idx: int) -> str:
        return self._tool_params[idx]["function"]["name"]  # type: ignore[index]

    def _tool_desc(self, idx: int) -> str:
        return self._tool_params[idx]["function"].get("description", "") or ""  # type: ignore[union-attr]

    def _tool_text(self, idx: int) -> str:
        return f"{self._tool_name(idx)} {self._tool_desc(idx)}"

    @staticmethod
    def _truncate_desc(desc: str) -> str:
        if len(desc) > _DESC_TRUNCATE_LEN:
            return desc[:_DESC_TRUNCATE_LEN] + "..." + "(tool description is truncated)"
        return desc

    _NO_IMPLICIT_TOOLS = "there are no implicit tools available."

    def _format_search_result(self, indices: list[int]) -> str:
        if not self._tool_params:
            return self._NO_IMPLICIT_TOOLS
        if not indices:
            return "No matching tools found."
        lines: list[str] = []
        for i in indices:
            name = self._tool_name(i)
            desc = self._truncate_desc(self._tool_desc(i))
            lines.append(f" *{name}*: {desc}")
        return "\n".join(lines)

    # ---- search modes ----

    def _search_grep(self, regex: str, limit: int | None) -> str:
        corpus_size = len(self._tool_params)
        if corpus_size == 0:
            return self._NO_IMPLICIT_TOOLS
        k = min(limit, corpus_size) if limit is not None else None
        pattern = re.compile(regex)
        matched: list[int] = []
        for i in range(corpus_size):
            if pattern.search(self._tool_text(i)):
                matched.append(i)
                if k is not None and len(matched) >= k:
                    break
        return self._format_search_result(matched)

    def _search_bm25(self, query: str, limit: int | None) -> str:
        corpus_size = len(self._tool_params)
        if corpus_size == 0:
            return self._NO_IMPLICIT_TOOLS
        k = min(limit if limit is not None else corpus_size, corpus_size)
        if k == 0:
            return "No tools available for search."
        query_tokens = [self._tokenizer.tokenize(query)]
        results = self._bm25_index.retrieve(query_tokens, k=k, show_progress=False)
        if not isinstance(results, bm25s.Results):
            raise TypeError(f"BM25.retrieve 应返回 Results 对象，实际为 {type(results)}")
        # results.documents 是 shape (num_queries, k) 的 numpy 数组
        indices: list[int] = [int(i) for i in results.documents[0]]
        return self._format_search_result(indices)

    # ---- reveal ----

    def _reveal(self, tool_names: list[str]) -> str:
        if not self._tool_params:
            return self._NO_IMPLICIT_TOOLS
        name_set = set(tool_names)
        lines: list[str] = []
        for i in range(len(self._tool_params)):
            if self._tool_name(i) in name_set:
                func_dict = self._tool_params[i]["function"]  # type: ignore[index]
                json_str = ujson.dumps(
                    {"name": func_dict["name"],
                     "description": func_dict.get("description", ""),
                     "parameters": func_dict.get("parameters", {})},
                    ensure_ascii=False,
                )
                lines.append(f"{TOOL_DISCOVERY_RESULT_BLOCK_START}\n{json_str}\n{TOOL_DISCOVERY_RESULT_BLOCK_END}")
        return "\n".join(lines) if lines else "No matching tools found."

    # ---- entry ----

    async def __call__(self, **kwargs: Any) -> ToolTaskResult:
        try:
            param = ToolDiscoveryToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(err["msg"] for err in e.errors())
            return ToolTaskResult(
                str_content=f"Invalid parameters:\n{error_msg}",
                occur_error=True,
            )

        if param.action == "search":
            if param.mode == "grep":
                result = self._search_grep(param.regex, param.limit)  # type: ignore[arg-type]
            else:  # bm25
                result = self._search_bm25(param.query, param.limit)  # type: ignore[arg-type]
        else:  # reveal
            result = self._reveal(param.tool_name)  # type: ignore[arg-type]

        return ToolTaskResult(str_content=result)


def construct_tool(
    implicit_tool_params: list[ChatCompletionToolParam],
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    # 1. 构建 LLM 可见的工具参数定义
    tool_param = ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=TOOL_NAME,
            description=TOOL_DESCRIPTION,
            parameters=turn_pydantic_model_to_json_schema(ToolDiscoveryToolParamDefine),
        ),
    )

    # 2. 构建BM25索引
    tokenizer = BM25MultilingualTokenizer()
    corpus_tokens: list[list[str]] = []
    for tp in implicit_tool_params:
        text = f"{tp['function']['name']} {tp['function'].get('description', '') or ''}"
        corpus_tokens.append(tokenizer.tokenize(text))

    retriever = bm25s.BM25()
    if corpus_tokens:
        retriever.index(corpus_tokens, show_progress=False)

    # 3. 实例化并返回
    tool_instance = ToolDiscoveryTool(
        tool_params=implicit_tool_params,
        bm25_index=retriever,
        tokenizer=tokenizer,
    )
    return tool_param, tool_instance
