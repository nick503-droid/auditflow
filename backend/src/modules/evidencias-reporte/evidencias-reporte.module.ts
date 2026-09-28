import { Module } from '@nestjs/common';
import { EvidenciasReporteService } from './evidencias-reporte.service';
import { EvidenciasReporteController } from './evidencias-reporte.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EvidenciaReporte } from './entities/evidencia-reporte.entity';
import { Reporte } from '../reportes/entities/reporte.entity';
// minio import removed
import { ConfigModule } from '@nestjs/config';

@Module({
  imports: [
    TypeOrmModule.forFeature([EvidenciaReporte, Reporte]),
    ConfigModule,
  ],
  controllers: [EvidenciasReporteController],
  providers: [EvidenciasReporteService],
})
export class EvidenciasReporteModule {}
