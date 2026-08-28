import {
  Controller,
  Post,
  UseInterceptors,
  UploadedFile,
  Body,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { MinioService } from '../../common/minio/minio.service';

@Controller('uploads')
export class UploadsController {
  constructor(private readonly minioService: MinioService) {}

  /**
   * POST /uploads
   *
   * Sube un archivo a MinIO. Acepta un campo de formulario opcional
   * `prefijo_nube` que indica la subcarpeta de destino dentro del bucket.
   *
   * Campos multipart esperados:
   *   file        (requerido) — el archivo binario
   *   prefijo_nube (opcional) — subcarpeta, p. ej. "bitacoras/08-25-2026"
   *                             o "reportes/Riverside caso Natalie..."
   *
   * Si no se envía `prefijo_nube`, el archivo va a la raíz del bucket
   * (comportamiento legado compatible con versiones anteriores de la app).
   */
  @Post()
  @UseInterceptors(FileInterceptor('file')) // 'file' = nombre del campo en el form-data
  async subir(
    @UploadedFile() file: Express.Multer.File,
    @Body('prefijo_nube') prefijo_nube?: string,
  ) {
    const url = await this.minioService.subirArchivo(
      file.buffer,
      file.originalname,
      file.mimetype,
      prefijo_nube || undefined, // pasar undefined en lugar de string vacío
    );
    return { evidencia_url: url };
  }
}