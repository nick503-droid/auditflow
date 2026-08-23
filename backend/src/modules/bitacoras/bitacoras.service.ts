import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { IsNull, MoreThanOrEqual, Repository } from 'typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { EvidenciaBitacora } from './entities/evidencia-bitacora.entity';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1, se confunden al leer
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class BitacorasService {
  constructor(
    @InjectRepository(Bitacora)
    private bitacorasRepo: Repository<Bitacora>,
    @InjectRepository(EvidenciaBitacora)
    private evidenciasRepo: Repository<EvidenciaBitacora>,
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
    const codigo = await this.generarCodigoUnico();

    // Normalizar campos opcionales: si no vienen, usar valores neutros
    // para que el registro sea válido y el código quede generado de inmediato.
    const nueva = this.bitacorasRepo.create({
      descripcion: '',
      hora: '',
      ...dto,
      // Pasamos el string de la fecha directamente si existe para evitar desfases de zona horaria
      fecha: dto.fecha ? (dto.fecha) : new Date(),
      codigo,
    });
    return this.bitacorasRepo.save(nueva);
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
   * Agrega una nueva evidencia a la bitácora identificada por `codigo`.
   * El código NO se invalida — se puede reutilizar cuantas veces sea necesario
   * dentro de la ventana de retención de DIAS_VIGENCIA_CODIGO días.
   */
  async adjuntarEvidenciaPorCodigo(
    codigo: string,
    evidencia_url: string,
    con_audio: boolean,
  ) {
    const bitacora = await this.findPorCodigo(codigo);
    if (!bitacora) {
      return null;
    }

    // Insertar en la tabla hija — no sobreescribe, agrega una nueva fila
    const nueva = this.evidenciasRepo.create({
      bitacora_id: bitacora.id,
      evidencia_url,
      con_audio,
    });
    await this.evidenciasRepo.save(nueva);

    return this.findOne(bitacora.id);
  }

  remove(id: string) {
    return this.bitacorasRepo.softDelete(id);
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