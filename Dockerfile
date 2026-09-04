FROM python:3.12-slim

# Evitar archivos .pyc y bufferizar logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY main.py .
COPY src ./src

# Crear directorios persistentes
RUN mkdir -p /app/data /app/downloads /app/logs

# Ejecutar aplicación
CMD ["python", "main.py"]