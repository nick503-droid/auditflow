import { Controller, Get, InternalServerErrorException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

@Controller('system')
export class SystemController {
  constructor(private configService: ConfigService) {}

  @Get('info')
  async getSystemInfo() {
    // 1. Obtener IP del servidor
    let serverIp = this.configService.get<string>('BACKEND_URL') 
      || this.configService.get<string>('MINIO_PUBLIC_ENDPOINT') 
      || 'Desconocida';
    
    // Limpiar la IP para visualización (quitar http:// y puerto si se desea, o dejarlo así)
    if (serverIp.includes('://')) {
        serverIp = serverIp.split('://')[1];
    }
    serverIp = serverIp.split(':')[0]; // quitar el puerto para mostrar solo la IP si se quiere, o dejarlo como está.

    const fullUrl = this.configService.get<string>('BACKEND_URL') 
    || this.configService.get<string>('MINIO_PUBLIC_ENDPOINT') 
    || 'http://192.168.1.150:3000';

    // 2. Obtener almacenamiento (usando df -h)
    const storagePath = this.configService.get<string>('STORAGE_PATH', '/usr/src/app/storage');
    
    let storageInfo = {
      total: 'N/A',
      usado: 'N/A',
      disponible: 'N/A',
      porcentaje: '0%',
      ruta: storagePath
    };

    try {
      // df -h devuelve algo como:
      // Filesystem      Size  Used Avail Use% Mounted on
      // overlay          50G   20G   30G  40% /
      const { stdout } = await execAsync(`df -h ${storagePath}`);
      const lines = stdout.trim().split('\n');
      
      if (lines.length > 1) {
        // La segunda línea tiene los datos
        // Ej: overlay 50G 20G 30G 40% /
        const parts = lines[1].trim().split(/\s+/);
        if (parts.length >= 5) {
          storageInfo = {
            total: parts[1],
            usado: parts[2],
            disponible: parts[3],
            porcentaje: parts[4],
            ruta: storagePath
          };
        }
      }
    } catch (error) {
      console.error(`Error ejecutando df -h en ${storagePath}:`, error);
      // Fallback si falla (ej. en Windows local sin WSL)
      storageInfo.total = 'Desconocido';
      storageInfo.usado = 'Error de lectura';
    }

    return {
      ip: fullUrl, // Devolver la URL completa para mayor claridad
      storage: storageInfo,
      entorno: process.env.NODE_ENV || 'development'
    };
  }
}
