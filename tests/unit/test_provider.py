import json

import httpx
import pytest

from another_atom.agent.provider import LLMProviderError, MockLLMProvider, OllamaCloudProvider
from another_atom.build.renderer import validate_app_spec
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    EngineerOutput,
    LeadRoute,
    Mode,
    ProjectLeadIntent,
    SourceFileDraft,
    SupportLevel,
)


@pytest.fixture
def provider() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Build a product catalog for lamps", SupportLevel.SUPPORTED),
        ("Build a catalog with login and payment", SupportLevel.ADAPTED),
        ("Build a CRM for sales teams", SupportLevel.ADAPTED),
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
        ("我想要实现一个翻译功能", LeadRoute.CLARIFY),
        ("Build a catalog for desk lamps", LeadRoute.TEAM),
        ("请创建一个家居产品目录", LeadRoute.TEAM),
        ("给我一个网页版扫雷", LeadRoute.TEAM),
    ],
)
def test_lead_routes_questions_and_build_requests(
    provider: MockLLMProvider, message: str, expected: LeadRoute
) -> None:
    assert provider.route_message(message).route == expected


def test_force_team_does_not_spend_a_lead_model_call(provider: MockLLMProvider) -> None:
    assert provider.route_message("Maybe a catalog", force_team=True).route == LeadRoute.TEAM
    assert provider.take_usage().request_count == 0


def test_ambiguous_build_intent_returns_structured_clarification(
    provider: MockLLMProvider,
) -> None:
    decision = provider.route_message("我想要实现一个翻译功能")

    assert decision.route == LeadRoute.CLARIFY
    assert len(decision.clarification_questions) == 2
    assert all(len(question.options) >= 2 for question in decision.clarification_questions)


def test_project_lead_answers_or_proposes_from_project_context(
    provider: MockLLMProvider,
) -> None:
    context = {
        "project_name": "Current Product",
        "application": {
            "primary_color": "#111111",
            "accent_color": "#2255aa",
            "background_color": "#ffffff",
        },
        "blueprint": {"modules": ["翻译输入", "翻译结果"]},
        "source_context": {
            "included_files": [
                {"path": "app.js", "content": "function translate() {}"}
            ]
        },
    }

    answer = provider.route_project_message("这个项目使用了哪些颜色？", context)
    proposal = provider.route_project_message("把主色改成蓝色", context)

    assert answer.intent == ProjectLeadIntent.ANSWER
    assert "Current Product" in answer.response
    assert "#2255aa" in answer.response
    assert proposal.intent == ProjectLeadIntent.PROPOSE_CHANGE
    assert proposal.change_summary == "把主色改成蓝色"


