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

  // Endpoint para el polling de la cuadrícula
  @Get('fecha/:fecha')
  findPorFecha(@Param('fecha') fecha: string) {
    return this.bitacorasService.findPorFecha(fecha);
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.bitacorasService.findOne(id);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() updateBitacoraDto: UpdateBitacoraDto) {
    return this.bitacorasService.update(id, updateBitacoraDto);
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

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.bitacorasService.remove(id);
  }
}