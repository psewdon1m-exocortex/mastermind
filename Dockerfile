FROM python:3.12-slim-trixie@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin mastermind
COPY src /app/src
COPY bridge/dist /app/bridge
COPY --chmod=0555 bin/mastermind /usr/local/bin/mastermind
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT ["python", "-m", "uvicorn", "mastermind.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "18390", "--no-access-log"]
