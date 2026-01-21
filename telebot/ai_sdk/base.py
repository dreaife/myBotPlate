from abc import ABC, abstractmethod

class AIProvider(ABC):
    @abstractmethod
    async def generate_summary(self, content: str, prompt: str = None) -> str:
        """Generate a summary from the given content."""
        pass
