FROM python:3.12-slim
WORKDIR /app
COPY common/dorin_common ./dorin_common
COPY website/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY website/ .
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
