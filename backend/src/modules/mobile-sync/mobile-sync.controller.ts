import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  UseInterceptors,
  UploadedFile,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { MobileSyncService } from './mobile-sync.service';
import { StorageService } from '../../common/storage/storage.service';

@Controller('mobile-sync')
export class MobileSyncController {
  constructor(
    private readonly mobileSyncService: MobileSyncService,
    private readonly storageService: StorageService,
  ) {}

  @Get('validate/:codigo')
  validar(@Param('codigo') codigo: string) {
    if (!codigo || codigo.length !== 6) {
      throw new BadRequestException('El código debe tener 6 caracteres.');
    }
    return this.mobileSyncService.validarCodigo(codigo);
  }

  @Post('link/:codigo')
  @UseInterceptors(FileInterceptor('file'))
  async vincular(
    @Param('codigo') codigo: string,
    @UploadedFile() file: Express.Multer.File,
    @Body('con_audio') conAudioStr?: string,
  ) {
    if (!file) {
      throw new BadRequestException('Se requiere un archivo.');
    }

    const conAudio = conAudioStr === 'true';

    // 1. Guardar temporalmente
    const nombreTemp = await this.storageService.guardarEnTemp(
      file.buffer,
      file.originalname,
    );

    // 2. Intentar vinculación y movimiento
    try {
      const resultado = await this.mobileSyncService.vincularEvidencia(
        codigo,
        nombreTemp,
        conAudio,
      );
      return resultado;
    } catch (error) {
      // Si falló por cualquier motivo, nos aseguramos de que el archivo temporal también se borre 
      // (si es que no alcanzó a moverse o si el servicio no lo hizo).
      await this.storageService.eliminarDeTemp(nombreTemp);
      throw error;
    }
  }
}
