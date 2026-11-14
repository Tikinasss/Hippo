import pytest

_VARIABLES = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY",
    "HIPPO_LLM_PROVIDER", "HIPPO_MODEL", "HIPPO_EFFORT", "HIPPO_LLM_BASE_URL", "HIPPO_LLM_API_KEY",
    "DATABASE_URL", "HIPPO_EMBED_MODEL", "HIPPO_EMBED_BASE_URL", "HIPPO_EMBED_API_KEY",
)


@pytest.fixture(autouse=True)
def _sans_configuration_locale(monkeypatch):
    """Les tests ne dépendent jamais du backend/.env du développeur : stockage en mémoire, pas d'embeddings."""
    for v in _VARIABLES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HIPPO_STORE", "memoire")
    monkeypatch.setenv("HIPPO_EMBED_PROVIDER", "aucun")
    from hippo.api import main
    from hippo.rag.recherche import moteur_recherche

    moteur_recherche.cache_clear()
    main._stockage = None
    main._assistant = None
    yield
    moteur_recherche.cache_clear()
