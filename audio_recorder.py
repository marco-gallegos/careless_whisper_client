#!/usr/bin/env python3
"""
Audio Recorder CLI - Graba audio con ffmpeg y ejecuta comandos después
"""

import argparse
import subprocess
import sys
import re
from pathlib import Path
from datetime import datetime


class AudioRecorder:
    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir) if output_dir else Path.cwd() / "recordings"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def list_devices(self):
        """Lista todos los dispositivos de audio disponibles usando ffmpeg."""
        print("🎤 Listando dispositivos de audio disponibles...\n")
        
        try:
            # Ejecutar ffmpeg para listar dispositivos
            result = subprocess.run(
                ['ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # ffmpeg envía la lista de dispositivos a stderr
            output = result.stderr
            
            # Parsear dispositivos de audio (entrada)
            audio_devices = []
            in_audio_section = False
            
            for line in output.split('\n'):
                if 'AVFoundation audio devices:' in line:
                    in_audio_section = True
                    continue
                elif 'AVFoundation video devices:' in line:
                    in_audio_section = False
                    continue
                    
                if in_audio_section:
                    # Buscar líneas con formato [AVFoundation indev @ ...] [0] Device Name
                    match = re.search(r'\[(\d+)\]\s+(.+)$', line)
                    if match:
                        device_id = match.group(1)
                        device_name = match.group(2).strip()
                        audio_devices.append((device_id, device_name))
            
            if audio_devices:
                print("Dispositivos de audio disponibles:")
                for dev_id, dev_name in audio_devices:
                    print(f"  [{dev_id}] {dev_name}")
                print()
                return audio_devices
            else:
                print("⚠️  No se encontraron dispositivos de audio.")
                return []
                
        except FileNotFoundError:
            print("❌ Error: ffmpeg no está instalado o no está en el PATH")
            print("   Instala ffmpeg con: brew install ffmpeg")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            print("❌ Error: Timeout al listar dispositivos")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error al listar dispositivos: {e}")
            sys.exit(1)
    
    def select_device_interactive(self):
        """Permite al usuario seleccionar un dispositivo de forma interactiva."""
        devices = self.list_devices()
        
        if not devices:
            print("No hay dispositivos disponibles para seleccionar.")
            sys.exit(1)
        
        while True:
            try:
                choice = input("Selecciona el número del dispositivo que deseas usar: ").strip()
                device_id = int(choice)
                
                # Verificar que el ID existe en la lista
                valid_ids = [int(dev[0]) for dev in devices]
                if device_id in valid_ids:
                    return str(device_id)
                else:
                    print(f"⚠️  ID inválido. Por favor selecciona uno de: {valid_ids}")
            except ValueError:
                print("⚠️  Por favor ingresa un número válido.")
            except KeyboardInterrupt:
                print("\n\n👋 Operación cancelada por el usuario.")
                sys.exit(0)
    
    def record(self, device_id: str, duration: int = None, output_filename: str = None):
        """Graba audio desde el dispositivo especificado."""
        
        # Generar nombre de archivo si no se proporciona
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"recording_{timestamp}.wav"
        
        # Asegurar que tenga extensión .wav
        if not output_filename.endswith('.wav'):
            output_filename += '.wav'
        
        output_path = self.output_dir / output_filename
        
        print(f"\n🎙️  Iniciando grabación...")
        print(f"   Dispositivo: {device_id}")
        print(f"   Guardando en: {output_path}")
        
        if duration:
            print(f"   Duración: {duration} segundos")
        else:
            print(f"   Presiona Ctrl+C para detener la grabación")
        
        print()
        
        # Construir comando de ffmpeg
        cmd = ['ffmpeg', '-f', 'avfoundation', '-i', f':{device_id}']
        
        if duration:
            cmd.extend(['-t', str(duration)])
        
        cmd.append(str(output_path))
        
        try:
            subprocess.run(cmd, check=True)
            print(f"\n✅ Grabación completada: {output_path}")
            return output_path
            
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error durante la grabación: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n\n⏹️  Grabación detenida por el usuario.")
            print(f"✅ Archivo guardado: {output_path}")
            return output_path
    
    def execute_command(self, command: str, audio_file: Path):
        """Ejecuta un comando después de la grabación."""
        print(f"\n🚀 Ejecutando comando post-grabación...")
        print(f"   Comando: {command}")
        print(f"   Archivo: {audio_file}")
        print()
        
        # Reemplazar {file} en el comando con la ruta del archivo
        command = command.replace('{file}', str(audio_file))
        command = command.replace('{filename}', audio_file.name)
        command = command.replace('{filepath}', str(audio_file.absolute()))
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=False,
                text=True
            )
            
            if result.returncode == 0:
                print(f"\n✅ Comando ejecutado exitosamente")
            else:
                print(f"\n⚠️  Comando finalizado con código: {result.returncode}")
                
        except Exception as e:
            print(f"\n❌ Error al ejecutar comando: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='🎙️  Audio Recorder CLI - Graba audio con ffmpeg',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Listar dispositivos disponibles
  %(prog)s --list-devices
  
  # Grabar con dispositivo 0 (duración indefinida, Ctrl+C para detener)
  %(prog)s --device 0
  
  # Grabar 10 segundos con dispositivo 1
  %(prog)s --device 1 --duration 10
  
  # Grabar y ejecutar comando después
  %(prog)s --device 0 --post-command "echo 'Grabación lista: {file}'"
  
  # Grabar con nombre personalizado
  %(prog)s --device 0 --output mi_grabacion.wav
  
  # Si no especificas dispositivo, se te pedirá seleccionar uno
  %(prog)s

Variables disponibles en --post-command:
  {file}      - Ruta completa del archivo
  {filename}  - Solo el nombre del archivo
  {filepath}  - Ruta absoluta del archivo
        """
    )
    
    parser.add_argument(
        '-l', '--list-devices',
        action='store_true',
        help='Lista todos los dispositivos de audio disponibles y sale'
    )
    
    parser.add_argument(
        '-d', '--device',
        type=str,
        help='ID del dispositivo de audio a usar (ej: 0, 1, 2...)'
    )
    
    parser.add_argument(
        '-t', '--duration',
        type=int,
        help='Duración de la grabación en segundos (opcional, si no se especifica graba hasta Ctrl+C)'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        help='Nombre del archivo de salida (default: recording_TIMESTAMP.wav)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./recordings',
        help='Directorio donde guardar las grabaciones (default: ./recordings)'
    )
    
    parser.add_argument(
        '-c', '--post-command',
        type=str,
        help='Comando a ejecutar después de la grabación. Usa {file} para referenciar el archivo grabado'
    )
    
    args = parser.parse_args()
    
    # Crear instancia del recorder
    recorder = AudioRecorder(output_dir=args.output_dir)
    
    # Si solo se pide listar dispositivos
    if args.list_devices:
        recorder.list_devices()
        return
    
    # Determinar qué dispositivo usar
    device_id = args.device
    
    if not device_id:
        print("ℹ️  No se especificó dispositivo. Selecciona uno de la lista:\n")
        device_id = recorder.select_device_interactive()
    
    # Grabar audio
    audio_file = recorder.record(
        device_id=device_id,
        duration=args.duration,
        output_filename=args.output
    )
    
    # Ejecutar comando post-grabación si se especificó
    if args.post_command:
        recorder.execute_command(args.post_command, audio_file)
    
    print(f"\n🎉 ¡Listo! Tu archivo está en: {audio_file.absolute()}\n")


if __name__ == '__main__':
    main()
