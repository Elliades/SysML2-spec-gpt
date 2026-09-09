FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY viewer ./viewer

RUN pip install --no-cache-dir .

ENV SYSML_SPEC_ROOT=/app
ENV SYSML_SPEC_DATA=/data
ENV SYSML_VIEWER_HOST=0.0.0.0
ENV SYSML_VIEWER_PORT=3112
ENV PYTHONUNBUFFERED=1

EXPOSE 3112

HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3112/api/health', timeout=6)" || exit 1

CMD ["python", "-m", "sysml_spec_qa", "serve"]
