from ..data_model import RegexConfig, SeparatorConfig, SplitConfig, SplitType, KamradtChunkConfig
from .md_strc_processor import MarkdownSturctProcessor
from .regex_processor import RegexProcessor
from .separator_processor import SeparatorProcessor
from .sat_processor import SegAnyTextProcessor
from .kamardt_processor import KamradtChunkProcessor


def validate_split_config(config: SplitConfig) -> bool:
    if config.type == SplitType.separator:
        return isinstance(config.config, SeparatorConfig)
    elif config.type == SplitType.regex:
        return isinstance(config.config, RegexConfig)
    elif config.type == SplitType.kamradt_chunk:
        return isinstance(config.config, KamradtChunkConfig)
    elif config.type in (SplitType.markdown_block, SplitType.sentence):
        return config.config is None
    else:
        return False

async def split_text(text: str, config: SplitConfig) -> list[str]:
    if not validate_split_config(config):
        raise ValueError("Invalid split config")
    if config.type == SplitType.separator:
        worker = SeparatorProcessor(text, config)
        worker.process()
    elif config.type == SplitType.regex:
        worker = RegexProcessor(text, config)
        worker.process()
    elif config.type == SplitType.markdown_block:
        worker = MarkdownSturctProcessor(text, config)
        worker.process()
    elif config.type == SplitType.sentence:
        worker = SegAnyTextProcessor(text, config)
        await worker.process_async()
    elif config.type == SplitType.kamradt_chunk:
        worker = KamradtChunkProcessor(text, config)
        await worker.process_async()
    

    return worker.split_result
