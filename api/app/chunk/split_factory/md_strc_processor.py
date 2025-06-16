from ..data_model import SplitConfig
from .processor_base import ProcessorBase
from mrkdwn_analysis import MarkdownAnalyzer, markdown_analyzer

class MarkdownSturctProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        super().__init__(text, config)
        
    def pre_process(self) -> None:
        md_strc = MarkdownAnalyzer.from_string(self.text)
        for token in md_strc.tokens:
            self.split_result.append(self.__present_token(token)+"\n\n")
        
    def __present_token(self, token: markdown_analyzer.BlockToken) -> str | None:
        if token.type == 'header':
            level = token.level
            text = token.content
            return "#"*level + " " + text
        elif token.type == 'paragraph':
            text = token.content
            return text
        elif token.type == 'blockquote':
            text = token.content
            res = []
            for line in text.split("\n"):
                res.append("> " + line)
            res = "\n".join(res)
            return res
        elif token.type == 'code':
            text = token.content
            return "```" + token.meta.get("language") + "\n"+ \
                text + "\n" + \
                "```"
        elif token.type == 'ordered_list' or token.type == 'unordered_list':
            items = token.meta["items"]
            if token.type == 'ordered_list':
                items_str = []
                for i, item in enumerate(items):
                    if item.get("task_item"):
                        if item.get("checked"):
                            items_str.append(f"{i+1}. [x] {item['text']}")
                        else:
                            items_str.append(f"{i+1}. [ ] {item['text']}")
                    else:
                        items_str.append(f"{i+1}. {item['text']}")
                return "\n".join(items_str)
            else:
                items_str = []
                for item in items:
                    if item.get("task_item"):
                        if item.get("checked"):
                            items_str.append(f"- [x] {item['text']}")
                        else:
                            items_str.append(f"- [ ] {item['text']}")
                    else:
                        items_str.append(item["text"])
                return "\n".join(items_str)
        elif token.type == 'table':
            header = token.meta["header"]
            rows = token.meta["rows"]
            header_str = "| " + " | ".join(header) + " |"
            table_split = "|" + "|".join(["---"] * len(header)) + "|"
            for i, row in enumerate(rows):
                rows[i] = "| " + " | ".join(row) + " |"
            row_str = "\n".join(rows)
            return header_str + "\n" + table_split + "\n" + row_str
        else:
            return None