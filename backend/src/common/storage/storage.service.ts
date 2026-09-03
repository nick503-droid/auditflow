import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as fs from 'fs';
import * as path from 'path';
import { randomUUID } from 'crypto';

@Injectable()
export class StorageService {
  private readonly logger = new Logger(StorageService.name);
  private readonly storagePath: string;
  private readonly backendUrl: string;

  constructor(private configService: ConfigService) {
    this.storagePath = this.configService.get<string>('STORAGE_PATH', '');
    this.backendUrl = this.configService.get<string>('BACKEND_URL', 'http://localhost:3000');

    if (!this.storagePath) {
      this.logger.warn('STORAGE_PATH no está definido en .env. Usando "./local_storage" por defecto.');
      this.storagePath = path.resolve('./local_storage');
    }

    // Asegurar que la carpeta base exista al arrancar el servidor
    if (!fs.existsSync(this.storagePath)) {
      fs.mkdirSync(this.storagePath, { recursive: true });
    }
    
    // Asegurar que exista la carpeta temporal
    const tempPath = path.join(this.storagePath, 'temp');
    if (!fs.existsSync(tempPath)) {
      fs.mkdirSync(tempPath, { recursive: true });
    }
  }

  /**
   * Escribe el archivo en disco duro local de forma ordenada.
   * Retorna la URL pública que puede ser usada por el frontend.
   */
  async subirArchivo(
    buffer: Buffer,
    nombreOriginal: string,
    prefijo?: string,
  ): Promise<string> {
    const uuid = randomUUID();
    
    // Limpieza de nombre
    const nombreLimpio = nombreOriginal.replace(/[^a-zA-Z0-9.\-_]/g, '_');
    const marcaTiempo = Date.now();
    
    // REQUERIMIENTO DE SEGURIDAD:
    // Se usa el UUID completo (36 caracteres) para garantizar que la URL pública sea inalcanzable 
    // por fuerza bruta (ungessable URL), protegiendo la privacidad de los videos en la red local.
    const nombreFisico = `${marcaTiempo}_${uuid}_${nombreLimpio}`;
    
    const relativoPath = prefijo ? path.join(prefijo, nombreFisico) : nombreFisico;
    const absolutoPath = path.join(this.storagePath, relativoPath);
    
    // Asegurar que la subcarpeta (ej. bitacoras/2026-08-30) exista
    const carpetaDestino = path.dirname(absolutoPath);
    if (!fs.existsSync(carpetaDestino)) {
      fs.mkdirSync(carpetaDestino, { recursive: true });
    }

    // Guardar físicamente el archivo en el disco duro
    await fs.promises.writeFile(absolutoPath, buffer);

    // Retornar la URL pública estática: http://localhost:3000/evidencias/bitacoras/2026-08-30/1725...mp4
    // Usamos replace para asegurar que las barras sean forward slashes en la URL, incluso en Windows
    const publicUrlPath = relativoPath.replace(/\\/g, '/');
    return `${this.backendUrl}/evidencias/${publicUrlPath}`;
  }

  /**
   * Guarda el archivo en una carpeta temporal (/temp) y retorna el nombre generado.
   */
  async guardarEnTemp(buffer: Buffer, nombreOriginal: string): Promise<string> {
    const uuid = randomUUID();
    const nombreLimpio = nombreOriginal.replace(/[^a-zA-Z0-9.\-_]/g, '_');
    const marcaTiempo = Date.now();
    const nombreFisico = `${marcaTiempo}_${uuid}_${nombreLimpio}`;
    
    const tempPath = path.join(this.storagePath, 'temp', nombreFisico);
    await fs.promises.writeFile(tempPath, buffer);
    
    return nombreFisico;
  }

  /**
   * Mueve un archivo de la carpeta temporal a su destino final.
   * Retorna la URL pública final.
   */
  async moverDeTemp(nombreFisico: string, prefijo: string): Promise<string> {
    const tempPath = path.join(this.storagePath, 'temp', nombreFisico);
    
    if (!fs.existsSync(tempPath)) {
      throw new Error(`El archivo temporal no existe: ${nombreFisico}`);
    }
    
    const relativoPath = path.join(prefijo, nombreFisico);
    const absolutoPath = path.join(this.storagePath, relativoPath);
    
    const carpetaDestino = path.dirname(absolutoPath);
    if (!fs.existsSync(carpetaDestino)) {
      fs.mkdirSync(carpetaDestino, { recursive: true });
    }
    
    await fs.promises.rename(tempPath, absolutoPath);
    
    const publicUrlPath = relativoPath.replace(/\\/g, '/');
    return `${this.backendUrl}/evidencias/${publicUrlPath}`;
  }

  /**
   * Elimina un archivo directamente de la carpeta temporal (Rollback).
   */
  async eliminarDeTemp(nombreFisico: string): Promise<void> {
    const tempPath = path.join(this.storagePath, 'temp', nombreFisico);
    if (fs.existsSync(tempPath)) {
      await fs.promises.unlink(tempPath);
      this.logger.log(`Rollback: Archivo temporal eliminado ${nombreFisico}`);
    }
  }

  /**
   * Elimina un archivo físico del disco dado su URL.
   */
  async eliminarArchivo(url: string): Promise<void> {
    try {
      if (!url.includes('/evidencias/')) return;
      
      // Extraer la ruta relativa de la URL
      // Ejemplo: http://localhost:3000/evidencias/bitacoras/fecha/archivo.mp4 -> bitacoras/fecha/archivo.mp4
      const partes = url.split('/evidencias/');
      if (partes.length < 2) return;
      
      const rutaRelativa = partes[1];
      const absolutoPath = path.join(this.storagePath, rutaRelativa);
      
      if (fs.existsSync(absolutoPath)) {
        await fs.promises.unlink(absolutoPath);
        this.logger.log(`Archivo físico eliminado: ${absolutoPath}`);
      } else {
        this.logger.warn(`El archivo no existía en disco: ${absolutoPath}`);
      }
    } catch (error) {
      this.logger.error(`Error eliminando archivo físico: ${error.message}`, error.stack);
    }
  }
}
