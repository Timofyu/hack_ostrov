FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV BROWSER_PATH=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
