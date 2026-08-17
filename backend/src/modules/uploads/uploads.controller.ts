import {
  Controller,
  Post,
  UseInterceptors,
  UploadedFile,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { MinioService } from '../../common/minio/minio.service';

@Controller('uploads')
export class UploadsController {
  constructor(private readonly minioService: MinioService) {}

  @Post()
  @UseInterceptors(FileInterceptor('file')) // 'file' = nombre del campo en el form-data
  async subir(@UploadedFile() file: Express.Multer.File) {
    const url = await this.minioService.subirArchivo(
      file.buffer,
      file.originalname,
      file.mimetype,
    );
    return { evidencia_url: url };
  }
}