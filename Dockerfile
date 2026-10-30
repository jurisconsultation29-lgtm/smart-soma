FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY agent_cards ./agent_cards
RUN useradd -m appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health'%os.environ.get('PORT','8001'))" || exit 1
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
