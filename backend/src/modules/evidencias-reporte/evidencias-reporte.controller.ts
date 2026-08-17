import { Controller, Post, Get, Patch, Delete, Body, Param } from '@nestjs/common';
import { EvidenciasReporteService } from './evidencias-reporte.service';
import { CreateEvidenciaReporteDto } from './dto/create-evidencias-reporte.dto';
import { UpdateEvidenciasReporteDto } from './dto/update-evidencias-reporte.dto';

@Controller('evidencias-reporte')
export class EvidenciasReporteController {
  constructor(private readonly evidenciasService: EvidenciasReporteService) {}

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.evidenciasService.findOne(id);
  }

  @Get('reporte/:reporteId')
  findByReporte(@Param('reporteId') reporteId: string) {
    return this.evidenciasService.findByReporte(reporteId);
  }

  @Post()
  create(@Body() dto: CreateEvidenciaReporteDto) {
    return this.evidenciasService.create(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateEvidenciasReporteDto) {
    return this.evidenciasService.update(id, dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.evidenciasService.remove(id);
  }
}