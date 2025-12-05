# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies (no cache to reduce size)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application file
COPY main.py .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/vehicles').read()" || exit 1

# Start the application
CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "8000"]
