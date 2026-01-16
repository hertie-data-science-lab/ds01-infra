FROM python:3.11-slim

WORKDIR /app

# Install minimal dependencies
RUN pip install --no-cache-dir PyYAML

# Copy exporter
COPY ds01_exporter.py /app/

# Run as non-root (but needs docker socket access via group)
RUN groupadd -g 999 docker && \
    useradd -r -u 1000 -g docker exporter

USER exporter

EXPOSE 9101

ENTRYPOINT ["python3", "/app/ds01_exporter.py"]
