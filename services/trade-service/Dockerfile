FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ .
EXPOSE 5002
HEALTHCHECK CMD curl -f http://localhost:5002/health || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers","2", "app:app"]