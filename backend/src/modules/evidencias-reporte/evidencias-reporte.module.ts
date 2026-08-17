import { Module } from '@nestjs/common';
import { EvidenciasReporteService } from './evidencias-reporte.service';
import { EvidenciasReporteController } from './evidencias-reporte.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EvidenciaReporte } from './entities/evidencia-reporte.entity';

@Module({
  imports: [TypeOrmModule.forFeature([EvidenciaReporte])],
  controllers: [EvidenciasReporteController],
  providers: [EvidenciasReporteService],
})
export class EvidenciasReporteModule {}