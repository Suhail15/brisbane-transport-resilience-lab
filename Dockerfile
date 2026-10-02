FROM python:3.11.14-slim
WORKDIR /app
COPY requirements.lock.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY services services
COPY configs configs
ENV PYTHONPATH=/app/services
CMD ["uvicorn", "resilience.api:app", "--host", "0.0.0.0", "--port", "8000"]
