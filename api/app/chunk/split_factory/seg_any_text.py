from wtpsplit import SaT
from functools import lru_cache
from deprecation import deprecated

@lru_cache(maxsize=1)
def _SaT_model():
    return SaT("sat-3l-sm")

@deprecated("this method should be redefined as requesting model by async network")
def split_into_sentences(text: str | list[str]) -> list[str]:
    """Single paragraph (str) will be split into one sentences list.
    Multiple paragraphs (list[str]) will be split into one sentences list too, which is
      as joined split res list for each paragraph.
    """
    itor = _SaT_model().split(text, split_on_input_newlines=False)

    res = []
    for sentes in itor:
        if isinstance(sentes, list):
            res.extend(sentes)
        else:
            res.append(sentes)
    # remove length 0 sentence
    res = [sent for sent in res if len(sent) > 0]
    return res