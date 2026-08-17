import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Reporte } from './entities/reporte.entity';
import { CreateReporteDto } from './dto/create-reporte.dto';
import { UpdateReporteDto } from './dto/update-reporte.dto';

@Injectable()
export class ReportesService {
  constructor(
    @InjectRepository(Reporte)
    private reportesRepo: Repository<Reporte>,
  ) {}

  findAll() {
    return this.reportesRepo.find({
      relations: ['usuario', 'restaurante', 'evidencias'],
      order: { fecha_jornada: 'DESC' },
    });
  }

  findOne(id: string) {
    return this.reportesRepo.findOne({
      where: { id },
      relations: ['usuario', 'restaurante', 'evidencias'],
    });
  }

  // Este es el endpoint que golpea la app de PC al final del día,
  // enviando el paquete completo desde el SQLite local
  create(dto: CreateReporteDto) {
    const nuevo = this.reportesRepo.create(dto);
    return this.reportesRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateReporteDto) {
    await this.reportesRepo.update(id, dto);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.reportesRepo.softDelete(id);
  }
}