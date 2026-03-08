FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install uv && uv pip install --system -e .
RUN groupadd --system appuser && useradd --system --gid appuser appuser \
    && chown -R appuser:appuser /app
USER appuser
CMD ["uvicorn", "codebase_search.app:app", "--host", "0.0.0.0", "--port", "8002"]
