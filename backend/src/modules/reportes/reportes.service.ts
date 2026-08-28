import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { Reporte } from './entities/reporte.entity';
import { CreateReporteDto } from './dto/create-reporte.dto';
import { UpdateReporteDto } from './dto/update-reporte.dto';
import { EvidenciaReporte } from '../evidencias-reporte/entities/evidencia-reporte.entity';
import { MinioService } from '../../common/minio/minio.service';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class ReportesService {
  constructor(
    @InjectRepository(Reporte)
    private reportesRepo: Repository<Reporte>,

    @InjectRepository(EvidenciaReporte)
    private evidenciasRepo: Repository<EvidenciaReporte>,

    private readonly minioService: MinioService,
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
    await this.reportesRepo.update(id, dto);
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
  async remove(id: string): Promise<{ eliminado: boolean; evidencias_borradas: number }> {
    const reporte = await this.reportesRepo.findOne({
      where: { id },
      relations: ['evidencias'],
      withDeleted: true, // por si ya estaba soft-deleted
    });

    if (!reporte) {
      throw new NotFoundException(`Reporte con id "${id}" no encontrado.`);
    }

    const evidencias = reporte.evidencias ?? [];
    let evidencias_borradas = 0;

    // ── Limpiar archivos en MinIO ─────────────────────────────────────────────
    for (const ev of evidencias) {
      const key = this.extraerKeyDeUrl(ev.evidencia_url);
      if (key) {
        const ok = await this.minioService.eliminarArchivo(key);
        if (ok) evidencias_borradas++;
      }
    }

    // ── Eliminar evidencias de la base de datos (hard delete) ─────────────────
    if (evidencias.length > 0) {
      const ids = evidencias.map((e) => e.id);
      await this.evidenciasRepo
        .createQueryBuilder()
        .delete()
        .whereInIds(ids)
        .execute();
    }

    // ── Eliminar el reporte (hard delete) ─────────────────────────────────────
    await this.reportesRepo
      .createQueryBuilder()
      .delete()
      .where('id = :id', { id })
      .execute();

    return { eliminado: true, evidencias_borradas };
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

  /**
   * Extrae el "key" (clave de objeto) de MinIO a partir de la URL pública.
   *
   * La URL tiene la forma:
   *   http://<host>:<port>/<bucket>/<key>
   *
   * Ejemplo:
   *   "http://localhost:9000/auditflow/reportes/Riverside.../uuid.mp4"
   *   → "reportes/Riverside.../uuid.mp4"
   *
   * Retorna null si la URL no tiene el formato esperado.
   */
  private extraerKeyDeUrl(url: string): string | null {
    if (!url) return null;
    try {
      const urlObj = new URL(url);
      // El pathname tiene la forma /<bucket>/<key>
      // Quitamos el primer "/" y el nombre del bucket
      const partes = urlObj.pathname.split('/').filter(Boolean);
      if (partes.length < 2) return null;
      // partes[0] = bucket, partes[1..N] = key (puede tener subcarpetas)
      return partes.slice(1).join('/');
    } catch {
      return null;
    }
  }
}