FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY schemas ./schemas
COPY static ./static
COPY server.py diagnose_qwen.py report_inputs.py specify_run.py check_specification.py ./
RUN useradd --create-home pipeline && mkdir /app/runs && chown pipeline:pipeline /app/runs
USER pipeline
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=2)" || exit 1
CMD ["python", "server.py", "--host", "0.0.0.0"]
