#!/usr/bin/env python3
"""
OBS Controller CLI - Control OBS Studio via WebSocket
"""

import argparse
import sys
import time
import random
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os

try:
    from obswebsocket import obsws, requests as obs_requests, events as obs_events
except ImportError:
    print("❌ Error: obs-websocket-py no está instalado")
    print("   Instala las dependencias con: pip install -r requirements.txt")
    sys.exit(1)

try:
    import pyperclip
except ImportError:
    print("❌ Error: pyperclip no está instalado")
    print("   Instala las dependencias con: pip install -r requirements.txt")
    sys.exit(1)


# Lista de frases Lorem Ipsum aleatorias
LOREM_IPSUM_TEXTS = [
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium.",
    "Totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.",
    "Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores.",
    "Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit.",
    "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti.",
    "Et harum quidem rerum facilis est et expedita distinctio. Nam libero tempore, cum soluta nobis est eligendi optio.",
    "Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet ut et voluptates repudiandae.",
    "Itaque earum rerum hic tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur.",
    "Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur.",
    "Vel illum qui dolorem eum fugiat quo voluptas nulla pariatur. At vero eos et accusamus.",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
]


class OBSController:
    def __init__(self, host: str = None, port: int = None, password: str = None):
        """Inicializa el controlador OBS con credenciales desde .env o parámetros."""
        
        # Cargar variables de entorno desde .env si existe
        env_path = Path(__file__).parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)
        
        # Usar parámetros o valores del .env o defaults
        self.host = host or os.getenv('OBS_HOST', 'localhost')
        self.port = int(port or os.getenv('OBS_PORT', 4455))
        self.password = password or os.getenv('OBS_PASSWORD', '')
        
        self.ws = None
        self.connected = False
    
    def connect(self):
        """Establece conexión con OBS WebSocket."""
        try:
            print(f"🔌 Conectando a OBS en {self.host}:{self.port}...")
            
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            
            print(f"✅ Conectado exitosamente a OBS")
            return True
            
        except ConnectionRefusedError:
            print(f"❌ Error: No se pudo conectar a OBS en {self.host}:{self.port}")
            print("   Asegúrate de que:")
            print("   1. OBS Studio está ejecutándose")
            print("   2. El plugin WebSocket está habilitado (Tools -> WebSocket Server Settings)")
            print("   3. El host y puerto son correctos")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error al conectar con OBS: {e}")
            print("   Verifica que la contraseña en tu archivo .env sea correcta")
            sys.exit(1)
    
    def disconnect(self):
        """Cierra la conexión con OBS."""
        if self.ws and self.connected:
            try:
                self.ws.disconnect()
                self.connected = False
                print("\n👋 Desconectado de OBS")
            except:
                pass
    
    def start_recording(self):
        """Inicia la grabación en OBS."""
        if not self.connected:
            print("❌ Error: No hay conexión con OBS")
            return False
        
        try:
            # Verificar si ya está grabando
            status = self.ws.call(obs_requests.GetRecordStatus())
            
            if status.getOutputActive():
                print("⚠️  OBS ya está grabando")
                return False
            
            # Iniciar grabación
            self.ws.call(obs_requests.StartRecord())
            print("🔴 Grabación iniciada en OBS")
            return True
            
        except Exception as e:
            print(f"❌ Error al iniciar grabación: {e}")
            return False
    
    def stop_recording(self):
        """Detiene la grabación en OBS."""
        if not self.connected:
            print("❌ Error: No hay conexión con OBS")
            return False
        
        try:
            # Verificar si está grabando
            status = self.ws.call(obs_requests.GetRecordStatus())
            
            if not status.getOutputActive():
                print("⚠️  OBS no está grabando actualmente")
                return False
            
            # Detener grabación
            self.ws.call(obs_requests.StopRecord())
            print("⏹️  Grabación detenida en OBS")
            return True
            
        except Exception as e:
            print(f"❌ Error al detener grabación: {e}")
            return False
    
    def get_recording_status(self):
        """Obtiene el estado actual de la grabación."""
        if not self.connected:
            print("❌ Error: No hay conexión con OBS")
            return None
        
        try:
            # Obtener información de OBS
            version = self.ws.call(obs_requests.GetVersion())
            record_status = self.ws.call(obs_requests.GetRecordStatus())
            
            print("\n📊 Estado de OBS:")
            print(f"   Versión OBS: {version.getObsVersion()}")
            print(f"   Versión WebSocket: {version.getObsWebSocketVersion()}")
            print(f"   Estado de grabación: {'🔴 GRABANDO' if record_status.getOutputActive() else '⚪ DETENIDO'}")
            
            if record_status.getOutputActive():
                # Obtener duración si está grabando
                timecode = record_status.getOutputTimecode()
                print(f"   Duración: {timecode}")
            
            return record_status.getOutputActive()
            
        except Exception as e:
            print(f"❌ Error al obtener estado: {e}")
            return None
    
    def listen_events(self):
        """Escucha todos los eventos de OBS y los imprime en consola."""
        if not self.connected:
            print("❌ Error: No hay conexión con OBS")
            return
        
        print("\n👂 Escuchando eventos de OBS...")
        print("   Presiona Ctrl+C para detener\n")
        
        # Función genérica para manejar cualquier evento
        def on_event(message):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            event_type = message.__class__.__name__
            
            print(f"[{timestamp}] 📡 {event_type}")
            # print(message)

            # //convertir message a dict
            message_dict = message.__dict__
            print(message_dict)
            
        
        # Registrar callback para TODOS los eventos
        # La librería obs-websocket-py permite registrar un callback general
        try:
            # Registrar eventos específicos comunes
            self.ws.register(on_event, obs_events.RecordStateChanged)
            self.ws.register(on_event, obs_events.StreamStateChanged)
            self.ws.register(on_event, obs_events.CurrentProgramSceneChanged)
            self.ws.register(on_event, obs_events.SceneItemEnableStateChanged)
            self.ws.register(on_event, obs_events.InputVolumeMeters)
            self.ws.register(on_event, obs_events.ExitStarted)
            
            # Mantener el script ejecutándose
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n\n⏹️  Dejando de escuchar eventos...")
                
        except Exception as e:
            print(f"❌ Error al escuchar eventos: {e}")
    
    def copy_random_text_to_clipboard(self):
        """Copia un texto Lorem Ipsum aleatorio al clipboard del sistema."""
        try:
            # Seleccionar un texto aleatorio de la lista
            random_text = random.choice(LOREM_IPSUM_TEXTS)
            
            # Copiar al clipboard
            pyperclip.copy(random_text)
            
            print("📋 Texto copiado al clipboard:")
            print(f"   \"{random_text[:80]}{'...' if len(random_text) > 80 else ''}\"")
            print(f"\n✅ Total: {len(random_text)} caracteres copiados")
            
            return random_text
            
        except Exception as e:
            print(f"❌ Error al copiar al clipboard: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(
        description='🎬 OBS Controller CLI - Control OBS Studio via WebSocket',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Configuración inicial
  cp .env.example .env
  # Edita .env y configura OBS_HOST, OBS_PORT, OBS_PASSWORD
  
  # Iniciar grabación en OBS
  %(prog)s --action start-recording
  
  # Detener grabación en OBS
  %(prog)s --action stop-recording
  
  # Ver estado actual de OBS
  %(prog)s --action status
  
  # Escuchar todos los eventos de OBS (mantiene el script ejecutándose)
  %(prog)s --action listen-events
  
  # Copiar texto Lorem Ipsum aleatorio al clipboard (no requiere OBS)
  %(prog)s --action copy-random-text

Requisitos previos:
  1. OBS Studio debe estar ejecutándose
  2. Habilitar WebSocket en OBS: Tools -> WebSocket Server Settings
  3. Configurar credenciales en el archivo .env
  
Variables en .env:
  OBS_HOST      - Host de OBS (default: localhost)
  OBS_PORT      - Puerto WebSocket (default: 4455)
  OBS_PASSWORD  - Contraseña del WebSocket
        """
    )
    
    parser.add_argument(
        '-a', '--action',
        type=str,
        required=True,
        choices=['start-recording', 'stop-recording', 'status', 'listen-events', 'copy-random-text'],
        help='Acción a ejecutar en OBS (o utilidades sin conexión)'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        help='Host de OBS WebSocket (override .env)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        help='Puerto de OBS WebSocket (override .env)'
    )
    
    parser.add_argument(
        '--password',
        type=str,
        help='Contraseña de OBS WebSocket (override .env)'
    )
    
    args = parser.parse_args()
    
    # Crear instancia del controlador
    controller = OBSController(
        host=args.host,
        port=args.port,
        password=args.password
    )
    
    # La acción 'copy-random-text' no requiere conexión a OBS
    if args.action == 'copy-random-text':
        controller.copy_random_text_to_clipboard()
        print("\n✅ Operación completada\n")
        return
    
    # Para las demás acciones, conectar a OBS
    controller.connect()
    
    try:
        # Ejecutar acción solicitada
        if args.action == 'start-recording':
            controller.start_recording()
        
        elif args.action == 'stop-recording':
            controller.stop_recording()
        
        elif args.action == 'status':
            controller.get_recording_status()
        
        elif args.action == 'listen-events':
            controller.listen_events()
        
    finally:
        # Asegurar desconexión limpia
        controller.disconnect()
    
    print("\n✅ Operación completada\n")


if __name__ == '__main__':
    main()
