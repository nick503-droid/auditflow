// evidencias-reporte.service.ts
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { EvidenciaReporte } from './entities/evidencia-reporte.entity';
import { Reporte } from '../reportes/entities/reporte.entity';
import { CreateEvidenciaReporteDto } from './dto/create-evidencias-reporte.dto';
import { UpdateEvidenciasReporteDto } from './dto/update-evidencias-reporte.dto';
import { StorageService } from '../../common/storage/storage.service';
import { ConfigService } from '@nestjs/config';
import { registrarEvidenciaOrdenada } from '../../common/evidence-order';

@Injectable()
export class EvidenciasReporteService {
  constructor(
    @InjectRepository(EvidenciaReporte)
    private evidenciasRepo: Repository<EvidenciaReporte>,
    @InjectRepository(Reporte)
    private reportesRepo: Repository<Reporte>,
    private storageService: StorageService,
    private configService: ConfigService,
  ) {}

  findOne(id: string) {
    return this.evidenciasRepo.findOneBy({ id });
  }

  findByReporte(reporte_id: string) {
    return this.evidenciasRepo.find({
      where: { reporte_id },
      order: { agregado_en: 'ASC', secuencia_adicion: 'ASC', orden_reproduccion: 'ASC', id: 'ASC' },
    });
  }

  async create(dto: CreateEvidenciaReporteDto) {
    const { agregado_en, ...values } = dto;
    return registrarEvidenciaOrdenada(
      this.evidenciasRepo, this.reportesRepo, dto.reporte_id, 'reporte_id', values, agregado_en,
    );
  }

  async update(id: string, dto: UpdateEvidenciasReporteDto) {
    // La incorporación es inmutable, también desde PATCH.
    const { agregado_en: _agregado, ...changes } = dto;
    await this.evidenciasRepo.update(id, changes);
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

    // 2. Eliminar registro de la DB (Hard Delete) y notificar el cambio al padre.
    const resultado = await this.evidenciasRepo.delete(id);
    if (resultado.affected) {
      await this.reportesRepo.update(evidencia.reporte_id, { updated_at: new Date() });
    }
    return resultado;
  }
}
