#!/usr/bin/env python3
"""
OBS Record and Send - Start recording via OBS WebSocket, wait until stopped,
capture the output file path, and optionally send it to an external API.
"""

import os
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

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
            click.echo(result.text[:1000])
    else:
        raise click.ClickException(f"Error al enviar: {result}")


def main():
    cli()


if __name__ == "__main__":
    main()
