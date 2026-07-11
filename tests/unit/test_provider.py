import pytest

from another_atom.agent.provider import LLMProviderError, MockLLMProvider, OllamaCloudProvider
from another_atom.config import get_settings
from another_atom.contracts.schemas import LeadRoute, Mode, SupportLevel


@pytest.fixture
def provider() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Build a product catalog for lamps", SupportLevel.SUPPORTED),
        ("Build a catalog with login and payment", SupportLevel.ADAPTED),
        ("Build a CRM for sales teams", SupportLevel.UNSUPPORTED),
    ],
)
def test_support_classification(
    provider: MockLLMProvider, prompt: str, expected: SupportLevel
) -> None:
    assert provider.create_blueprint(prompt, Mode.TEAM).support_level == expected


def test_mock_failure_hook_is_explicit(provider: MockLLMProvider) -> None:
    with pytest.raises(LLMProviderError):
        provider.create_blueprint("Catalog [fail:llm]", Mode.TEAM)
    assert provider.take_usage().request_count == 1


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What can this version build?", LeadRoute.DIRECT),
        ("Build a catalog for desk lamps", LeadRoute.TEAM),
        ("请创建一个家居产品目录", LeadRoute.TEAM),
    ],
)
def test_lead_routes_questions_and_build_requests(
    provider: MockLLMProvider, message: str, expected: LeadRoute
) -> None:
    assert provider.route_message(message).route == expected


def test_force_team_does_not_spend_a_lead_model_call(provider: MockLLMProvider) -> None:
    assert provider.route_message("Maybe a catalog", force_team=True).route == LeadRoute.TEAM
    assert provider.take_usage().request_count == 0


def test_provider_outputs_complete_renderer_contract(provider: MockLLMProvider) -> None:
    prompt = "Build a product catalog called Mono Market"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)
    assert {page.route for page in app_spec.pages} >= {"/", "/catalog"}
    assert any(page.route.startswith("/product/") for page in app_spec.pages)
    assert len(app_spec.products) >= 3
    assert provider.take_usage().request_count == 3


def test_ollama_provider_records_response_token_usage(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    blueprint = MockLLMProvider().create_blueprint("Build a catalog", Mode.TEAM)

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "message": {"content": blueprint.model_dump_json()},
                "prompt_eval_count": 120,
                "eval_count": 80,
            }

    monkeypatch.setattr(
        "another_atom.agent.provider.httpx.post",
        lambda *args, **kwargs: Response(),
    )
    provider = OllamaCloudProvider(model="deepseek-v4-pro")
    result = provider.create_blueprint("Build a catalog", Mode.TEAM)
    usage = provider.take_usage()
    assert result.project_name == blueprint.project_name
    assert usage.request_count == 1
    assert usage.input_tokens == 120
    assert usage.output_tokens == 80
    get_settings.cache_clear()
