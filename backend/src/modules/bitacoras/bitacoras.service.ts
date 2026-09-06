import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { IsNull, Repository } from 'typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';
import { StorageService } from '../../common/storage/storage.service';
import { ConfigService } from '@nestjs/config';
import { generarCodigoUnico } from '../../common/utils/code-generator';

@Injectable()
export class BitacorasService {
  constructor(
    @InjectRepository(Bitacora)
    private bitacorasRepo: Repository<Bitacora>,
    @InjectRepository(EvidenciaBitacora)
    private evidenciasRepo: Repository<EvidenciaBitacora>,
    private storageService: StorageService,
    private configService: ConfigService,
  ) {}

  findAll() {
    return this.bitacorasRepo.find({
      relations: { usuario: true, restaurante: true, evidencias: true },
      order: { fecha: 'DESC', hora: 'DESC' },
    });
  }

  /**
   * Trae todas las bitácoras de una fecha específica, sin filtrar por
   * usuario ni restaurante — esto es lo que llena la cuadrícula
   * compartida entre todos los videovigilantes.
   */
  findPorFecha(fecha: string) {
    // Usamos string crudo en lugar de new Date(fecha) para evitar 
    // que la zona horaria atrase el día por accidente.
    return this.bitacorasRepo.find({
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      where: { fecha: fecha as any },
      relations: { usuario: true, restaurante: true, evidencias: true },
      order: { hora: 'ASC' },
    });
  }

  findOne(id: string) {
    return this.bitacorasRepo.findOne({
      where: { id },
      relations: { usuario: true, restaurante: true, evidencias: true },
    });
  }

  findPorCodigo(codigo: string) {
    return this.bitacorasRepo.findOne({
      where: { codigo: codigo.toUpperCase() },
      order: { fecha: 'DESC' }, // si hay colisión de código viejo, toma la más reciente
    });
  }

  /**
   * Devuelve las evidencias de la bitácora identificada por código corto.
   * Retorna [] si no existe o hay error.
   */
  async findEvidenciasPorCodigo(codigo: string): Promise<EvidenciaBitacora[]> {
    const bitacora = await this.findPorCodigo(codigo);
    if (!bitacora) return [];
    return this.evidenciasRepo.find({
      where: { bitacora_id: bitacora.id },
      order: { creado_en: 'ASC' },
    });
  }

  async create(dto: CreateBitacoraDto) {
    const { client_id, ...restoDto } = dto;

    // 1. Idempotencia (Camino rápido para reintentos diferidos)
    if (client_id) {
      // Retiramos las relations pesadas. Solo necesitamos saber si existe.
      const existente = await this.bitacorasRepo.findOne({
        where: { id: client_id },
      });
      if (existente) return existente; 
    }

    const codigo = await generarCodigoUnico(this.bitacorasRepo, {
      campoCodigo: 'codigo',
      campoFecha: 'fecha',
    });

    const nueva = this.bitacorasRepo.create({
      id: client_id, // Si es undefined, TypeORM generará el UUID
      descripcion: '',
      hora: '',
      ...restoDto,
      fecha: dto.fecha ? dto.fecha : new Date(),
      codigo,
    });
    
    // 2. Inserción Segura (Atrapa concurrencia exacta)
    try {
      return await this.bitacorasRepo.save(nueva);
    } catch (error) {
      // 1062 es el código de MySQL para ER_DUP_ENTRY (Duplicate entry for primary key)
      if (error.code === 'ER_DUP_ENTRY' || error.errno === 1062) {
        // Alguien más (el otro hilo) lo insertó fracciones de segundo antes.
        // Retornamos la entidad que intentábamos guardar, simulando éxito.
        return nueva; 
      }
      throw error;
    }
  }

  async update(id: string, dto: UpdateBitacoraDto) {
    await this.bitacorasRepo.update(id, dto);
    return this.findOne(id);
  }

  /**
   * Cierra todas las bitácoras abiertas de una fecha dada:
   * establece `cerrada_en = NOW()` en las que tienen `cerrada_en IS NULL`.
   * Retorna cuántas filas se marcaron como cerradas.
   */
  async cerrarBitacoraDia(fecha: string): Promise<{ cerradas: number }> {
    // Usamos QueryBuilder. Pasamos el string de la fecha directamente ('YYYY-MM-DD')
    // Esto es 100% inmune a problemas de zonas horarias de JavaScript.
    const result = await this.bitacorasRepo
      .createQueryBuilder()
      .update(Bitacora)
      .set({ cerrada_en: new Date() })
      .where('fecha = :fecha', { fecha })
      .andWhere('cerrada_en IS NULL')
      .execute();

    return { cerradas: result.affected ?? 0 };
  }

  /**
   * Adjunta una nueva evidencia a la bitácora identificada por `codigo`.
   *
   * OPTIMIZACIÓN N+1 (antes: 3 queries → ahora: 2 queries):
   *   1. findPorCodigo(codigo)  → SELECT bitacora completo con relaciones  [eliminado]
   *   2. evidenciasRepo.save()  → INSERT evidencia                          [conservado]
   *   3. findOne(bitacora.id)   → SELECT bitácora + relaciones nuevamente   [conservado, pero ligero]
   *
   * Nueva estrategia:
   *   Q1 (lean): SELECT b.id FROM bitacoras WHERE codigo = ? LIMIT 1
   *              → solo el UUID, sin hidratar relaciones ni evidencias.
   *   Q2       : INSERT INTO evidencias_bitacora ...
   *   Q3 (lean): SELECT evidencias WHERE bitacora_id = ?
   *              → devuelve solo las evidencias (lo que el controller retorna).
   */
  async adjuntarEvidenciaPorCodigo(
    codigo: string,
    evidencia_url: string,
    con_audio: boolean,
  ) {
    // Q1 — Obtener solo el id de la bitácora; sin cargar relaciones costosas.
    const fila = await this.bitacorasRepo
      .createQueryBuilder('b')
      .select('b.id', 'id')
      .where('b.codigo = :codigo', { codigo: codigo.toUpperCase() })
      .orderBy('b.fecha', 'DESC')
      .limit(1)
      .getRawOne<{ id: string }>();

    if (!fila) {
      return null;
    }

    // Q2 — Insertar la nueva evidencia directamente con el id obtenido.
    const nueva = this.evidenciasRepo.create({
      bitacora_id: fila.id,
      evidencia_url,
      con_audio,
    });
    await this.evidenciasRepo.save(nueva);

    // Q3 — Retornar la bitácora con sus relaciones para el response del controller.
    //      findOne() aquí es necesario para que el PC-App actualice su panel lateral.
    return this.findOne(fila.id);
  }

  remove(id: string) {
    return this.bitacorasRepo.softDelete(id);
  }

  async removeEvidencia(id: string) {
    const evidencia = await this.evidenciasRepo.findOneBy({ id });
    if (!evidencia) {
      return null;
    }

    if (evidencia.evidencia_url) {
      // 1. Eliminar físicamente del almacenamiento local (Hard Delete de objeto multimedia)
      await this.storageService.eliminarArchivo(evidencia.evidencia_url);
    }

    // 2. Eliminar registro de la DB (Hard Delete)
    return this.evidenciasRepo.delete(id);
  }

}