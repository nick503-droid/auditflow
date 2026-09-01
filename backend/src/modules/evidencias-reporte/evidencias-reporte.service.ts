// evidencias-reporte.service.ts
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { EvidenciaReporte } from './entities/evidencia-reporte.entity';
import { CreateEvidenciaReporteDto } from './dto/create-evidencias-reporte.dto';
import { UpdateEvidenciasReporteDto } from './dto/update-evidencias-reporte.dto';
import { StorageService } from '../../common/storage/storage.service';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class EvidenciasReporteService {
  constructor(
    @InjectRepository(EvidenciaReporte)
    private evidenciasRepo: Repository<EvidenciaReporte>,
    private storageService: StorageService,
    private configService: ConfigService,
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

  async remove(id: string) {
    const evidencia = await this.findOne(id);
    if (!evidencia) {
      return null;
    }

    if (evidencia.evidencia_url) {
      // 1. Eliminar físicamente del almacenamiento local (Hard Delete)
      await this.storageService.eliminarArchivo(evidencia.evidencia_url);
    }

    // 2. Eliminar registro de la DB (Hard Delete)
    return this.evidenciasRepo.delete(id);
  }
}