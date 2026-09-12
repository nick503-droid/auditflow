import {
  Controller,
  Post,
  UseInterceptors,
  UploadedFile,
  Body,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { StorageService } from '../../common/storage/storage.service';

@Controller('uploads')
export class UploadsController {
  constructor(private readonly storageService: StorageService) {}

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
    const url = await this.storageService.subirArchivo(
      file.buffer,
      file.originalname,
      prefijo_nube || undefined, // pasar undefined en lugar de string vacío
    );
    return { evidencia_url: url };
  }

  /**
   * POST /uploads/chunk
   * Sube un fragmento de archivo.
   */
  @Post('chunk')
  @UseInterceptors(FileInterceptor('file'))
  async uploadChunk(
    @UploadedFile() file: Express.Multer.File,
    @Body('fileId') fileId: string,
    @Body('chunkIndex') chunkIndex: string,
  ) {
    if (!file || !fileId || chunkIndex === undefined) {
      throw new Error('Missing chunk parameters');
    }
    await this.storageService.guardarChunk(fileId, parseInt(chunkIndex, 10), file.buffer);
    return { success: true };
  }

  /**
   * POST /uploads/commit
   * Ensambla todos los fragmentos previamente subidos.
   */
  @Post('commit')
  async commitChunks(
    @Body('fileId') fileId: string,
    @Body('originalname') originalname: string,
    @Body('totalChunks') totalChunks: string,
    @Body('prefijo_nube') prefijo_nube?: string,
  ) {
    if (!fileId || !originalname || !totalChunks) {
      throw new Error('Missing commit parameters');
    }
    const url = await this.storageService.commitChunks(
      fileId,
      originalname,
      parseInt(totalChunks, 10),
      prefijo_nube || undefined,
    );
    return { evidencia_url: url };
  }
}