FROM python:3.11-slim

WORKDIR /app

# Dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run configuration check at startup, then launch uvicorn
CMD ["sh", "-c", "python -m app.core.config_check && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
