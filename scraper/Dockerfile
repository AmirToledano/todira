# syntax=docker/dockerfile:1
# Plain slim Python image — no browser needed anymore. yad2_client.py switched from a local
# patchright/Playwright browser (routed through a ZenRows residential proxy) to ZenRows' own
# Fetch API (a plain HTTP call, rendered on ZenRows' infrastructure) 2026-09-02, after discovering
# the proxy-gateway approach billed every sub-resource a rendered page loaded individually — see
# yad2_client.py's module docstring and PROJECT_STATE.md for the incident history. No more
# `patchright install chromium` step, no more Playwright base image.
FROM python:3.12-slim
WORKDIR /app
COPY common/dorin_common ./dorin_common
COPY scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scraper/ .
ENV PYTHONPATH=/app
CMD ["python", "-u", "main.py"]
