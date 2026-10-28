FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 STORE_PATH=/data/users.json
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY evilmarkhorsx_bot.py bot.py
VOLUME ["/data"]
CMD ["python", "bot.py"]
