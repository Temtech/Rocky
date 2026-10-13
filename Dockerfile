FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=build_ca,target=/tmp/build-ca.pem \
    if [ -f /tmp/build-ca.pem ]; then PIP_CERT=/tmp/build-ca.pem pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY . .
RUN useradd --create-home --uid 10001 rocky && chown -R rocky:rocky /app
USER rocky
EXPOSE 8000
CMD ["gunicorn", "rocky.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "--access-logfile", "/dev/null"]
