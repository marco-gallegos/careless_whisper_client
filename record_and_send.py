#!/usr/bin/env python3
"""
OBS Record and Send - Start recording via OBS WebSocket, wait until stopped,
capture the output file path, and optionally send it to an external API.
"""

import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

try:
    import pyperclip
except ImportError:
    print("❌ Error: pyperclip no está instalado")
    print("   Instala las dependencias con: uv sync")
    sys.exit(1)

try:
    import click
except ImportError:
    print("❌ Error: click no está instalado")
    print("   Instala las dependencias con: uv sync")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ Error: requests no está instalado")
    print("   Instala las dependencias con: uv sync")
    sys.exit(1)

try:
    from obswebsocket import obsws, requests as obs_requests, events as obs_events
except ImportError:
    print("❌ Error: obs-websocket-py no está instalado")
    print("   Instala las dependencias con: uv sync")
    sys.exit(1)


OBS_OUTPUT_STOPPED = "OBS_WEBSOCKET_OUTPUT_STOPPED"
DEFAULT_TIMEOUT_SECONDS = 1 * 60 * 60  # 1 hour
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "transcriptions.db"


def get_db_connection(db_path=None):
    """Get a connection to the SQLite database."""
    db_path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path=None):
    """Initialize the SQLite database with required tables."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription TEXT NOT NULL,
            language TEXT,
            processing_time REAL,
            model_used TEXT,
            source_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY (transcription_id) REFERENCES transcriptions (id)
        )
    """)
    
    conn.commit()
    conn.close()


