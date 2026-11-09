FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
EXPOSE 5002
CMD ["gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:5002", "app:create_app()"]
