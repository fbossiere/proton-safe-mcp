"""Client adapters. Each one owns exactly the resources it created."""

from .base import ClientAdapter, CommandResult, CommandRunner
from .openai_local import OpenAILocalAdapter

__all__ = ["ClientAdapter", "CommandResult", "CommandRunner", "OpenAILocalAdapter"]
