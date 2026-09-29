FROM python:3.12.7-slim
WORKDIR /app
COPY services/statistics-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/statistics-service/app /app/app
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8002
CMD ["python", "-m", "app.run"]
