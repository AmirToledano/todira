# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY common/dorin_common ./dorin_common
COPY migrations ./migrations
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot/ .
ENV PYTHONPATH=/app
CMD ["python", "main.py"]
