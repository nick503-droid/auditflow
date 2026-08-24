import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThanOrEqual, Repository } from 'typeorm';
import { Reporte } from './entities/reporte.entity';
import { CreateReporteDto } from './dto/create-reporte.dto';
import { UpdateReporteDto } from './dto/update-reporte.dto';

const CARACTERES_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // sin I/O/0/1
const DIAS_VIGENCIA_CODIGO = 5;

@Injectable()
export class ReportesService {
  constructor(
    @InjectRepository(Reporte)
    private reportesRepo: Repository<Reporte>,
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

  // Ahora el método es asíncrono (async) para esperar la generación del código
  async create(dto: CreateReporteDto) {
    const codigo = await this.generarCodigoUnico();
    
    // Asignamos el código recién creado al DTO antes de guardarlo
    const nuevo = this.reportesRepo.create({
      ...dto,
      codigo: codigo
    });
    
    return this.reportesRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateReporteDto) {
    await this.reportesRepo.update(id, dto);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.reportesRepo.softDelete(id);
  }

  private async generarCodigoUnico(): Promise<string> {
    const fechaLimite = new Date();
    fechaLimite.setDate(fechaLimite.getDate() - DIAS_VIGENCIA_CODIGO);

    for (let intento = 0; intento < 10; intento++) {
      const candidato = this.generarCodigoAleatorio();

      // Verifica que este código no exista en reportes recientes
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