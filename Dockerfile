FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
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
