import os
from enum import Enum
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

JINJA_TEMPLATE_ROOT_PATH = Path(__file__).parent

JINJA_ENV = Environment(loader=FileSystemLoader(JINJA_TEMPLATE_ROOT_PATH))