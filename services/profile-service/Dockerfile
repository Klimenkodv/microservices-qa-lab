FROM python:3.12.7-slim
WORKDIR /app
COPY services/profile-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/profile-service/app /app/app
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8003 50051
CMD ["python", "-m", "app.run"]
