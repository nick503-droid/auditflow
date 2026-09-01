import { Controller, Get, Post, Body, Patch, Param, Delete, NotFoundException } from '@nestjs/common';
import { BitacorasService } from './bitacoras.service';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';

@Controller('bitacoras')
export class BitacorasController {
  constructor(private readonly bitacorasService: BitacorasService) {}

  @Post()
  create(@Body() createBitacoraDto: CreateBitacoraDto) {
    return this.bitacorasService.create(createBitacoraDto);
  }

  @Get()
  findAll() {
    return this.bitacorasService.findAll();
  }

  // ── Endpoints con parámetros específicos ANTES de :id ─────────────────────
  // (NestJS resuelve rutas en orden de declaración; si :id va primero,
  //  captura 'fecha' y 'codigo' como UUIDs y las rutas específicas nunca llegan)

  /** Polling de la cuadrícula compartida entre vigilantes. */
  @Get('fecha/:fecha')
  findPorFecha(@Param('fecha') fecha: string) {
    return this.bitacorasService.findPorFecha(fecha);
  }

  /**
   * Cierra todas las bitácoras abiertas de una fecha dada.
   * Llamado por el cliente de escritorio con el botón "Cerrar bitácora del día".
   * Retorna { cerradas: number }.
   */
  @Patch('fecha/:fecha/cerrar')
  cerrarBitacoraDia(@Param('fecha') fecha: string) {
    return this.bitacorasService.cerrarBitacoraDia(fecha);
  }

  /**
   * Devuelve la lista fresca de evidencias de una bitácora por su código corto.
   * Usado por el cliente para cargar evidencias sin esperar el siguiente polling.
   */
  @Get('codigo/:codigo/evidencias')
  async findEvidenciasPorCodigo(@Param('codigo') codigo: string) {
    const evidencias = await this.bitacorasService.findEvidenciasPorCodigo(codigo);
    return evidencias;
  }

  // Endpoint para adjuntar evidencia desde móvil o PC usando el código corto
  @Patch('codigo/:codigo/evidencia')
  async adjuntarEvidencia(
    @Param('codigo') codigo: string,
    @Body('evidencia_url') evidencia_url: string,
    @Body('con_audio') con_audio: boolean,
  ) {
    const bitacoraActualizada = await this.bitacorasService.adjuntarEvidenciaPorCodigo(
      codigo,
      evidencia_url,
      con_audio
    );

    if (!bitacoraActualizada) {
      throw new NotFoundException(`Código ${codigo} no encontrado o expirado.`);
    }

    return bitacoraActualizada;
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.bitacorasService.findOne(id);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() updateBitacoraDto: UpdateBitacoraDto) {
    return this.bitacorasService.update(id, updateBitacoraDto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.bitacorasService.remove(id);
  }

  @Delete('evidencia/:id')
  removeEvidencia(@Param('id') id: string) {
    return this.bitacorasService.removeEvidencia(id);
  }
}