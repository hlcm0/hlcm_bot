from pydantic import BaseModel, Field


class AiAgentConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    model: str = ""
    safeguard_model: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.3
    max_tokens: int = 1024
    system_prompt: str = (
        "你是一个 AI 助手，你的名字叫草莓。"
    )
    first_ai_message: str = "你好呀，我是草莓。有什么可以帮你的吗？"


class Config(BaseModel):
    ai_agent: AiAgentConfig = Field(default_factory=AiAgentConfig)
