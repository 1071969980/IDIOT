"""
Session Agent Configuration Module

This module provides command-pattern-based API for managing session agent configurations.
It includes functionality for getting, updating, and resetting session configurations
using a database-backed storage system.
"""

# Import main components with safe fallbacks to avoid import errors
from .config_data_model import SessionAgentConfig