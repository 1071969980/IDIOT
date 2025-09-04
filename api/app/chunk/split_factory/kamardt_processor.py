from .processor_base import ProcessorBase
from ..data_model import SplitConfig, SplitType, KamradtChunkConfig, LengthLimitConfig
from api.load_balance import LOAD_BLANCER, QWEN_TEXT_EMBEDDING_SERVICE_NAME
from api.llm.generator import DEFAULT_RETRY_CONFIG
from api.load_balance.delegate.openai import embedding_delegate_for_async_openai
from .seg_any_text import split_into_sentences

import numpy as np

class KamradtChunkProcessor(ProcessorBase):
    def __init__(self, text: str, config: SplitConfig):
        if not config.type == SplitType.kamradt_chunk or \
            not isinstance(config.config, KamradtChunkConfig):
            raise ValueError("Invalid split config")
        super().__init__(text, config)
        self.sentences = []
        self.sentences_embeddings = None

    async def pre_process_async(self):

        assert(isinstance(self.split_config, KamradtChunkConfig))
        except_chunk_size = self.split_config.except_chunk_size
        text_length = len(self.text)
        except_chunk_num = max(1, text_length // except_chunk_size)
        if except_chunk_num == 1:
            self.split_result = [self.text]
            return

        # split text into sentences using SAT
        self.sentences = split_into_sentences(self.text)
        # merge sentences with window config
        if self.split_config.sentence_window > 1:
            window_size = self.split_config.sentence_window
            window_offset = self.split_config.sentence_window_offset
            offset_prefix = window_size - 1 - window_offset
            offset_suffix = 1 + window_offset
            merged_sentences = []
            for i, _ in enumerate(self.sentences):
                from_index = max(0, i - offset_prefix)
                to_index = min(len(self.sentences), i + offset_suffix)
                merged_sentences.append("".join(self.sentences[from_index:to_index]))
        else:
            merged_sentences = self.sentences
        
        # calculate embeddings
        async def delegate(instance):
            return await embedding_delegate_for_async_openai(
                instance,
                merged_sentences,
                DEFAULT_RETRY_CONFIG
            )
        
        res = await LOAD_BLANCER.execute(
            QWEN_TEXT_EMBEDDING_SERVICE_NAME,
            delegate
        )

        self.sentences_embeddings = [np.array(embedding.embedding) for embedding in res.data]
        self.sentences_embeddings = np.stack(self.sentences_embeddings)

        # calculate cosine distances to previous embeddings
        _pre_sentences_embeddings = self.sentences_embeddings[:-1]
        _cur_sentences_embeddings = self.sentences_embeddings[1:]
        pre_sentences_distance: np.ndarray = np.einsum("si,si-> s", # s := sentence count, i := embedding dimension
                                           _pre_sentences_embeddings, 
                                           _cur_sentences_embeddings)
        normal_term = np.linalg.norm(_pre_sentences_embeddings, axis=1) * \
            np.linalg.norm(_cur_sentences_embeddings, axis=1)
        pre_sentences_distance = pre_sentences_distance / normal_term
        pre_sentences_distance = 1 - pre_sentences_distance # distance should be in [0, 1]
        distance_list: list[float] = pre_sentences_distance.tolist()
        distance_list.insert(0, 1) # insert 1 at the beginning, so that the distance list has the same length as the sentence list

        # find (using dichotomy) the split points which satisfy the except chunk length
        max_iter = 20
        threshold = 0.5
        low_bound = 0
        high_bound = 1
        
        for i in range(max_iter):
            split_index = [i for i, distance in enumerate(distance_list) if distance < threshold]
            if len(split_index) == except_chunk_num:
                break
            if len(split_index) > except_chunk_num:
                high_bound = threshold
                threshold = (low_bound + high_bound) / 2
            else:
                low_bound = threshold
                threshold = (low_bound + high_bound) / 2
        
        split_index.insert(0, 0)
        split_index.append(len(self.sentences))

        self.split_result = [
            "".join(self.sentences[split_index[i]:split_index[i+1]])
            for i in range(len(split_index) - 1)
        ]
