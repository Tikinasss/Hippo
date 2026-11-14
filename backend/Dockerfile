# API Hippo (FastAPI). Le corpus est monté dans /app/corpus (licences : il n'est pas copié dans l'image).
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HIPPO_CORPUS_DIR=/app/corpus
WORKDIR /app/backend
COPY pyproject.toml ./
COPY hippo ./hippo
RUN pip install -e . && useradd --create-home hippo && mkdir -p /app/corpus && chown -R hippo /app
USER hippo
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=300s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/sante', timeout=4)"
# prépare la base, le corpus et l'index, puis lance l'API (les vecteurs : service « vecteurs » de docker-compose)
CMD ["sh", "-c", "python -m hippo.preparer && exec uvicorn hippo.api.main:app --host 0.0.0.0 --port 8000 --workers ${HIPPO_WORKERS:-2}"]
