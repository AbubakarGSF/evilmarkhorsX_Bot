FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORE_PATH=/app/users.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY evilmarkhorsx_bot.py bot.py

# Proxy list container mein na ho to bot direct (proxy OFF) chalta hai.
# Isliye kro_proxies.txt copy nahi kar rahe - direct X connection use karega.
# Agar chahen to Railway ya local .env mein PROXY_FILE set karke phir se proxy ON kar saktein.

CMD ["python", "bot.py"]
