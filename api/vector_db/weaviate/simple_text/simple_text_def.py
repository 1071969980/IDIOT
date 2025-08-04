from dataclasses import dataclass

from numpy import ndarray
from weaviate.classes.config import Property
from weaviate.collections.classes.config import DataType, Tokenization


@dataclass
class SimpleTextObeject_Weaviate:
    text: str
    collection_name: str | None
    tenant_name: str | None
    vector: list[float] | ndarray | None

SIMPLE_TEXT_OBEJECT_SCHEMA = [
    Property(
        name="text",
        data_type=DataType.TEXT,
        description="Text to store",
        tokenization=Tokenization.TRIGRAM,
    ),
]
