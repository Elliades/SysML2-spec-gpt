FROM python:3.12-slim

WORKDIR /app

# PyMuPDF wheels are self-contained; ca-certificates is for first-boot OMG downloads.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY viewer ./viewer

# Corporate proxy (Compose passes HTTP_PROXY / HTTPS_PROXY as build args).
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

RUN pip install --no-cache-dir .

ENV SYSML_SPEC_ROOT=/app
ENV SYSML_SPEC_DATA=/data
ENV SYSML_VIEWER_HOST=0.0.0.0
ENV SYSML_VIEWER_PORT=3112
ENV PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 3112

# First `boot` downloads OMG PDFs and builds the index (several minutes).
HEALTHCHECK --interval=30s --timeout=8s --start-period=900s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3112/api/health', timeout=6)" || exit 1

CMD ["python", "-m", "sysml_spec_qa", "boot"]
