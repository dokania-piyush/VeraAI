FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 VERA_DB_PATH=/app/data/vera.sqlite3
WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements-lock.txt \
    && groupadd --gid 10001 vera \
    && useradd --uid 10001 --gid vera --no-create-home vera \
    && mkdir -p /app/data && chown vera:vera /app/data
COPY vera/ ./vera/
COPY web/ ./web/
COPY scripts/__init__.py scripts/run.py ./scripts/
COPY bot.py ./
USER vera
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/v1/healthz',timeout=4)" || exit 1
CMD ["python", "-m", "scripts.run", "--host", "0.0.0.0"]
