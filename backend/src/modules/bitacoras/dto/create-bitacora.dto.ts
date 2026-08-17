import { IsUUID, IsString, IsNotEmpty, IsOptional, IsBoolean, IsDateString, IsEnum } from 'class-validator';
import { NivelUrgencia } from '../entities/bitacora.entity';

export class CreateBitacoraDto {
  @IsUUID()
  restaurante_id: string;

  @IsUUID()
  usuario_id: string;

  @IsString()
  @IsNotEmpty()
  descripcion: string;

  @IsOptional()
  @IsString()
  evidencia_url?: string;

  @IsOptional()
  @IsBoolean()
  con_audio?: boolean;

  @IsDateString()
  fecha: string;

  @IsString()
  @IsNotEmpty()
  hora: string;

  @IsOptional()
  @IsEnum(NivelUrgencia)
  urgencia?: NivelUrgencia;
}