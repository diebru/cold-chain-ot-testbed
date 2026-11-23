FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends nmap \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /attacks
# Il container resta acceso e gli attacchi si lanciano con "docker compose exec"
CMD ["sleep", "infinity"]
