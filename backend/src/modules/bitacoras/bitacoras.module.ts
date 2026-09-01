import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { BitacorasService } from './bitacoras.service';
import { BitacorasController } from './bitacoras.controller';
// minio import removed
import { ConfigModule } from '@nestjs/config';

@Module({
  imports: [
    TypeOrmModule.forFeature([Bitacora, EvidenciaBitacora]),
    ConfigModule,
  ],
  controllers: [BitacorasController],
  providers: [BitacorasService],
})
export class BitacorasModule {}