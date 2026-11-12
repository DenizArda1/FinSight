# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Native dependencies are compiled only in this stage, if wheels are unavailable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install -r requirements.txt \
    && /opt/venv/bin/python -m pip check


FROM python:3.13-slim-bookworm AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" finsight \
    && useradd --uid "${APP_UID}" --gid finsight --create-home finsight \
    && mkdir -p /app/configs /app/financial_data /app/logs \
    && chown -R finsight:finsight /app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
COPY configs /opt/finsight/configs
COPY docker/entrypoint.py /opt/finsight/entrypoint.py

USER finsight
EXPOSE 8766
STOPSIGNAL SIGINT

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/', timeout=3).close()"

ENTRYPOINT ["python", "/opt/finsight/entrypoint.py"]
CMD ["python", "-m", "src.web", "--host", "0.0.0.0", "--port", "8766"]
