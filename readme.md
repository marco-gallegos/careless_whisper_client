# Careless whisper

is a project to automate and enhace my workflows as dev using AI.

## OBS Controller CLI

Un script CLI en Python para controlar OBS Studio via WebSocket.

### Características

- 🎬 Control de grabación en OBS (iniciar/detener)
- 📡 Escucha de eventos en tiempo real
- 📊 Consulta del estado actual de OBS
- 🔐 Configuración segura mediante archivo .env
- 🎯 CLI intuitiva con argumentos claros

### Requisitos Previos

1. **OBS Studio** debe estar ejecutándose
2. **Habilitar WebSocket en OBS**: 
   - Ve a `Tools` → `WebSocket Server Settings`
   - Marca "Enable WebSocket server"
   - Configura un puerto (default: 4455) y contraseña opcional
3. **Instalar dependencias Python**:
   ```shell
   pip install -r requirements.txt
   ```

### Configuración Inicial

```shell
# 1. Copia el archivo de ejemplo
cp .env.example .env

# 2. Edita .env con tus credenciales de OBS
# OBS_HOST=localhost
# OBS_PORT=4455
# OBS_PASSWORD=tu_contraseña
```

### Uso

```shell
# Iniciar grabación en OBS
python obs_controller.py --action start-recording

# Detener grabación en OBS
python obs_controller.py --action stop-recording

# Ver estado actual de OBS (versión, estado de grabación, etc.)
python obs_controller.py --action status

# Escuchar todos los eventos de OBS en tiempo real
# (mantiene el script ejecutándose, presiona Ctrl+C para detener)
python obs_controller.py --action listen-events

# Override de configuración desde CLI (no usa .env)
python obs_controller.py --action status --host localhost --port 4455 --password mipass
```

### Eventos que Escucha

Cuando usas `--action listen-events`, el script captura y muestra:

- 🔴 **Eventos de Grabación**: inicio, detención, pausa, reanudación
- 📺 **Eventos de Streaming**: inicio, detención
- 🎭 **Cambios de Escena**: transiciones entre escenas
- 🎚️ **Cambios de Sources**: habilitación/deshabilitación de elementos
- 📊 **Métricas de Audio**: niveles de volumen (VU meters)
- 🚪 **Eventos de Sistema**: cierre de OBS

Cada evento se muestra con:
- Timestamp
- Tipo de evento
- Datos asociados al evento

## Audio Recorder CLI

Un script CLI en Python para grabar audio usando ffmpeg.

### Características

- 🎙️ Grabación de audio con ffmpeg
- 🔍 Lista automática de dispositivos disponibles
- ⏱️ Duración configurable o indefinida (Ctrl+C para detener)
- 🚀 Ejecuta comandos después de grabar
- 📁 Guarda grabaciones en carpeta configurable

### Uso

```shell
# Listar dispositivos disponibles
python audio_recorder.py --list-devices

# Grabar con dispositivo específico
python audio_recorder.py --device 0

# Grabar 10 segundos
python audio_recorder.py --device 0 --duration 10

# Grabar y ejecutar comando después
python audio_recorder.py --device 0 --post-command "echo 'Listo: {file}'"

# Si no especificas dispositivo, te pedirá elegir uno
python audio_recorder.py

# Con nombre personalizado y directorio específico
python audio_recorder.py --device 0 --output mi_audio.wav --output-dir ~/grabaciones
```

### Variables en post-command

- `{file}` - Ruta completa del archivo
- `{filename}` - Solo el nombre del archivo
- `{filepath}` - Ruta absoluta del archivo

## Dependencies

### Python Packages

```shell
pip install -r requirements.txt
```

Incluye:
- `obs-websocket-py` - Cliente WebSocket para OBS Studio
- `python-dotenv` - Carga variables de entorno desde .env

### Mac

fswatch to check dfs changes

```shell
brew install fswatch
brew install ffmpeg

# copy 

launchctl load ~/Library/LaunchAgents/com.tudominio.folderwatcher.plist

```


### Linux

### Windows

not supported because sucks :)
