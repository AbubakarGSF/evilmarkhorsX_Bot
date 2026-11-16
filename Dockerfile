FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORE_PATH=/app/users.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY evilmarkhorsx_bot.py bot.py

# Proxy list ko image ke andar rakho (/app/kro_proxies.txt). Iske baghair
# PROXY_FILE=kro_proxies.txt container mein kabhi nahi milta aur bot direct
# (proxy OFF) chalta hai.
COPY kro_proxies.txt /app/kro_proxies.txt

CMD ["python", "bot.py"]
