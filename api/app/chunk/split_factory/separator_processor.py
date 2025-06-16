from ..data_model import SplitConfig
from .processor_base import ProcessorBase

class SeparatorProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        super().__init__(text, config)
        
    def pre_process(self) -> None:
        self.split_result = self.__split_text_by_separator(self.text, self.split_config)
        
    def __split_text_by_separator(self) -> list[str]:
        if self.split_config.keep_separator:
            res = [s for s in self.text.split(self.split_config.separator) if s]
            if self.split_config.keep_as_prefix:
                res = [self.split_config.separator + s for s in res]
                res[0] = res[0][len(self.split_config.separator):]
            if self.split_config.keep_as_suffix:
                res = [s + self.split_config.separator for s in res]
                res[-1] = res[-1][:-len(self.split_config.separator)]
    
        return [s for s in self.text.split(self.split_config.separator) if s]
    
    
