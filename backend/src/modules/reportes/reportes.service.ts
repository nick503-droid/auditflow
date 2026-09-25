import { ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { Reporte } from './entities/reporte.entity';
import { CreateReporteDto } from './dto/create-reporte.dto';
import { UpdateReporteDto } from './dto/update-reporte.dto';
import { EvidenciaReporte } from '../evidencias-reporte/entities/evidencia-reporte.entity';
import { StorageService } from '../../common/storage/storage.service';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class ReportesService {
  constructor(
    @InjectRepository(Reporte)
    private reportesRepo: Repository<Reporte>,

    @InjectRepository(EvidenciaReporte)
    private evidenciasRepo: Repository<EvidenciaReporte>,

    private readonly storageService: StorageService,
  ) { }

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

  // El método es asíncrono para esperar la generación del código único
  async create(dto: CreateReporteDto) {
    const codigo = await this.generarCodigoUnico();

    const nuevo = this.reportesRepo.create({
      ...dto,
      codigo: codigo,
    });

    return this.reportesRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateReporteDto) {
    const { version, ...cambios } = dto;
    const reporte = await this.findOne(id);
    if (!reporte) return null;

    // La comprobación debe formar parte del UPDATE. Consultar y luego save()
    // permite que dos PCs pasen la comprobación y una pise a la otra.
    if (version === undefined || version === null) {
      throw new ConflictException('El cliente debe actualizar el reporte antes de guardar.');
    }

    const resultado = await this.reportesRepo
      .createQueryBuilder()
      .update(Reporte)
      .set({
        ...cambios,
        updated_at: new Date(),
        version: () => 'version + 1',
      })
      .where('id = :id AND version = :version', { id, version })
      .execute();

    if (!resultado.affected) {
      throw new ConflictException('El reporte fue modificado por otro auditor.');
    }

    return this.findOne(id);
  }

  /**
   * Elimina un reporte de forma COMPLETA (hard delete):
   *   1. Carga el reporte y sus evidencias.
   *   2. Por cada evidencia, extrae el key de MinIO de la URL pública
   *      y llama a MinioService.eliminarArchivo().
   *   3. Hard-deletes las evidencias de la base de datos.
   *   4. Hard-deletes el reporte de la base de datos.
   *
   * Si el reporte no existe se lanza NotFoundException.
   * Si MinIO falla en algún archivo, se registra el error en consola
   * pero la operación continúa para no bloquear la eliminación del
   * registro en base de datos.
   */
  async remove(id: string) {
    const reporte = await this.reportesRepo.findOne({ where: { id } });
    if (!reporte) {
      throw new NotFoundException(`Reporte con id "${id}" no encontrado.`);
    }
    await this.reportesRepo.softDelete(id);
    return { eliminado: true };
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  private async generarCodigoUnico(): Promise<string> {
    const fechaLimite = new Date();
    fechaLimite.setDate(fechaLimite.getDate() - DIAS_VIGENCIA_CODIGO);

    for (let intento = 0; intento < 10; intento++) {
      const candidato = this.generarCodigoAleatorio();

      const existente = await this.reportesRepo.findOne({
        where: {
          codigo: candidato,
          fecha_jornada: MoreThanOrEqual(fechaLimite as any),
        },
      });

      if (!existente) {
        return candidato;
      }
    }

    throw new Error('No se pudo generar un código de reporte único');
  }

  private generarCodigoAleatorio(): string {
    let resultado = '';
    for (let i = 0; i < 6; i++) {
      const indice = Math.floor(Math.random() * CARACTERES_CODIGO.length);
      resultado += CARACTERES_CODIGO[indice];
    }
    return resultado;
  }


}
