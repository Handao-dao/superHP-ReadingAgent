import asyncio
from types import SimpleNamespace

from superhp_agent.config import Settings
from superhp_agent.contracts import LLMResponse
from superhp_agent.providers.base import BaseLLMProvider, GenerationSettings
from superhp_agent.providers.factory import make_provider
from superhp_agent.providers.openai_compat import OpenAICompatProvider
from superhp_agent.providers.registry import find_by_name, match_by_model


class ScriptedProvider(BaseLLMProvider):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = 0
        self.last_kwargs = {}

    async def chat(self, messages, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return self.responses.pop(0)

    def get_default_model(self):
        return "scripted"


def test_registry_finds_deepseek_by_name_and_model():
    assert find_by_name("deepseek").default_api_base == "https://api.deepseek.com"
    assert match_by_model("deepseek-v4-pro").name == "deepseek"


def test_openai_compat_parse_dict_response():
    result = OpenAICompatProvider._parse({
        "choices": [{
            "message": {"content": "hello"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    })

    assert result.content == "hello"
    assert result.usage["total_tokens"] == 3


def test_openai_compat_parses_native_tool_calls():
    result = OpenAICompatProvider._parse({
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "search_local_book_catalog",
                        "arguments": '{"genres":["mystery"]}',
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
    })

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0].id == "call-1"
    assert result.tool_calls[0].name == "search_local_book_catalog"
    assert result.tool_calls[0].arguments == {"genres": ["mystery"]}
    assert result.tool_calls[0].raw_arguments == '{"genres":["mystery"]}'


def test_openai_compat_preserves_invalid_tool_argument_error():
    result = OpenAICompatProvider._parse({
        "choices": [{
            "message": {
                "tool_calls": [{
                    "id": "call-bad",
                    "function": {
                        "name": "search_local_book_catalog",
                        "arguments": "{bad-json",
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
    })

    assert result.tool_calls[0].arguments == {}
    assert "invalid tool arguments JSON" in (
        result.tool_calls[0].arguments_error
    )


def test_openai_compat_parse_object_response():
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="hello object", reasoning_content=None),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )

    result = OpenAICompatProvider._parse(response)

    assert result.content == "hello object"
    assert result.usage["total_tokens"] == 5


def test_openai_compat_build_kwargs_adds_deepseek_thinking_disabled():
    provider = OpenAICompatProvider(
        api_key="sk-test",
        api_base="https://api.deepseek.com",
        default_model="deepseek-v4-pro",
        spec=find_by_name("deepseek"),
    )

    kwargs = provider._build_kwargs(
        messages=[{"role": "user", "content": "hi", "internal": "drop"}],
        tools=[{
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search.",
                "parameters": {"type": "object"},
            },
        }],
        model=None,
        max_tokens=128,
        temperature=0.2,
        reasoning_effort=None,
        extra_body=None,
    )

    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["tools"][0]["function"]["name"] == "search"
    assert "internal" not in kwargs["messages"][0]


def test_chat_with_retry_uses_generation_defaults():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="ok")])
        provider.generation = GenerationSettings(temperature=0.1, max_tokens=123)

        await provider.chat_with_retry(messages=[{"role": "user", "content": "hi"}])

        assert provider.last_kwargs["temperature"] == 0.1
        assert provider.last_kwargs["max_tokens"] == 123

    asyncio.run(run_case())


def test_chat_with_retry_forwards_tool_definitions():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="ok")])
        tools = [{
            "type": "function",
            "function": {
                "name": "search",
                "parameters": {"type": "object"},
            },
        }]

        await provider.chat_with_retry(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )

        assert provider.last_kwargs["tools"] == tools

    asyncio.run(run_case())


def test_chat_with_retry_retries_transient_error(monkeypatch):
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="429 rate limit", finish_reason="error"),
            LLMResponse(content="ok"),
        ])
        delays = []

        async def fake_sleep(delay):
            delays.append(delay)

        monkeypatch.setattr("superhp_agent.providers.base.asyncio.sleep", fake_sleep)

        result = await provider.chat_with_retry(messages=[{"role": "user", "content": "hi"}])

        assert result.content == "ok"
        assert provider.calls == 2
        assert delays == [1.0]

    asyncio.run(run_case())


def test_factory_creates_openai_compat_provider():
    settings = Settings(
        llm_provider="deepseek",
        llm_model_id="deepseek-v4-pro",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="sk-test",
        llm_temperature=0.3,
        llm_max_tokens=777,
    )

    provider = make_provider(settings)

    assert isinstance(provider, OpenAICompatProvider)
    assert provider.get_default_model() == "deepseek-v4-pro"
    assert provider.generation.temperature == 0.3
    assert provider.generation.max_tokens == 777
