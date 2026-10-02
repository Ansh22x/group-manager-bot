# Giyu-Bot with Hermes Agent baked in (NousResearch/hermes-agent)
# Base moved to 3.11 to satisfy Hermes' Python requirement.
FROM python:3.11-slim

# System deps: ffmpeg for media, git for Hermes install, build tools for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libpq-dev \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---- Install Hermes Agent into its own venv --------------------------------
# Hermes requires Python 3.11 (matching the base image) and is installed via
# its official install script into /opt/hermes, exposed on PATH so the bot's
# `hermes` bridge subprocess works out of the box.
ENV HERMES_HOME=/opt/hermes-home \
    PATH="/opt/hermes/bin:${PATH}"
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --prefix /opt/hermes \
    || (git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /tmp/hermes-agent \
        && python -m venv /opt/hermes \
        && /opt/hermes/bin/pip install --no-cache-dir -e /tmp/hermes-agent \
        && ln -s /opt/hermes/bin/hermes /usr/local/bin/hermes \
        && rm -rf /tmp/hermes-agent)

# Pre-create Hermes home so first boot doesn't run interactive setup
RUN mkdir -p /opt/hermes-home

# ---- Bot dependencies ------------------------------------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["python", "main.py"]
