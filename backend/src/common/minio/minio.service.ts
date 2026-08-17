import { Injectable, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from 'minio';
import { randomUUID } from 'crypto';

@Injectable()
export class MinioService implements OnModuleInit {
  private client: Client;
  private bucket: string;

  constructor(private config: ConfigService) {
    this.client = new Client({
      endPoint: this.config.get('MINIO_ENDPOINT')!,
      port: parseInt(this.config.get('MINIO_PORT')!),
      useSSL: false, // en tu red local no necesitas HTTPS
      accessKey: this.config.get('MINIO_ACCESS_KEY')!,
      secretKey: this.config.get('MINIO_SECRET_KEY')!,
    });
    this.bucket = this.config.get('MINIO_BUCKET')!;
  }

  // Se ejecuta una vez al arrancar el backend: crea el bucket si no existe
  async onModuleInit() {
    const existe = await this.client.bucketExists(this.bucket).catch(() => false);
    if (!existe) {
      await this.client.makeBucket(this.bucket);
      console.log(`Bucket "${this.bucket}" creado en MinIO`);
    }
  }

  // Sube el buffer del archivo y regresa la URL para guardar en evidencia_url
  async subirArchivo(buffer: Buffer, nombreOriginal: string, mimetype: string): Promise<string> {
    const extension = nombreOriginal.split('.').pop();
    const nombreArchivo = `${randomUUID()}.${extension}`;

    await this.client.putObject(this.bucket, nombreArchivo, buffer, buffer.length, {
      'Content-Type': mimetype,
    });

    // URL local que el dashboard usará para reproducir el video/foto
    return `http://${this.config.get('MINIO_ENDPOINT')}:${this.config.get('MINIO_PORT')}/${this.bucket}/${nombreArchivo}`;
  }
}