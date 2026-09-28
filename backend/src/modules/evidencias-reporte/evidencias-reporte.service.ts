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
      order: { orden_reproduccion: 'ASC' },
    });
  }

  async create(dto: CreateEvidenciaReporteDto) {
    const nueva = this.evidenciasRepo.create(dto);
    const evidencia = await this.evidenciasRepo.save(nueva);
    // Las evidencias son hijas del reporte. Tocar el padre permite que las
    // demás PC detecten el cambio también al consultar sus listados/deltas.
    await this.reportesRepo.update(dto.reporte_id, { updated_at: new Date() });
    return evidencia;
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

    // 2. Eliminar registro de la DB (Hard Delete) y notificar el cambio al padre.
    const resultado = await this.evidenciasRepo.delete(id);
    if (resultado.affected) {
      await this.reportesRepo.update(evidencia.reporte_id, { updated_at: new Date() });
    }
    return resultado;
  }
}
