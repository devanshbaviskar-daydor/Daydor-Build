# One image for the API and the queue worker (they differ only by command). Build from the repository root:
#   docker build -t daydor .
# The backend is installed in editable mode on purpose: its registry/, model/ and migrations/ folders are read from the source tree.
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY daydor-backend /app/daydor-backend
COPY daydor-frontend/api /app/daydor-frontend/api
RUN pip install -e "/app/daydor-backend[claude]" -e /app/daydor-frontend/api \
 && useradd --system --uid 10001 daydor && chown -R daydor /app
USER daydor
ENV DAYDOR_API_ENV=production
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "daydor_api.app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
