# syntax=docker/dockerfile:1
# Playwright's own image ships all system-level deps a Chromium browser needs pre-installed
# (fonts, libgtk, libnss, etc.) for the exact playwright version in the tag — needed since plain
# httpx requests to Yad2 are blocked by bot protection (see scraper/YAD2_NOTES.md). We use
# patchright (see requirements.txt), not the vanilla playwright package this base image ships —
# patchright needs its OWN patched Chromium build, fetched below via `patchright install`; the
# base image's OS-level deps are still what that patched Chromium runs on top of.
# Verify this tag still exists on mcr.microsoft.com before relying on it long-term — Microsoft
# periodically retires old playwright image tags.
FROM mcr.microsoft.com/playwright/python:v1.47.0-noble
WORKDIR /app
COPY common/dorin_common ./dorin_common
COPY scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && patchright install chromium
COPY scraper/ .
ENV PYTHONPATH=/app
CMD ["python", "-u", "main.py"]
