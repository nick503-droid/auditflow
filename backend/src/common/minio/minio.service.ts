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
  // y asegura que la política sea de lectura pública para que las URLs
  // directas funcionen en la red local sin presigned URLs.
  async onModuleInit() {
    const existe = await this.client.bucketExists(this.bucket).catch(() => false);
    if (!existe) {
      await this.client.makeBucket(this.bucket);
      console.log(`Bucket "${this.bucket}" creado en MinIO`);
    }

    // Política de lectura pública — permite GET anónimo a cualquier objeto
    // del bucket. Solo aplica en la red local, no se expone a internet.
    const politica = JSON.stringify({
      Version: '2012-10-17',
      Statement: [
        {
          Effect: 'Allow',
          Principal: { AWS: ['*'] },
          Action: ['s3:GetObject'],
          Resource: [`arn:aws:s3:::${this.bucket}/*`],
        },
      ],
    });
    await this.client.setBucketPolicy(this.bucket, politica);
  }

  /**
   * Sube el buffer del archivo y regresa la URL pública para guardar en evidencia_url.
   *
   * @param buffer         - Contenido binario del archivo.
   * @param nombreOriginal - Nombre original del archivo (para extraer extensión).
   * @param mimetype       - MIME type del archivo.
   * @param prefijo        - Subcarpeta opcional dentro del bucket, sin slash al final.
   *                         Ej: "bitacoras/08-25-2026" o "reportes/Riverside caso..."
   *                         Si se omite, el archivo va a la raíz del bucket (comportamiento
   *                         legado, compatible con versiones anteriores).
   */
  async subirArchivo(
    buffer: Buffer,
    nombreOriginal: string,
    mimetype: string,
    prefijo?: string,
  ): Promise<string> {
    const extension = nombreOriginal.split('.').pop();
    const uuid = randomUUID();

    // Construir la clave (key) del objeto en MinIO:
    //   sin prefijo → "uuid.ext"
    //   con prefijo  → "bitacoras/08-25-2026/uuid.ext"
    const nombreArchivo = prefijo
      ? `${prefijo}/${uuid}.${extension}`
      : `${uuid}.${extension}`;

    await this.client.putObject(this.bucket, nombreArchivo, buffer, buffer.length, {
      'Content-Type': mimetype,
    });

    // URL local que el dashboard usará para reproducir el video/foto
    return `http://${this.config.get('MINIO_ENDPOINT')}:${this.config.get('MINIO_PORT')}/${this.bucket}/${nombreArchivo}`;
  }

  /**
   * Elimina un objeto de MinIO dado su nombre de clave (key).
   * El key puede ser plano ("uuid.mp4") o con prefijo de carpeta
   * ("reportes/Riverside.../uuid.mp4").
   *
   * Retorna true si la operación tuvo éxito, false si el objeto
   * no existía o si ocurrió un error.
   */
  async eliminarArchivo(key: string): Promise<boolean> {
    try {
      await this.client.removeObject(this.bucket, key);
      return true;
    } catch (err) {
      console.error(`[MinIO] Error al eliminar objeto "${key}":`, err);
      return false;
    }
  }
}