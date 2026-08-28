import { Module } from '@nestjs/common';
import { ReportesService } from './reportes.service';
import { ReportesController } from './reportes.controller';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Reporte } from './entities/reporte.entity';
import { EvidenciaReporte } from '../evidencias-reporte/entities/evidencia-reporte.entity';

@Module({
  // EvidenciaReporte se agrega para que ReportesService pueda inyectar su
  // repositorio y hacer hard-delete en cascada al eliminar un reporte.
  imports: [TypeOrmModule.forFeature([Reporte, EvidenciaReporte])],
  controllers: [ReportesController],
  providers: [ReportesService],
})
export class ReportesModule {}