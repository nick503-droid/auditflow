import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { Bitacora } from './entities/bitacora.entity';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1, se confunden al leer
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class BitacorasService {
  constructor(
    @InjectRepository(Bitacora)
    private bitacorasRepo: Repository<Bitacora>,
  ) {}

  findAll() {
    return this.bitacorasRepo.find({
      relations: { usuario: true, restaurante: true },
      order: { fecha: 'DESC', hora: 'DESC' },
    });
  }

  /**
   * Trae todas las bitácoras de una fecha específica, sin filtrar por
   * usuario ni restaurante — esto es lo que llena la cuadrícula
   * compartida entre todos los videovigilantes.
   */
  findPorFecha(fecha: string) {
    return this.bitacorasRepo.find({
      where: { fecha: new Date(fecha) },
      relations: { usuario: true, restaurante: true },
      order: { hora: 'ASC' },
    });
  }

  findOne(id: string) {
    return this.bitacorasRepo.findOne({
      where: { id },
      relations: { usuario: true, restaurante: true },
    });
  }

  findPorCodigo(codigo: string) {
    return this.bitacorasRepo.findOne({
      where: { codigo: codigo.toUpperCase() },
      order: { fecha: 'DESC' }, // si hay colisión de código viejo, toma la más reciente
    });
  }

  async create(dto: CreateBitacoraDto) {
    const codigo = await this.generarCodigoUnico();

    const nueva = this.bitacorasRepo.create({
      ...dto,
      codigo,
    });
    return this.bitacorasRepo.save(nueva);
  }

  async update(id: string, dto: UpdateBitacoraDto) {
    await this.bitacorasRepo.update(id, dto);
    return this.findOne(id);
  }

  async adjuntarEvidenciaPorCodigo(codigo: string, evidencia_url: string, con_audio: boolean) {
    const bitacora = await this.findPorCodigo(codigo);
    if (!bitacora) {
      return null;
    }
    await this.bitacorasRepo.update(bitacora.id, { evidencia_url, con_audio });
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
    throw new Error('No se pudo generar un código único después de 10 intentos');
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