def store_transcription(response_data, source_file=None, db_path=None):
    """
    Store transcription and segments in the database.
    Returns the transcription ID.
    """
    init_database(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO transcriptions (transcription, language, processing_time, model_used, source_file)
        VALUES (?, ?, ?, ?, ?)
    """, (
        response_data.get("transcription", ""),
        response_data.get("language"),
        response_data.get("processing_time"),
        response_data.get("model_used"),
        str(source_file) if source_file else None
    ))
    
    transcription_id = cursor.lastrowid
    
    segments = response_data.get("segments", [])
    for segment in segments:
        cursor.execute("""
            INSERT INTO segments (transcription_id, segment_id, start_time, end_time, text)
            VALUES (?, ?, ?, ?, ?)
        """, (
            transcription_id,
            segment.get("id", 0),
            segment.get("start", 0.0),
            segment.get("end", 0.0),
            segment.get("text", "")
        ))
    
    conn.commit()
    conn.close()
    return transcription_id


def copy_to_clipboard(text):
    """Copy text to system clipboard."""
    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        click.echo(f"⚠️ No se pudo copiar al portapapeles: {e}", err=True)
        return False


def _unregister_record_callback(ws, callback, event=obs_events.RecordStateChanged):
    """Unregister RecordStateChanged callback if the library supports it."""
    try:
        if hasattr(ws, "unregister"):
            ws.unregister(callback, event)
    except Exception:
        pass


def load_config():
    """Load .env from script directory."""
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_event_output_path(message):
    """Extract outputPath and outputState from RecordStateChanged event."""
    datain = getattr(message, "datain", None) or message.__dict__.get("datain", {})
    if not datain:
        return None, None
    return datain.get("outputPath"), datain.get("outputState")


class RecordAndSendController:
    """Controls OBS recording and optional API upload."""

    def __init__(self, host=None, port=None, password=None):
        load_config()
        self.host = host or os.getenv("OBS_HOST", "localhost")
        self.port = int(port or os.getenv("OBS_PORT", 4455))
        self.password = password or os.getenv("OBS_PASSWORD", "")
        self.ws = None
        self.connected = False
        self.recorded_file_path = None
        self.recording_stopped = False

    def connect(self):
        """Connect to OBS WebSocket."""
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            return True
        except ConnectionRefusedError:
            raise click.ClickException(
                f"No se pudo conectar a OBS en {self.host}:{self.port}. "
                "Asegúrate de que OBS esté abierto y el WebSocket habilitado."
            )
        except Exception as e:
            raise click.ClickException(f"Error al conectar con OBS: {e}")

    def disconnect(self):
        """Disconnect from OBS."""
        if self.ws and self.connected:
            try:
                self.ws.disconnect()
            except Exception:
                pass
            self.connected = False

    def _on_record_state_changed(self, message):
        """Callback for RecordStateChanged: capture path when recording stopped."""
        output_path, output_state = get_event_output_path(message)
        if output_state == OBS_OUTPUT_STOPPED and output_path:
            self.recorded_file_path = output_path
            self.recording_stopped = True

    def start_and_wait_for_stop(self, timeout_seconds=None, stop_from_cli=True):
        """
        Start recording, register for RecordStateChanged, and block until
        recording is stopped (user can stop from OBS or press Enter in CLI).
        Returns the output file path or None on timeout/error.
        """
        if not self.connected:
            raise click.ClickException("No hay conexión con OBS")

        timeout_seconds = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        self.recorded_file_path = None
        self.recording_stopped = False

        try:
            status = self.ws.call(obs_requests.GetRecordStatus())
            if status.getOutputActive():
                raise click.ClickException("OBS ya está grabando. Detén la grabación actual primero.")
        except Exception as e:
            raise click.ClickException(f"Error al verificar estado: {e}")

        self.ws.register(self._on_record_state_changed, obs_events.RecordStateChanged)
        try:
            self.ws.call(obs_requests.StartRecord())
        except Exception as e:
            _unregister_record_callback(self.ws, self._on_record_state_changed)
            raise click.ClickException(f"Error al iniciar grabación: {e}")

        click.echo("🔴 Grabación iniciada. Detén la grabación desde OBS cuando termines.")
        if stop_from_cli:
            click.echo("   (O presiona Enter aquí para detener desde la CLI)")
            def stop_on_enter():
                input()
                if not self.recording_stopped and self.ws and self.connected:
                    try:
                        self.ws.call(obs_requests.StopRecord())
                    except Exception:
                        pass
            stop_thread = threading.Thread(target=stop_on_enter, daemon=True)
            stop_thread.start()

        deadline = time.monotonic() + timeout_seconds
        while not self.recording_stopped and time.monotonic() < deadline:
            time.sleep(0.3)
        _unregister_record_callback(self.ws, self._on_record_state_changed)

        if not self.recording_stopped:
            click.echo("⏱️ Timeout: la grabación no se detuvo en el tiempo indicado.", err=True)
            return None
        return self.recorded_file_path

    def send_file_to_api(self, file_path, api_url=None, token=None, field_name="file"):
        """
        POST file to external API as multipart/form-data.
        Returns (success: bool, response or error message).
        """
        path = Path(file_path)
        if not path.is_file():
            return False, f"El archivo no existe: {path}"

        api_url = api_url or os.getenv("RECORD_SEND_API_URL")
        if not api_url:
            return False, "No se especificó API URL (RECORD_SEND_API_URL o --api-url)"

        token = token or os.getenv("RECORD_SEND_API_TOKEN")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params = {
            "model": "small",
        }

        try:
            with open(path, "rb") as f:
                files = {field_name: (path.name, f, "application/octet-stream")}
                resp = requests.post(api_url, files=files, headers=headers, timeout=120, params=params)
            if resp.ok:
                return True, resp
            return False, f"API respondió {resp.status_code}: {resp.text[:500]}"
        except requests.RequestException as e:
            return False, str(e)


@click.group()
@click.option("--host", envvar="OBS_HOST", default="localhost", help="OBS WebSocket host")
@click.option("--port", type=int, envvar="OBS_PORT", default=4455, help="OBS WebSocket port")
@click.option("--password", envvar="OBS_PASSWORD", default="", help="OBS WebSocket password")
@click.pass_context
def cli(ctx, host, port, password):
    """Record with OBS and optionally send the file to an API."""
    load_config()
    ctx.obj = {"host": host, "port": port, "password": password}


@cli.command("record")
@click.option(
    "--send",
    "do_send",
    is_flag=True,
    default=False,
    help="After recording, send the file to the configured API",
)
@click.option(
    "--timeout",
    type=int,
    default=None,
    metavar="SECONDS",
    help=f"Max time to wait for recording to stop (default: {DEFAULT_TIMEOUT_SECONDS})",
)
@click.option(
    "--api-url",
    type=str,
    envvar="RECORD_SEND_API_URL",
    default=None,
    help="API URL to POST the file (overrides RECORD_SEND_API_URL)",
)
@click.option(
    "--api-token",
    type=str,
    envvar="RECORD_SEND_API_TOKEN",
    default=None,
    help="Bearer token for API (overrides RECORD_SEND_API_TOKEN)",
)
@click.option(
    "--stop-from-cli/--no-stop-from-cli",
    default=True,
    help="Permitir detener la grabación desde la CLI con Enter (default: activado)",
)
@click.pass_context
def record(ctx, do_send, timeout, api_url, api_token, stop_from_cli):
    """
    Start OBS recording, wait until you stop it from OBS (or Enter en la CLI), then show the file path.
    Use --send to also POST the file to the configured API.
    """
    ctrl = RecordAndSendController(
        host=ctx.obj["host"],
        port=ctx.obj["port"],
        password=ctx.obj["password"],
    )
    click.echo(f"🔌 Conectando a OBS en {ctrl.host}:{ctrl.port}...")
    ctrl.connect()
    try:
        file_path = ctrl.start_and_wait_for_stop(
            timeout_seconds=timeout, stop_from_cli=stop_from_cli
        )
        if not file_path:
            raise click.ClickException("No se obtuvo el path del archivo grabado.")
        click.echo(f"📁 Archivo grabado: {file_path}")
        if do_send:
            ok, result = ctrl.send_file_to_api(file_path, api_url=api_url, token=api_token)
            if ok:
                click.echo("✅ Archivo enviado correctamente a la API.")
                if hasattr(result, "text") and result.text:
                    click.echo(result.text[:1000])
            else:
                raise click.ClickException(f"Error al enviar a la API: {result}")
    finally:
        ctrl.disconnect()


@cli.command("send")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the file to send",
)
@click.option(
    "--api-url",
    type=str,
    envvar="RECORD_SEND_API_URL",
    default=None,
    help="API URL to POST the file (or set RECORD_SEND_API_URL)",
)
@click.option(
    "--api-token",
    type=str,
    envvar="RECORD_SEND_API_TOKEN",
    default=None,
    help="Bearer token for API",
)
def send_file(file_path, api_url, api_token):
    """Send an existing file to the configured API."""
    load_config()
    if not api_url:
        raise click.ClickException("Indica --api-url o configura RECORD_SEND_API_URL")
    ctrl = RecordAndSendController()
    ok, result = ctrl.send_file_to_api(
        file_path, api_url=api_url, token=api_token
    )
    if ok:
        click.echo("✅ Archivo enviado correctamente.")
        if hasattr(result, "text") and result.text:
            click.echo(result.text)
    else:
        raise click.ClickException(f"Error al enviar: {result}")


@cli.command("translate")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the audio file to transcribe",
)
@click.option(
    "--api-url",
    type=str,
    envvar="RECORD_SEND_API_URL",
    default=None,
    help="API URL for transcription (or set RECORD_SEND_API_URL)",
)
@click.option(
    "--api-token",
    type=str,
    envvar="RECORD_SEND_API_TOKEN",
    default=None,
    help="Bearer token for API",
)
@click.option(
    "--copy/--no-copy",
    default=True,
    help="Copy transcription to clipboard (default: enabled)",
)
@click.option(
    "--store/--no-store",
    default=True,
    help="Store transcription in local database (default: enabled)",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to SQLite database (default: transcriptions.db in script directory)",
)
def translate(file_path, api_url, api_token, copy, store, db_path):
    """
    Transcribe an audio file via API, copy to clipboard, and store in database.
    """
    load_config()
    if not api_url:
        raise click.ClickException("Indica --api-url o configura RECORD_SEND_API_URL")
    
    ctrl = RecordAndSendController()
    click.echo(f"📤 Enviando archivo para transcripción: {file_path}")
    
    ok, result = ctrl.send_file_to_api(file_path, api_url=api_url, token=api_token)
    
    if not ok:
        raise click.ClickException(f"Error al enviar a la API: {result}")
    
    try:
        response_data = result.json()
    except (json.JSONDecodeError, AttributeError) as e:
        raise click.ClickException(f"Error al parsear respuesta JSON: {e}")
    
    if response_data.get("status") != "success":
        raise click.ClickException(f"La API reportó error: {response_data}")
    
    transcription = response_data.get("transcription", "")
    language = response_data.get("language", "unknown")
    segments = response_data.get("segments", [])
    processing_time = response_data.get("processing_time", 0)
    model_used = response_data.get("model_used", "unknown")
    
    click.echo(f"\n📝 Transcripción ({language}):")
    click.echo(f"   {transcription}")
    click.echo(f"\n⏱️  Tiempo de procesamiento: {processing_time:.2f}s")
    click.echo(f"🤖 Modelo usado: {model_used}")
    click.echo(f"📊 Segmentos: {len(segments)}")
    
    if copy:
        if copy_to_clipboard(transcription):
            click.echo("📋 Transcripción copiada al portapapeles")
    
    if store:
        try:
            transcription_id = store_transcription(response_data, source_file=file_path, db_path=db_path)
            db_location = db_path or DEFAULT_DB_PATH
            click.echo(f"💾 Guardado en base de datos (ID: {transcription_id})")
            click.echo(f"   📁 DB: {db_location}")
        except Exception as e:
            click.echo(f"⚠️ Error al guardar en base de datos: {e}", err=True)


@cli.command("list-transcriptions")
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to SQLite database",
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Number of transcriptions to show (default: 10)",
)
@click.option(
    "--show-segments",
    is_flag=True,
    default=False,
    help="Show segments for each transcription",
)
def list_transcriptions(db_path, limit, show_segments):
    """List stored transcriptions from the local database."""
    db_path = db_path or DEFAULT_DB_PATH
    
    if not Path(db_path).exists():
        click.echo("📭 No hay base de datos. Aún no se han guardado transcripciones.")
        return
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, transcription, language, processing_time, model_used, source_file, created_at
        FROM transcriptions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    
    transcriptions = cursor.fetchall()
    
    if not transcriptions:
        click.echo("📭 No hay transcripciones almacenadas.")
        conn.close()
        return
    
    click.echo(f"📚 Últimas {len(transcriptions)} transcripciones:\n")
    
    for t in transcriptions:
        click.echo(f"━━━ ID: {t['id']} ━━━")
        click.echo(f"📅 {t['created_at']}")
        click.echo(f"🌐 Idioma: {t['language']} | ⏱️ {t['processing_time']:.2f}s | 🤖 {t['model_used']}")
        if t['source_file']:
            click.echo(f"📁 Archivo: {t['source_file']}")
        
        text_preview = t['transcription'][:100] + "..." if len(t['transcription']) > 100 else t['transcription']
        click.echo(f"📝 {text_preview}")
        
        if show_segments:
            cursor.execute("""
                SELECT segment_id, start_time, end_time, text
                FROM segments
                WHERE transcription_id = ?
                ORDER BY segment_id
            """, (t['id'],))
            segments = cursor.fetchall()
            if segments:
                click.echo("   Segmentos:")
                for seg in segments:
                    click.echo(f"   [{seg['start_time']:.2f}s - {seg['end_time']:.2f}s] {seg['text']}")
        
        click.echo()
    
    conn.close()


@cli.command("get-transcription")
@click.option(
    "--id",
    "transcription_id",
    type=int,
    required=True,
    help="Transcription ID to retrieve",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to SQLite database",
)
@click.option(
    "--copy/--no-copy",
    default=False,
    help="Copy transcription to clipboard",
)
def get_transcription(transcription_id, db_path, copy):
    """Get a specific transcription by ID and optionally copy to clipboard."""
    db_path = db_path or DEFAULT_DB_PATH
    
    if not Path(db_path).exists():
        raise click.ClickException("No hay base de datos.")
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, transcription, language, processing_time, model_used, source_file, created_at
        FROM transcriptions
        WHERE id = ?
    """, (transcription_id,))
    
    t = cursor.fetchone()
    
    if not t:
        conn.close()
        raise click.ClickException(f"No se encontró transcripción con ID {transcription_id}")
    
    click.echo(f"━━━ Transcripción ID: {t['id']} ━━━")
    click.echo(f"📅 {t['created_at']}")
    click.echo(f"🌐 Idioma: {t['language']} | ⏱️ {t['processing_time']:.2f}s | 🤖 {t['model_used']}")
    if t['source_file']:
        click.echo(f"📁 Archivo: {t['source_file']}")
    click.echo(f"\n📝 Transcripción completa:\n{t['transcription']}\n")
    
    cursor.execute("""
        SELECT segment_id, start_time, end_time, text
        FROM segments
        WHERE transcription_id = ?
        ORDER BY segment_id
    """, (transcription_id,))
    segments = cursor.fetchall()
    
    if segments:
        click.echo("📊 Segmentos:")
        for seg in segments:
            click.echo(f"   [{seg['start_time']:.2f}s - {seg['end_time']:.2f}s] {seg['text']}")
    
    conn.close()
    
    if copy:
        if copy_to_clipboard(t['transcription']):
            click.echo("\n📋 Transcripción copiada al portapapeles")


def main():
    cli()


if __name__ == "__main__":
    main()
