# Telegram File Downloader (MTProto / Telethon) & Bot de Administración

Sistema automatizado en Python para la detección, encolado, descarga de archivos de gran tamaño (aprox. 4 GB por archivo) desde Telegram utilizando **Telethon (MTProto)** y administración remota mediante **Telegram Bot API**.

---

## 🚀 Características Principales

* **MTProto para descargas de gran tamaño (4 GB+)**: Las descargas de archivos grandes se ejecutan mediante Telethon/MTProto nativo usando una cuenta de usuario real (sin límites del Bot API).
* **Bot de Administración Remoto**: Control total del downloader vía Telegram Bot API con panel interactivo (`/start`), menú de comandos autocompletado en Telegram UI, botones inline, progreso en tiempo real y notificaciones.
* **Seguridad por Lista Blanca**: Filtro de administradores autorizados mediante `ADMIN_USER_IDS`.
* **Detección Automática & Aprobación**: Escucha mensajes en tiempo real y notifica nuevos archivos con botones inline `[ Descargar ]` / `[ Ignorar ]`. Soporta descarga automática condicional vía `AUTO_DOWNLOAD`.
* **Guía Interactiva en el Bot (`/guide`)**: Módulo interactivo dentro del chat de Telegram con navegación por pestañas (`Inicio`, `Descargas & .part`, `Comandos`, `Configuración`).
* **Barra de Progreso Gráfica & Formato HTML**: Renderizado gráfico de avance `[██████░░░░] 62.4%`, códigos monospaciados y badges de estado.
* **Arquitectura Limpia y Modular**: Separación de capas (`config`, `core`, `database`, `telegram`, `downloads`, `services`, `bot`, `utils`).
* **Persistencia Única con SQLite**: Control de estado centralizado (`PENDIENTE`, `DESCARGANDO`, `COMPLETADO`, `ERROR`, `CANCELADO`) en `data/downloads.db`.
* **Reanudación Segura (`.part`)**: Bloques de 128 KB alineados a MTProto. Permite pausar, detener e interrumpir descargas conservando el progreso parcial.
* **Verificación de Espacio en Disco**: Comprobación previa de espacio disponible antes de iniciar cada descarga.
* **Compatibilidad 100% CLI**: Se conservan intactos los comandos CLI existentes.

---

## 📁 Estructura del Proyecto

```text
telegram-downloader/
│
├── main.py              # Punto de entrada principal (CLI & Inicio de servicios)
├── requirements.txt     # Dependencias del proyecto (Telethon, python-telegram-bot, etc.)
├── .env.example         # Plantilla de configuración
├── .env                 # Variables de entorno locales
├── .gitignore           # Archivos excluidos de git
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
│   ├── database/        # Persistencia de datos, SQLite y Repositorios
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── repository.py
│   │
│   ├── telegram/        # Integración MTProto (Telethon) y listener de mensajes
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── message_handler.py
│   │
│   ├── downloads/       # Motor de descargas, gestor de cola y progreso
│   │   ├── __init__.py
│   │   ├── downloader.py
│   │   ├── queue_manager.py
│   │   └── progress.py
│   │
│   ├── services/        # Servicios compartidos de negocio (CLI y Bot)
│   │   ├── __init__.py
│   │   ├── scan_service.py
│   │   ├── download_service.py
│   │   └── status_service.py
│   │
│   ├── bot/             # Bot de Administración (Telegram Bot API)
│   │   ├── __init__.py
│   │   ├── bot.py
│   │   ├── handlers.py
│   │   ├── keyboards.py
│   │   └── notifications.py
│   │
│   └── utils/           # Utilidades generales (Logger y Filesystem)
│       ├── __init__.py
│       ├── logger.py
│       └── filesystem.py
│
├── venv/                # Entorno virtual aislado de Python
├── data/                # Base de datos SQLite (downloads.db) y sesión Telethon
├── downloads/           # Carpeta de destino de archivos descargados físicamente
└── logs/                # Historial de logs (downloader.log)
```

---

## 🛠️ Instalación y Configuración

### 1. Activar el Entorno Virtual (`venv`) e Instalar Dependencias

