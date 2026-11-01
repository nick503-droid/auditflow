import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { IsNull, MoreThan, MoreThanOrEqual, Repository } from 'typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';
import { StorageService } from '../../common/storage/storage.service';
import { ConfigService } from '@nestjs/config';
import { ordenarAdjuntas, registrarEvidenciaOrdenada } from '../../common/evidence-order';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1, se confunden al leer
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class BitacorasService {
  constructor(
    @InjectRepository(Bitacora)
    private bitacorasRepo: Repository<Bitacora>,
    @InjectRepository(EvidenciaBitacora)
    private evidenciasRepo: Repository<EvidenciaBitacora>,
    private storageService: StorageService,
    private configService: ConfigService,
  ) { }

  async findAll() {
    const rows = await this.bitacorasRepo.find({
      relations: { usuario: true, restaurante: true, evidencias: true },
      order: { fecha: 'DESC', created_at: 'ASC', id: 'ASC' },
    });
    return (rows || []).map(row => ordenarAdjuntas(row)!);
  }

  /**
   * Trae todas las bitácoras de una fecha específica, sin filtrar por
   * usuario ni restaurante — esto es lo que llena la cuadrícula
   * compartida entre todos los videovigilantes.
   */
  async findPorFecha(fecha: string) {
    // Usamos string crudo en lugar de new Date(fecha) para evitar 
    // que la zona horaria atrase el día por accidente.
    const rows = await this.bitacorasRepo.find({
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      where: { fecha: fecha as any },
      relations: { usuario: true, restaurante: true, evidencias: true },
      // La hora del evento es texto libre (p. ej. California). No ordena filas.
      order: { created_at: 'ASC', id: 'ASC' },
    });
    return (rows || []).map(row => ordenarAdjuntas(row)!);
  }

  /**
   * Devuelve SÓLO las bitácoras de una fecha que hayan sido creadas,
   * modificadas o eliminadas (soft-delete) después de `desde`.
   * Se incluyen los registros con deleted_at != NULL para que el cliente
   * pueda retirarlos de la UI sin necesidad de un full-fetch.
   */
  async findDesde(fecha: string, desde: Date) {
    const rows = await this.bitacorasRepo.find({
      withDeleted: true,          // incluir soft-deletes para que el cliente los retire
      where: { fecha: fecha as any, updated_at: MoreThan(desde) },
      relations: { usuario: true, restaurante: true, evidencias: true },
      order: { created_at: 'ASC', id: 'ASC' },
    });
    return (rows || []).map(row => ordenarAdjuntas(row)!);
  }

  async findOne(id: string) {
    return ordenarAdjuntas(await this.bitacorasRepo.findOne({
      where: { id },
      relations: { usuario: true, restaurante: true, evidencias: true },
    }));
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
      order: { agregado_en: 'ASC', secuencia_adicion: 'ASC', creado_en: 'ASC', id: 'ASC' },
    });
  }

  async create(dto: CreateBitacoraDto) {
    const clientId = dto.client_id?.trim() || null;
    if (clientId) {
      const existente = await this.bitacorasRepo.findOne({
        where: { client_id: clientId },
      });
      if (existente) return existente;
    }

    const codigo = await this.generarCodigoUnico();

    // Normalizar campos opcionales: si no vienen, usar valores neutros
    // para que el registro sea válido y el código quede generado de inmediato.
    const nueva = this.bitacorasRepo.create({
      restaurante_id: dto.restaurante_id,
      usuario_id: dto.usuario_id,
      descripcion: dto.descripcion ?? '',
      hora: dto.hora ?? '',
      urgencia: dto.urgencia,
      evidencia_url: dto.evidencia_url,
      con_audio: dto.con_audio,
      client_id: clientId,
      // Pasamos el string de la fecha directamente si existe para evitar desfases de zona horaria
      fecha: dto.fecha ? (dto.fecha) : new Date(),
      codigo,
    });
    try {
      return await this.bitacorasRepo.save(nueva);
    } catch (error) {
      // Dos reintentos pueden llegar simultáneamente y pasar el findOne previo.
      // El índice único decide el ganador; el otro devuelve ese mismo registro.
      const dbError = error as {
        code?: string;
        driverError?: { code?: string };
      };
      if (
        clientId &&
        (dbError.code ?? dbError.driverError?.code) === 'ER_DUP_ENTRY'
      ) {
        const creadoPorOtroIntento = await this.bitacorasRepo.findOne({
          where: { client_id: clientId },
        });
        if (creadoPorOtroIntento) return creadoPorOtroIntento;
      }
      throw error;
    }
  }

  async update(id: string, dto: UpdateBitacoraDto) {
    const bitacora = await this.findOne(id);
    if (!bitacora) return null;
    const { client_id: _clientId, version: _version, ...camposActualizables } = dto;
    // findOne carga restaurante/usuario. Guardar esa entidad con una FK nueva
    // deja dos valores contradictorios y TypeORM prioriza la relación antigua.
    // Actualizar sólo el PATCH evita restaurar el restaurante previo y no
    // reescribe otros campos leídos antes de una edición de otra PC.
    // TypeORM mantiene updated_at/version; no copiar la versión del cliente.
    if (Object.values(camposActualizables).some((valor) => valor !== undefined)) {
      await this.bitacorasRepo.update(id, camposActualizables);
    }
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
   * Agrega una nueva evidencia a la bitácora identificada por `codigo`.
   * El código NO se invalida — se puede reutilizar cuantas veces sea necesario
   * dentro de la ventana de retención de DIAS_VIGENCIA_CODIGO días.
   */
  async adjuntarEvidenciaPorCodigo(
    codigo: string,
    evidencia_url: string,
    con_audio: boolean,
    agregado_en?: string,
  ) {
    const bitacora = await this.findPorCodigo(codigo);
    if (!bitacora) {
      return null;
    }

    // El cliente offline reintenta una vinculación si la respuesta se perdió.
    // La URL del objeto es estable en la cola local, así que reconocerla aquí
    // evita registrar la misma evidencia dos veces.
    const existente = await this.evidenciasRepo.findOne({
      where: { bitacora_id: bitacora.id, evidencia_url },
    });
    if (existente) {
      return this.findOne(bitacora.id);
    }

    // Insertar en la tabla hija — no sobreescribe, agrega una nueva fila
    await registrarEvidenciaOrdenada(this.evidenciasRepo, this.bitacorasRepo, bitacora.id, 'bitacora_id', {
      bitacora_id: bitacora.id,
      evidencia_url,
      con_audio,
    }, agregado_en);

    // El helper toca updated_at del padre en la misma transacción para deltas.
    return this.findOne(bitacora.id);
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
    const resultado = await this.evidenciasRepo.delete(id);

    // Igual que al crearla, la eliminación de una hija debe invalidar el
    // cursor delta de la bitácora padre.
    if (resultado.affected) {
      await this.tocarBitacora(evidencia.bitacora_id);
    }

    return resultado;
  }

  /** Actualiza explícitamente el cursor de sincronización de la bitácora. */
  private async tocarBitacora(bitacoraId: string): Promise<void> {
    await this.bitacorasRepo.update(bitacoraId, { updated_at: new Date() });
  }

  /**
   * Genera un código de 6 caracteres y verifica que no choque con
   * ningún código usado en los últimos DIAS_VIGENCIA_CODIGO días.
   * Si hay colisión (muy raro, pero posible), reintenta.
   */
  private async generarCodigoUnico(): Promise<string> {
    const fechaLimite = new Date();
    fechaLimite.setDate(fechaLimite.getDate() - DIAS_VIGENCIA_CODIGO);

    for (let intento = 0; intento < 10; intento++) {
      const candidato = this.generarCodigoAleatorio();

      const existente = await this.bitacorasRepo.findOne({
        where: {
          codigo: candidato,
          fecha: MoreThanOrEqual(fechaLimite),
        },
      });

      if (!existente) {
        return candidato;
      }
    }

    // Si después de 10 intentos sigue chocando (extremadamente improbable),
    // algo raro está pasando — mejor fallar ruidosamente que devolver un
    // código duplicado
    throw new Error(
      'No se pudo generar un código único después de 10 intentos',
    );
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
