// bitacoras.controller.ts
import { Controller, Get, Post, Body, Param, Patch, Delete } from '@nestjs/common';
import { BitacorasService } from './bitacoras.service';
import { CreateBitacoraDto } from './dto/create-bitacora.dto';
import { UpdateBitacoraDto } from './dto/update-bitacora.dto';

@Controller('bitacoras')
export class BitacorasController {
  constructor(private readonly bitacorasService: BitacorasService) {}

  @Get()
  findAll() {
    return this.bitacorasService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.bitacorasService.findOne(id);
  }

  @Post()
  create(@Body() dto: CreateBitacoraDto) {
    return this.bitacorasService.create(dto);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateBitacoraDto) {
    return this.bitacorasService.update(id, dto);
  }

  @Patch(':id/evidencia')
  adjuntarEvidencia(
    @Param('id') id: string,
    @Body('evidencia_url') evidencia_url: string,
    @Body('con_audio') con_audio: boolean,
  ) {
    return this.bitacorasService.adjuntarEvidencia(id, evidencia_url, con_audio);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.bitacorasService.remove(id);
  }
}