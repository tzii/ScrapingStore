# Match the Python package version in pyproject.toml so browser binaries
# and the Playwright client stay compatible.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY pyproject.toml README.md LICENSE CHANGELOG.md MANIFEST.in ./
COPY scrapingstore ./scrapingstore

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin scraper \
    && mkdir -p /app/data /app/docs \
    && chown -R scraper:scraper /app

USER scraper

ENV PYTHONUNBUFFERED=1
ENV SCRAPINGSTORE_HOME=/app

ENTRYPOINT ["scrapingstore"]
CMD ["scrape"]