def test_ollama_project_lead_receives_project_source_context(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "message": {
                    "content": (
                        '{"intent":"answer","response":"Uses current code",'
                        '"reason":"Project context supplied","change_summary":null}'
                    )
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

    def fake_post(*args, **kwargs):
        captured.update(kwargs.get("json", {}))
        return Response()

    monkeypatch.setattr("another_atom.agent.provider.httpx.post", fake_post)
    provider = OllamaCloudProvider(model="deepseek-v4-flash")
    decision = provider.route_project_message(
        "现在怎么实现的？",
        {
            "project_name": "Current Product",
            "product_spec": {"content": "Approved product document"},
            "source_context": {
                "included_files": [
                    {"path": "app.js", "content": "function translate() {}"}
                ]
            },
        },
    )

    assert decision.intent == ProjectLeadIntent.ANSWER
    assert "Approved product document" in captured["messages"][1]["content"]
    assert "function translate() {}" in captured["messages"][1]["content"]
    assert captured["think"] is False
    get_settings.cache_clear()


def test_local_model_request_is_adapted_and_not_mapped_as_completed() -> None:
    provider = MockLLMProvider()
    blueprint = provider.create_blueprint(
        "创建一个可以调用本地大模型的翻译软件", Mode.TEAM
    )

    assert blueprint.support_level == SupportLevel.ADAPTED
    assert any("localhost" in item for item in blueprint.omitted_requirements)
    assert all("本地大模型" not in item for item in blueprint.mapped_requirements)


def test_ollama_lead_disables_thinking(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "message": {
                    "content": (
                        '{"route":"team","response":"Calling team","reason":"Explicit build"}'
                    )
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

    def fake_post(*args, **kwargs):
        captured.update(kwargs.get("json", {}))
        return Response()

    monkeypatch.setattr("another_atom.agent.provider.httpx.post", fake_post)
    provider = OllamaCloudProvider(model="deepseek-v4-flash")
    assert provider.route_message("给我一个网页版扫雷").route == LeadRoute.TEAM
    assert provider.take_usage().request_count == 1
    assert captured["think"] is False
    get_settings.cache_clear()


def test_ollama_timeout_falls_back_to_deepseek_official(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    get_settings.cache_clear()
    calls: list[tuple[str, dict]] = []

    class DeepSeekResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"route":"team","response":"Calling team",'
                                '"reason":"Explicit build"}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            }

    def fake_post(url, *args, **kwargs):
        calls.append((url, kwargs.get("json", {})))
        if "ollama.com" in url:
            raise httpx.ReadTimeout("primary timed out")
        return DeepSeekResponse()

    monkeypatch.setattr("another_atom.agent.provider.httpx.post", fake_post)
    provider = OllamaCloudProvider(model="deepseek-v4-flash")
    events: list[tuple[str, dict]] = []
    provider.begin_stage(
        timeout_seconds=60,
        event_handler=lambda event_type, payload: events.append((event_type, payload)),
    )
    decision = provider.route_message("给我一个网页版扫雷")
    usage = provider.take_usage()

    assert decision.route == LeadRoute.TEAM
    assert [url for url, _ in calls] == [
        "https://ollama.com/api/chat",
        "https://api.deepseek.com/chat/completions",
    ]
    assert calls[1][1]["thinking"] == {"type": "disabled"}
    assert usage.request_count == 2
    assert usage.fallback_provider == "deepseek"
    assert usage.input_tokens == 20
    assert usage.output_tokens == 8
    event_types = [event_type for event_type, _ in events]
    assert event_types.index("provider.timeout") < event_types.index(
        "provider.fallback.started"
    )
    assert event_types.index("provider.fallback.started") < event_types.index(
        "provider.response.received"
    )
    provider.end_stage()
    get_settings.cache_clear()


def test_provider_circuit_skips_repeated_primary_timeout(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    get_settings.cache_clear()
    calls: list[str] = []

    class DeepSeekResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"route":"team","response":"Calling team",'
                                '"reason":"Explicit build"}'
                            )
                        }
                    }
                ],
                "usage": {},
            }

    def fake_post(url, *args, **kwargs):
        calls.append(url)
        if "ollama.com" in url:
            raise httpx.ReadTimeout("primary timed out")
        return DeepSeekResponse()

    monkeypatch.setattr("another_atom.agent.provider.httpx.post", fake_post)
    provider = OllamaCloudProvider(model="deepseek-v4-flash")
    events: list[str] = []
    provider.begin_stage(
        timeout_seconds=60,
        event_handler=lambda event_type, payload: events.append(event_type),
    )

    assert provider.route_message("给我一个网页版扫雷").route == LeadRoute.TEAM
    assert provider.route_message("再给我一个网页版扫雷").route == LeadRoute.TEAM

    assert calls.count("https://ollama.com/api/chat") == 1
    assert calls.count("https://api.deepseek.com/chat/completions") == 2
    assert "provider.primary.skipped" in events
    provider.end_stage()
    get_settings.cache_clear()


def test_engineer_stream_is_buffered_before_contract_validation(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    mock = MockLLMProvider()
    prompt = "Build a translation tool"
    blueprint = mock.create_blueprint(prompt, Mode.TEAM)
    architecture = mock.create_architecture_spec(blueprint)
    expected = mock.create_app_spec(blueprint, architecture, prompt)
    encoded = expected.model_dump_json()
    midpoint = len(encoded) // 2
    captured: dict = {}

    class StreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({"message": {"content": encoded[:midpoint]}})
            yield json.dumps(
                {
                    "message": {"content": encoded[midpoint:]},
                    "done": True,
                    "prompt_eval_count": 120,
                    "eval_count": 80,
                }
            )

    def fake_stream(*args, **kwargs):
        captured.update(kwargs.get("json", {}))
        return StreamResponse()

    monkeypatch.setattr("another_atom.agent.provider.httpx.stream", fake_stream)
    provider = OllamaCloudProvider(model="deepseek-v4-pro")
    events: list[str] = []
    provider.begin_stage(
        timeout_seconds=60,
        event_handler=lambda event_type, payload: events.append(event_type),
    )

    result = provider.create_app_spec(blueprint, architecture, prompt)
    usage = provider.take_usage()

    assert result == expected
    assert captured["stream"] is True
    assert events.index("provider.request.started") < events.index("provider.first_token")
    assert events.index("provider.first_token") < events.index("provider.response.received")
    assert usage.request_count == 1
    assert usage.input_tokens == 120
    assert usage.output_tokens == 80
    provider.end_stage()
    get_settings.cache_clear()


def test_visible_stream_emits_only_message_and_validates_enveloped_result(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    blueprint = MockLLMProvider().create_blueprint("构建翻译工具", Mode.TEAM)
    visible = "我正在根据需求整理产品方案。"
    encoded = json.dumps(
        {"message": visible, "result": blueprint.model_dump(mode="json")},
        ensure_ascii=False,
    )
    chunks = [encoded[index : index + 9] for index in range(0, len(encoded), 9)]

    class VisibleStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            for index, chunk in enumerate(chunks):
                yield json.dumps(
                    {
                        "message": {"content": chunk},
                        "done": index == len(chunks) - 1,
                    }
                )

    monkeypatch.setattr(
        "another_atom.agent.provider.httpx.stream",
        lambda *args, **kwargs: VisibleStreamResponse(),
    )
    provider = OllamaCloudProvider(model="deepseek-v4-pro")
    events: list[tuple[str, dict]] = []
    provider.begin_stage(
        timeout_seconds=60,
        event_handler=lambda event_type, payload: events.append((event_type, payload)),
    )

    result = provider.create_blueprint("构建翻译工具", Mode.TEAM)

    assert result == blueprint
    assert [kind for kind, _ in events].count("agent.message.started") == 1
    assert [kind for kind, _ in events].count("agent.message.completed") == 1
    assert "".join(
        payload["delta"]
        for kind, payload in events
        if kind == "agent.message.delta"
    ) == visible
    assert "".join(
        payload["delta"]
        for kind, payload in events
        if kind == "agent.output.delta"
    ) == encoded
    assert len(
        [payload for kind, payload in events if kind == "agent.output.delta"]
    ) <= len(encoded) // 2_048 + 2
    provider.end_stage()
    get_settings.cache_clear()


def test_engineer_stream_continues_through_deepseek_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    get_settings.cache_clear()
    mock = MockLLMProvider()
    prompt = "Build a translation tool"
    blueprint = mock.create_blueprint(prompt, Mode.TEAM)
    architecture = mock.create_architecture_spec(blueprint)
    expected = mock.create_app_spec(blueprint, architecture, prompt)
    encoded = expected.model_dump_json()
    midpoint = len(encoded) // 2
    calls: list[tuple[str, dict]] = []

    class TimeoutStreamResponse:
        def __enter__(self):
            raise httpx.ReadTimeout("primary timed out")

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    class DeepSeekStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": encoded[:midpoint]}}]}
            )
            yield "data: " + json.dumps(
                {
                    "choices": [{"delta": {"content": encoded[midpoint:]}}],
                    "usage": {"prompt_tokens": 130, "completion_tokens": 90},
                }
            )
            yield "data: [DONE]"

    def fake_stream(method, url, *args, **kwargs):
        calls.append((url, kwargs.get("json", {})))
        if "ollama.com" in url:
            return TimeoutStreamResponse()
        return DeepSeekStreamResponse()

    monkeypatch.setattr("another_atom.agent.provider.httpx.stream", fake_stream)
    provider = OllamaCloudProvider(model="deepseek-v4-pro")
    events: list[str] = []
    provider.begin_stage(
        timeout_seconds=60,
        event_handler=lambda event_type, payload: events.append(event_type),
    )

    result = provider.create_app_spec(blueprint, architecture, prompt)
    usage = provider.take_usage()

    assert result == expected
    assert [url for url, _ in calls] == [
        "https://ollama.com/api/chat",
        "https://api.deepseek.com/chat/completions",
    ]
    assert calls[1][1]["stream"] is True
    assert calls[1][1]["stream_options"] == {"include_usage": True}
    assert events.index("provider.timeout") < events.index("provider.fallback.started")
    assert events.index("provider.fallback.started") < events.index("provider.first_token")
    assert usage.request_count == 2
    assert usage.fallback_provider == "deepseek"
    assert usage.input_tokens == 130
    assert usage.output_tokens == 90
    provider.end_stage()
    get_settings.cache_clear()


def test_stage_deadline_stops_before_starting_a_provider_request(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    provider = OllamaCloudProvider(model="deepseek-v4-pro")
    events: list[str] = []
    provider.begin_stage(
        timeout_seconds=0,
        event_handler=lambda event_type, payload: events.append(event_type),
    )

    with pytest.raises(LLMProviderError, match="deadline"):
        provider.route_message("给我一个网页版扫雷")

    assert provider.take_usage().request_count == 0
    assert events == ["provider.deadline.exceeded"]
    provider.end_stage()
    get_settings.cache_clear()


def test_provider_outputs_complete_renderer_contract(provider: MockLLMProvider) -> None:
    prompt = "Build a product catalog called Mono Market"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)
    assert {page.route for page in app_spec.pages} >= {"/", "/catalog"}
    assert any(page.route.startswith("/product/") for page in app_spec.pages)
    assert len(app_spec.products) >= 3
    assert provider.take_usage().request_count == 3


def test_data_analyst_and_reviewer_have_distinct_contracts(
    provider: MockLLMProvider,
) -> None:
    prompt = "Build a product catalog called Mono Market"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)
    data_profile = provider.analyze_data(blueprint, architecture, app_spec, prompt)
    validation_report = validate_app_spec(
        app_spec,
        prompt,
        blueprint=blueprint,
        architecture_spec=architecture,
    )
    review_report = provider.review(
        blueprint,
        architecture,
        app_spec,
        data_profile,
        validation_report,
        prompt,
    )

    assert data_profile.sources == ["AppSpec.products"]
    assert data_profile.entities
    assert all(
        check.status in {"pass", "warning", "not_applicable"} for check in data_profile.checks
    )
    assert review_report.verdict == "accept"
    assert review_report.issues == []
    assert review_report.engineering_checks


def test_engineer_repair_uses_validation_evidence_and_preserves_scope(
    provider: MockLLMProvider,
) -> None:
    prompt = "Build a product catalog [repair:needed]"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)
    validation_report = validate_app_spec(
        app_spec,
        prompt,
        blueprint=blueprint,
        architecture_spec=architecture,
    )

    assert validation_report.passed is False
    current_output = EngineerOutput(
        app_spec=app_spec,
        unit_tests=[
            SourceFileDraft(
                path="tests/app.test.js",
                role="test",
                content="import test from 'node:test';\n",
            )
        ],
    )
    repaired = provider.repair_engineer_output(
        blueprint,
        architecture,
        current_output,
        validation_report,
        prompt,
    )
    repaired_report = validate_app_spec(
        repaired.app_spec,
        prompt,
        blueprint=blueprint,
        architecture_spec=architecture,
    )

    assert repaired.app_spec.pages[0].route == "/"
    assert repaired.app_spec.html == app_spec.html
    assert repaired.app_spec.javascript == app_spec.javascript
    assert repaired.unit_tests == current_output.unit_tests
    assert repaired_report.passed is True


