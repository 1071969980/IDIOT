from enum import Enum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

JINJA_TEMPLATE_ = Path(__file__).parent

class AvailableTemplates(str, Enum):
    ContractReview = "contract_review.jinja"
    ContractReviewJsonFormatter = "contract_review_json_formatter.jinja"

JINJA_ENV = Environment(loader=FileSystemLoader(JINJA_TEMPLATE_))