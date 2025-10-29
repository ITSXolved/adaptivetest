FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code to /app directory (this puts main.py directly in /app/)
COPY app/ ./

# Add current directory to Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 5300

# Command to run the application - main.py contains the Flask app variable 'app'
CMD ["gunicorn", "--bind", "0.0.0.0:5300", "--workers", "1", "--reload", "main:app"]
