import { Controller, Get, Post, Body, Param, Delete, Patch } from '@nestjs/common';
import { ReportesService } from './reportes.service';
import { CreateReporteDto } from './dto/create-reporte.dto';
import { UpdateReporteDto } from './dto/update-reporte.dto';

@Controller('reportes')
export class ReportesController {
  constructor(private readonly reportesService: ReportesService) {}

  @Get()
  findAll() {
    return this.reportesService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.reportesService.findOne(id);
  }

  @Post()
  create(@Body() dto: CreateReporteDto) {
    return this.reportesService.create(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateReporteDto) {
    return this.reportesService.update(id, dto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.reportesService.remove(id);
  }
}