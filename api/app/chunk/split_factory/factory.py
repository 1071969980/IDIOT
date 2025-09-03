from ..data_model import RegexConfig, SeparatorConfig, SplitConfig, SplitType
from .md_strc_processor import MarkdownSturctProcessor
from .regex_processor import RegexProcessor
from .separator_processor import SeparatorProcessor


def validate_split_config(config: SplitConfig) -> bool:
    if config.type == SplitType.separator:
        return isinstance(config.config, SeparatorConfig)
    elif config.type == SplitType.regex:
        return isinstance(config.config, RegexConfig)
    elif config.type == SplitType.markdown_block:
        return config.config is None
    else:
        return False

def split_text(text: str, config: SplitConfig) -> list[str]:
    if not validate_split_config(config):
        raise ValueError("Invalid split config")
    if config.type == SplitType.separator:
        worker = SeparatorProcessor(text, config)
    elif config.type == SplitType.regex:
        worker = RegexProcessor(text, config)
    elif config.type == SplitType.markdown_block:
        worker = MarkdownSturctProcessor(text, config)
    worker.process()
    return worker.split_result