def test_minesweeper_preserves_the_game_goal_and_generates_web_source(
    provider: MockLLMProvider,
) -> None:
    prompt = "给我一个网页版扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)

    assert blueprint.support_level == SupportLevel.SUPPORTED
    assert blueprint.product_type == "web_game"
    assert blueprint.pages == ["游戏主界面"]
    assert "minefield" in app_spec.html
    assert "function reveal" in app_spec.javascript
    assert app_spec.products == []


def test_extract_json_handles_reasoning_and_prose() -> None:
    from another_atom.agent.provider import OllamaCloudProvider

    extract = OllamaCloudProvider._extract_json
    # Reasoning text with braces before the real object.
    assert extract('think {x} then\n{"a": 1}') == '{"a": 1}'
    # Trailing prose and a stray closing brace after the object.
    assert extract('{"a": 1} note: use } later') == '{"a": 1}'
    # Fenced markdown block.
    assert extract('```json\n{"a": 1}\n```') == '{"a": 1}'
    # Braces inside string literals must not end the object early.
    assert extract('{"k": "has } brace"}') == '{"k": "has } brace"}'
    with pytest.raises(ValueError):
        extract("no json here")


def test_ollama_provider_requests_structured_format(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    blueprint = MockLLMProvider().create_blueprint("Build a catalog", Mode.TEAM)
    captured: dict = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({
                "message": {"content": blueprint.model_dump_json()},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 5,
            })

    def fake_stream(*args, **kwargs):
        captured.update(kwargs.get("json", {}))
        return Response()

    monkeypatch.setattr("another_atom.agent.provider.httpx.stream", fake_stream)
    OllamaCloudProvider(model="deepseek-v4-pro").create_blueprint("Build a catalog", Mode.TEAM)
    # Real reliability fix: the request must constrain output to the JSON schema.
    assert isinstance(captured.get("format"), dict)
    assert captured["format"].get("type") == "object"
    assert captured["format"].get("required") == ["message", "result"]
    assert captured["stream"] is True
    get_settings.cache_clear()


def test_ollama_provider_records_response_token_usage(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
    get_settings.cache_clear()
    blueprint = MockLLMProvider().create_blueprint("Build a catalog", Mode.TEAM)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({
                "message": {"content": blueprint.model_dump_json()},
                "done": True,
                "prompt_eval_count": 120,
                "eval_count": 80,
            })

    monkeypatch.setattr(
        "another_atom.agent.provider.httpx.stream",
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
