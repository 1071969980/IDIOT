from ..data_model import SplitConfig, RegexConfig
from .processor_base import ProcessorBase
import re

class RegexProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        super().__init__(text, config)
        
    def pre_process(self) -> None:
        re_str = self.split_config.regex
        matches = re.finditer(re_str, self.text)
        self.split_result = self.__split_text_by_regex_match(matches, self.split_config)
    
    def __split_text_by_regex_match(self, matches: list[re.Match], config: RegexConfig) -> list[str]:
        res = []
        for i, match in enumerate(matches):
            chunk = self.text[:match.start()] if i == 0 else self.text[matches[i-1].end():match.start()]
            res.append(chunk)
        res.append(self.text[matches[-1].end():])
        
        if config.keep_regex_match:
            if config.keep_as_prefix:
                to_prefix = res[1:]
                for i, match in enumerate(matches):
                    to_prefix[i] = match.group() + to_prefix[i]
                res = res[0] + to_prefix
            if config.keep_as_suffix:
                to_suffix = res[:-1]
                for i, match in enumerate(matches):
                    to_suffix[i] = to_suffix[i] + match.group()
                res = to_suffix + res[-1]
                
        return res
        
    
    
