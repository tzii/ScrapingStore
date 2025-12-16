# Use official Playwright image to ensure browsers are installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entrypoint to run the scraper by default
ENTRYPOINT ["python", "main.py"]
CMD ["scrape"]
