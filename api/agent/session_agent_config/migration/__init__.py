from typing import Callable
from .version_pair import SessionAgentConfigMigrationVersionPair
from ..config_data_model import SessionAgentConfig

MIGRATION_FUNC: dict[SessionAgentConfigMigrationVersionPair, Callable[[SessionAgentConfig], SessionAgentConfig]] = {
    # SessionAgentConfigMigrationVersionPair("0.0.1", "0.0.2"): lambda config: config,
}