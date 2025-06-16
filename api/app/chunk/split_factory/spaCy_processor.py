from ..data_model import SplitConfig
from .processor_base import ProcessorBase
from .spaCy_model import nlp_sm

class SpaCyProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        super().__init__(text, config)
        
    def pre_process(self) -> None:
        doc = nlp_sm(self.text)
        self.split_result = list(doc.sents)