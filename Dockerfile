# ---------- Stage 1: build wheels ----------
FROM python:3.11-slim AS builder

ARG DEBIAN_FRONTEND=noninteractive

# install packages required to build wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc python3-dev libssl-dev libffi-dev git curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

# copy requirements and build wheels into /wheels
COPY requirements.txt .
# upgrade pip/setuptools/wheel then build wheels
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip wheel --wheel-dir /wheels -r requirements.txt

# ---------- Stage 2: runtime image ----------
FROM python:3.11-slim

ARG APP_USER=appuser
ARG APP_DIR=/app

ENV PYTHONUNBUFFERED=1 \
    PATH="/home/${APP_USER}/.local/bin:${PATH}"

# install minimal runtime packages (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

# create non-root user (optional but recommended)
RUN useradd --create-home --shell /bin/bash ${APP_USER}

WORKDIR ${APP_DIR}

# copy prebuilt wheels from builder and install
COPY --from=builder /wheels /wheels
# install from wheels (faster, no dev tools required)
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install --no-index --find-links /wheels -r /wheels/requirements.txt \
 && rm -rf /wheels

# copy app source
COPY . .

# ensure files are owned by non-root user
RUN chown -R ${APP_USER}:${APP_USER} ${APP_DIR}

USER ${APP_USER}

EXPOSE 5000

# Healthcheck hits your get_data endpoint; adjust URL if needed
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/get_data || exit 1

# Run Gunicorn with a single worker so simulator (started on import) runs only once.
# --access-logfile - and --error-logfile - push logs to stdout/stderr for Docker logging.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-", "app3:app"]
