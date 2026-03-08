# Use official Python image with Playwright pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Ensure logs are shown immediately
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium only to save space
RUN playwright install chromium

# Copy the bot code
COPY link_bypass_bot.py .

# Run the bot
CMD ["python3", "-u", "link_bypass_bot.py"]

