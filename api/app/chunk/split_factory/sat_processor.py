from .processor_base import ProcessorBase
from ..data_model import SplitConfig
from .seg_any_text import split_into_sentences

class SegAnyTextProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        super().__init__(text, config)

    async def pre_process_async(self):
        self.split_result = split_into_sentences(self.text)