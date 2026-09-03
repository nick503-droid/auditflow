import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { MobileSyncController } from './mobile-sync.controller';
import { MobileSyncService } from './mobile-sync.service';
import { StorageModule } from '../../common/storage/storage.module';

// Importar las entidades necesarias
import { Bitacora } from '../bitacoras/entities/bitacora.entity';
import { EvidenciaBitacora } from '../bitacoras/entities/evidencia-bitacora.entity';
import { Reporte } from '../reportes/entities/reporte.entity';
import { EvidenciaReporte } from '../evidencias-reporte/entities/evidencia-reporte.entity';

@Module({
  imports: [
    TypeOrmModule.forFeature([
      Bitacora,
      EvidenciaBitacora,
      Reporte,
      EvidenciaReporte,
    ]),
    StorageModule,
  ],
  controllers: [MobileSyncController],
  providers: [MobileSyncService],
})
export class MobileSyncModule {}
