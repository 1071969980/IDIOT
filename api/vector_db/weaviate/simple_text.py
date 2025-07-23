from ..vector_db_base import BaseVectorDB
from dataclasses import dataclass
from weaviate.classes.config import Property


@dataclass
class SimpleTextObeject_Weaviate:
    collection_name: str
    tenent_name: str
    text: str

SIMPLE_TEXT_OBEJECT_SCHEMA = [
    Property(
        name="text",
        dataType="text",
        description="Text to store",
        tokenization="trigram"
    ),
    Property(
        name="metadata",
        dataType="object",
        description="Metadata to store",
    )
]