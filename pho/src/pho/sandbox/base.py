"""
Base interface for code sandbox implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class ICodeSandbox(ABC):
    """Abstract base class for code sandbox."""

    @abstractmethod
    async def run_code(self, code: str, inputs: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """
        Run code and return result dictionary.

        Must ensure:
        1. The 'main' function in code is called.
        2. inputs are passed as parameters to main.
        3. Return value must be a Dict (or wrapped as Dict).
        """
        pass
