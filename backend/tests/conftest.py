import pytest

_VARIABLES_LLM = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY",
    "HIPPO_LLM_PROVIDER", "HIPPO_MODEL", "HIPPO_EFFORT", "HIPPO_LLM_BASE_URL", "HIPPO_LLM_API_KEY",
)


@pytest.fixture(autouse=True)
def _sans_configuration_locale(monkeypatch):
    """Les tests ne dépendent jamais du backend/.env du développeur."""
    for v in _VARIABLES_LLM:
        monkeypatch.delenv(v, raising=False)
