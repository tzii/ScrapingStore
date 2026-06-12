# Match the Python package version in requirements.txt so browser binaries
# and the Playwright client stay compatible.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entrypoint to run the scraper by default
ENTRYPOINT ["python", "main.py"]
CMD ["scrape"]
