import pytest

from another_atom.agent.provider import LLMProviderError, MockLLMProvider
from another_atom.contracts.schemas import Mode, SupportLevel


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


def test_provider_outputs_complete_renderer_contract(provider: MockLLMProvider) -> None:
    prompt = "Build a product catalog called Mono Market"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    visual = provider.create_visual_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, visual, prompt)
    assert {page.route for page in app_spec.pages} >= {"/", "/catalog"}
    assert any(page.route.startswith("/product/") for page in app_spec.pages)
    assert len(app_spec.products) >= 3
