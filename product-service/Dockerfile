FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
EXPOSE 5001
CMD ["gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:5001", "app:create_app()"]
