FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_DEFAULT_TIMEOUT=120
RUN pip install \
    --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --default-timeout "${PIP_DEFAULT_TIMEOUT}" \
    -r requirements.txt

COPY app ./app
RUN mkdir -p /data

ENV JIALUTONG_DATA_DIR=/data
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
