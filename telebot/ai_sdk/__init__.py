from .base import AIProvider
from .openai_client import OpenAIClient

def get_ai_provider(config: dict) -> AIProvider:
    provider_type = config.get('provider', 'openai')
    
    if provider_type == 'openai':
        return OpenAIClient(
            api_key=config.get('api_key'),
            base_url=config.get('base_url'),
            model=config.get('model', 'gpt-3.5-turbo')
        )
    # Add other providers here
    return None
