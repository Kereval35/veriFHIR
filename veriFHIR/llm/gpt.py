from openai import OpenAI
from typing import Optional

class GPT:
    def __init__(self, guidelines_prompt: str, api_key: str, model: str):
        self._client = OpenAI(api_key = api_key)
        self._guidelines_prompt = guidelines_prompt
        self._model = model
    
    def get_client(self) -> OpenAI:
        return self._client
    
    def get_guidelines_prompt(self) -> str:
        return self._guidelines_prompt
    
    def get_model(self) -> str:
        return self._model
        
    def openai_chat_completion_response(self, prompt: str, response_format: Optional[dict] = None) -> Optional[str]:
        response = self.get_client().chat.completions.create(
            model = self.get_model(),
            messages = [
                    {"role": "system", "content": self.get_guidelines_prompt()},
                    {"role": "user", "content": prompt}
            ],
            seed=123,
            response_format = response_format
        ) #type: ignore
        return response.choices[0].message.content