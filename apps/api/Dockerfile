FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY apps/api /app/apps/api
RUN pip install --no-cache-dir ".[api,cad]"

ENV PYTHONPATH=/app/apps/api
EXPOSE 8000
CMD ["uvicorn", "reality_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