**En Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**En Linux / macOS:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🔑 Variables de Entorno (`.env`)

Configura tus datos en `.env`:
```env
# Telethon (MTProto - Cuenta de usuario real)
API_ID=12345678
API_HASH=tu_api_hash_aqui
PHONE_NUMBER=+573001234567
CHAT_ID=-1001234567890

# Bot de Administración (Telegram Bot API)
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_USER_IDS=123456789,987654321

# Descarga automática y frecuencia de actualización
AUTO_DOWNLOAD=false
BOT_PROGRESS_UPDATE_INTERVAL=10

# Directorios
DOWNLOAD_DIR=./downloads
DATA_DIR=./data
LOG_DIR=./logs

# Cola y disco
MAX_CONCURRENT_DOWNLOADS=1
MIN_DISK_SPACE_GB=5.0
```

---

## 📖 Guía de Uso Completa

### 1. Requisitos Previos
1. **Credenciales de Telethon**: Obtén tu `API_ID` y `API_HASH` en [my.telegram.org](https://my.telegram.org).
2. **Bot Token**: Crea un bot con [@BotFather](https://t.me/BotFather) y copia el `BOT_TOKEN`.
3. **Admin User ID**: Obtén tu ID numérico de Telegram usando [@userinfobot](https://t.me/userinfobot) y colócalo en `ADMIN_USER_IDS`.

### 2. Flujo de Inicio Rápido
1. **Autenticación Telethon**:
   ```bash
   python main.py auth
   ```
2. **Obtener CHAT_ID del canal o grupo**:
   ```bash
   python main.py list-chats
   ```
3. **Escaneo de archivos del chat**:
   ```bash
   python main.py scan
   ```
4. **Iniciar todo el sistema (Telethon + Queue + Bot)**:
   ```bash
   python main.py start
   ```

---

## 💻 Comandos CLI

Todos los comandos CLI continúan funcionando exactamente igual:

```bash
python main.py auth         # Autenticación interactiva con Telethon
python main.py list-chats   # Lista los chats recientes para identificar CHAT_ID
python main.py scan         # Escanea el chat configurado y registra archivos en SQLite
python main.py start        # Inicia Telethon, la cola de descargas y el Bot de Administración
python main.py status       # Muestra estadísticas y últimos registros en consola
```

---

## 🤖 Bot de Administración de Telegram

Cuando ejecutas `python main.py start`, el Bot de Administración se conecta de forma paralela en el mismo proceso.

### Comandos del Bot:
* `/start` — Panel interactivo de administración y resumen de estado.
* `/status` — Estado del sistema y barra de progreso gráfica de la descarga activa.
* `/scan` — Ejecuta el escaneo del chat en tiempo real.
* `/files` — Explorador de archivos paginados con filtros (`Todos`, `Pendientes`, `Descargando`, `Completados`, `Errores`).
* `/queue` — Muestra los archivos pendientes en la cola.
* `/downloads` — Muestra la descarga activa actual.
* `/start_downloads` — Inicia o reanuda el procesamiento de la cola de descargas.
* `/stop_downloads` — Pausa la cola para que no se inicien nuevos archivos.
* `/cancel` — Solicita confirmación y cancela la descarga activa conservando el archivo `.part`.
* `/guide` — Guía de uso interactiva por pestañas dentro del chat.
* `/help` — Menú de ayuda rápida.

---

## 💾 Descargas Grandes & Archivos `.part`

- **Archivos de 4 GB+**: Se descargan exclusivamente por el protocolo MTProto nativo mediante Telethon.
- **Reanudación Segura**: Si el proceso se detiene o se envía `/cancel`, el archivo parcial `nombre.rar.part` se **conserva**. Al reanudar, se continuará automáticamente desde el último byte descargado.
- **Verificación de Disco**: Comprobación previa de espacio con `shutil.disk_usage`. Si no hay suficiente espacio, la descarga no iniciará y avisará al administrador.

---

## 🛡️ Seguridad

El bot rechaza automáticamente cualquier comando de usuarios cuyos Telegram IDs no estén incluidos en `ADMIN_USER_IDS` respondiendo:
> *No tienes autorización para utilizar este bot.*
