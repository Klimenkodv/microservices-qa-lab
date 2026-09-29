FROM python:3.12.7-slim
RUN pip install --no-cache-dir sqlite-web==0.6.4
RUN useradd --create-home appuser
USER appuser
EXPOSE 8080
