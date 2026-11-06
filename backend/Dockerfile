FROM python:3.12-slim
COPY . /src
RUN mkdir -p /app && (test -d /src/backend && cp -a /src/backend/. /app/ || cp -a /src/. /app/)
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
