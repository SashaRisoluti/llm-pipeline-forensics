FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY pipeline ./pipeline
COPY tracing ./tracing
COPY forensics ./forensics
COPY evals ./evals
COPY api ./api
COPY scripts ./scripts
RUN pip install --no-cache-dir .
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "api.app:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
