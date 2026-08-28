<<<<<<< HEAD
# Telegram File Downloader (MTProto / Telethon)

Sistema automatizado en Python para la detección, encolado y descarga de archivos de gran tamaño (aprox. 4 GB por archivo) desde Telegram utilizando **Telethon (MTProto)** y una cuenta de usuario real (NO Bot API).

---

## 🚀 Características Principales

* **MTProto sin límites de Bot API**: Descarga de archivos de gran tamaño (4 GB+) utilizando el protocolo nativo de Telegram.
* **Arquitectura Profesional Modular en `src/`**: Separación clara de responsabilidades (`config`, `core`, `database`, `telegram`, `downloads`, `utils`).
* **Entorno Virtual aislado**: Encapsulado en `venv` para mantener las dependencias aisladas.
* **Persistencia con SQLite**: Control de estado (`PENDIENTE`, `DESCARGANDO`, `COMPLETADO`, `ERROR`, `CANCELADO`) en `data/downloads.db`.
* **Reanudación segura (Resume)**: Soporte para archivos temporales `.part` alineados a bloques de 128 KB exigidos por MTProto.
* **Prevención de duplicados**: Restricción `UNIQUE(chat_id, message_id)` para evitar descargar dos veces el mismo archivo.
* **Verificación de espacio en disco**: Comprobación previa de espacio disponible antes de iniciar cada descarga.
* **Interfaz de Consola Dashboard**: Visualización en tiempo real de velocidad (MB/s), porcentaje, ETA y conteo de cola.
* **Detección de conjuntos divididos**: Notificación automática cuando se completa la descarga de partes divididas (`.part01.rar`, `.7z.001`, etc.).

---

## 📁 Estructura Profesional del Proyecto

```text
telegram-downloader/
│
├── main.py              # Punto de entrada principal (CLI)
├── requirements.txt     # Dependencias del proyecto
├── .env.example         # Plantilla de configuración de credenciales
├── .env                 # Variables de entorno locales
├── .gitignore           # Archivos excluidos del control de versiones
├── README.md            # Documentación del proyecto
│
├── src/                 # Código fuente organizado por responsabilidades
│   ├── __init__.py
│   │
│   ├── config/          # Configuración y variables de entorno
│   │   ├── __init__.py
│   │   └── settings.py
│   │
│   ├── core/            # Modelos centrales y estados
│   │   ├── __init__.py
│   │   └── models.py
│   │
│   ├── database/        # Persistencia de datos y SQLite
│   │   ├── __init__.py
│   │   └── database.py
│   │
│   ├── telegram/        # Integración nativa con Telethon/MTProto
│   │   ├── __init__.py
│   │   └── client.py
│   │
│   ├── downloads/       # Motor de descargas y gestor de cola
│   │   ├── __init__.py
│   │   ├── downloader.py
│   │   └── queue_manager.py
│   │
│   └── utils/           # Utilidades generales (Logger)
│       ├── __init__.py
│       └── logger.py
│
├── venv/                # Entorno virtual aislado de Python
├── data/                # Base de datos SQLite (downloads.db) y sesión Telethon
├── downloads/           # Carpeta de destino de archivos descargados físicamente
└── logs/                # Historial de logs (downloader.log)
```

---

## 🛠️ Instalación y Configuración del Entorno Virtual

### 1. Clonar o descargar el proyecto

Asegúrate de estar en el directorio raíz del proyecto:
```bash
cd c:\Users\prosa\Desktop\Codes\teelagram-downloader
```

### 2. Crear y Activar el Entorno Virtual (`venv`)

**En Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**En Windows (CMD):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**En Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar Dependencias

Con el entorno virtual activado:
```bash
pip install -r requirements.txt
```

---

## 🔑 Configuración de Credenciales (`.env`)

Copia el archivo de plantilla `.env.example` a `.env`:
```bash
cp .env.example .env
```

Edita `.env` con tus datos de Telegram:
```env
# Obtén tu API_ID y API_HASH en https://my.telegram.org
API_ID=12345678
API_HASH=tu_api_hash_aqui
PHONE_NUMBER=+573001234567

# ID del chat de Telegram a vigilar (los supergrupos/canales suelen iniciar con -100)
CHAT_ID=-1001234567890

# Rutas de almacenamiento
DOWNLOAD_DIR=./downloads
DATA_DIR=./data
LOG_DIR=./logs

# Configuración de cola y disco
MAX_CONCURRENT_DOWNLOADS=1
MIN_DISK_SPACE_GB=5.0
```

---

## 💻 Uso de la Aplicación

Todos los comandos se ejecutan a través de `main.py` utilizando el entorno virtual:

### 1. Autenticación Inicial
```bash
python main.py auth
```

### 2. Listar Chats (para obtener el `CHAT_ID`)
```bash
python main.py list-chats
```

### 3. Escanear Archivos Existentes
```bash
python main.py scan
```

### 4. Iniciar el Servicio de Descargas
```bash
python main.py start
```

### 5. Consultar Estado de la Cola
```bash
python main.py status
```
=======
# teelagram-downloader
>>>>>>> 2a7b5457749d289a74d4c5ae0a88699248ea11a3
