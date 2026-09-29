FROM python:3.12.7-slim
WORKDIR /app
COPY services/notification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/notification-service/app /app/app
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8001
CMD ["python", "-m", "app.run"]
