FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY supervisore.py .
COPY templates/ templates/
# Versione vulnerabile: il processo gira come root, come molti firmware embedded
EXPOSE 80 502
CMD ["python", "supervisore.py"]
