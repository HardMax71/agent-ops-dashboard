FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install uv && uv pip install --system -e .
CMD ["uvicorn", "investigator.app:app", "--host", "0.0.0.0", "--port", "8001"]
