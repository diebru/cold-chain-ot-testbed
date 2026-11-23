FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.3
COPY telegestione.py .
COPY templates/ templates/
EXPOSE 8080
CMD ["python", "telegestione.py"]
