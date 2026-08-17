import { Global, Module } from '@nestjs/common';
import { MinioService } from './minio.service';

@Global() // así cualquier módulo puede inyectar MinioService sin re-importarlo
@Module({
  providers: [MinioService],
  exports: [MinioService],
})
export class MinioModule {}