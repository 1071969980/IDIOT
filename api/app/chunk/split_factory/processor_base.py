from abc import ABC,abstractmethod
from ..data_model import SplitConfig, TruncateLevel
from seg_any_text import split_into_sentences

class ProcessorBase(ABC):
    def __init__(self, text: str, config: SplitConfig):
        self.text = text
        self.split_config = config.config
        self.length_limit_config = config.length_limit
        self.split_result =[]
    
    @abstractmethod
    def pre_process(self) -> None:
        raise NotImplementedError
        
    def post_process(self) -> None:
        if self.length_limit_config.min_length < 0 and\
            self.length_limit_config.max_length < 0:
            return self.split_result
        final_result = []
        while self.split_result:
            chunk = self.split_result.pop(0)
            # 长度过短
            if len(chunk) < self.length_limit_config.min_length and \
                self.length_limit_config.min_length > 0:
                if self.length_limit_config.max_length > 0: # 如果有最大长度限制
                    over_max_flag = len(chunk) + len(self.split_result[0]) > self.length_limit_config.max_length
                    while self.split_result and not over_max_flag :
                        chunk += self.split_result.pop(0)
                else:
                    while self.split_result:
                        chunk += self.split_result.pop(0)
                        if len(chunk) > self.length_limit_config.min_length:
                            break
                final_result.append(chunk)
            # 长度过长
            elif len(chunk) > self.length_limit_config.max_length and \
                self.length_limit_config.max_length > 0:
                final_result.append(self.truncate_text(chunk))
            else:
                final_result.append(chunk)
        self.split_result = final_result
        return None
    
    def process(self) -> None:
        self.pre_process()
        self.post_process()
        
    def truncate_text(self, text: str) -> str:
        if self.length_limit_config.turncate_level == TruncateLevel.char:
            return self.__truncate_at_char(text)
        elif self.length_limit_config.turncate_level == TruncateLevel.sentence:
            return self.__truncate_at_sentence(text)
        else:
            raise ValueError("Invalid turncate_level in SplitConfig")
        
    def __truncate_at_char(self, text: str) -> str:
        self.split_result.insert(0, text[self.length_limit_config.max_length:])
        return text[:self.length_limit_config.max_length]
    
    def __truncate_at_sentence(self, text: str) -> str:
        doc = split_into_sentences(text)
        output_text = ""
        truncated = False
        reserved_text = ""
        for sent in doc.sents:
            if not truncated:
                if output_text == "" or len(output_text) + len(sent) < self.length_limit_config.max_length:
                    output_text += sent.text
                else:
                    truncated = True
                    reserved_text += sent.text
            else:
                reserved_text += sent.text
        self.split_result.insert(0, reserved_text)
        return self.truncate_text(output_text)