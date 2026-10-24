# AURA AI web app — production container
FROM python:3.12-slim

# Keep Python output unbuffered and skip .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    AWS_REGION=us-east-1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application.
COPY app.py pipeline.py catalog.py metrics.py engine.py extractor.py geo.py hazards.py routing.py mapdata.py urgency.py bedrock_client.py ./
COPY static ./static

EXPOSE 8000

# Run with gunicorn (production WSGI server). Threads let a single worker
# handle concurrent Bedrock calls without blocking.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
