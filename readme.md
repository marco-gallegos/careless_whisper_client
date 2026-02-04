# Careless whisper


is a project to automate and enhace my workflows as dev using AI.

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
