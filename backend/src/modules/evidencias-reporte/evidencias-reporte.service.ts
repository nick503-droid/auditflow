// evidencias-reporte.service.ts
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { EvidenciaReporte } from './entities/evidencia-reporte.entity';
import { CreateEvidenciaReporteDto } from './dto/create-evidencias-reporte.dto';
import { UpdateEvidenciasReporteDto } from './dto/update-evidencias-reporte.dto';

@Injectable()
export class EvidenciasReporteService {
  constructor(
    @InjectRepository(EvidenciaReporte)
    private evidenciasRepo: Repository<EvidenciaReporte>,
  ) {}

  findOne(id: string) {
    return this.evidenciasRepo.findOneBy({ id });
  }

  findByReporte(reporte_id: string) {
    return this.evidenciasRepo.find({
      where: { reporte_id },
      order: { orden_reproduccion: 'ASC' },
    });
  }

  create(dto: CreateEvidenciaReporteDto) {
    const nueva = this.evidenciasRepo.create(dto);
    return this.evidenciasRepo.save(nueva);
  }

  async update(id: string, dto: UpdateEvidenciasReporteDto) {
    await this.evidenciasRepo.update(id, dto);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.evidenciasRepo.softDelete(id);
  }
}