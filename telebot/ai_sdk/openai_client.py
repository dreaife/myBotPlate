import logging
from openai import AsyncOpenAI
from .base import AIProvider

class OpenAIClient(AIProvider):
    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-3.5-turbo"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.logger = logging.getLogger(__name__)

    async def generate_summary(self, content: str, prompt: str = None) -> str:
        default_prompt = (
            "You are a helpful assistant that summarizes Telegram group chat logs. "
            "Please analyze the following conversation and group it into distinct topics or events.\n"
            "For each topic:\n"
            "1. Provide a concise bullet-point summary.\n"
            "2. IMPORTANT: You MUST include a link to the start of this topic. "
            "Use the [SourceLink] provided in the input for the first message of that topic.\n"
            "Format:\n"
            "### Topic Title ([Link to start](SourceLink))\n"
            "- Summary point 1\n"
            "- Summary point 2\n\n"
            "The input content format is:\n"
            "Msg: <text>\n"
            "SourceLink: <url>\n"
            "---\n"
            "Do not include images or videos in the summary. Output clear text.\n"
            "Note: Messages marked with '(Followed User ...)' are from high-priority users. "
            "You MUST give these users' messages higher weight in the summary. "
            "Explicitly mention their names and summarize what they discussed."
        )
        system_prompt = prompt if prompt else default_prompt

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"OpenAI API Error: {e}")
            return f"Error generating summary: {e}"
