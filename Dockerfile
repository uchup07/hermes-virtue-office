FROM python:3.11-slim
ARG OFFICE_UID=1000
ARG OFFICE_GID=1000
RUN if ! getent group "$OFFICE_GID" >/dev/null; then groupadd --gid "$OFFICE_GID" office; fi \
    && useradd --non-unique --uid "$OFFICE_UID" --gid "$OFFICE_GID" --create-home office
WORKDIR /app
COPY __init__.py serve.py ./
COPY web ./web
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER ${OFFICE_UID}:${OFFICE_GID}
EXPOSE 8114
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8114/health', timeout=3).close()"
CMD ["python3", "serve.py", "--host", "0.0.0.0", "--port", "8114", "--data-dir", "/data"]
