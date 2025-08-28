from enum import Enum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

JINJA_TEMPLATE_ = Path(__file__).parent

class AvailableTemplates(str, Enum):
    ContractReview = "contract_review.jinja"
    ContractReviewJsonFormatter = "contract_review_json_formatter.jinja"
    SuggestionMerge = "suggestion_merge.jinja"
    SuggestionMergeJsonFormatter = "suggestion_merge_json_formatter.jinja"
    JsonExtract = "json_extract.jinja"
    JsonExtractErrorExplanation = "json_extractor_error_explanation.jinja"

JINJA_ENV = Environment(loader=FileSystemLoader(JINJA_TEMPLATE_))