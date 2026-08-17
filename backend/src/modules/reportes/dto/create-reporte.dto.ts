import { IsUUID, IsString, IsNotEmpty, IsDateString } from 'class-validator';

export class CreateReporteDto {
  @IsUUID()
  restaurante_id: string;

  @IsUUID()
  usuario_id: string;

  @IsString()
  @IsNotEmpty()
  notas_finales: string;

  @IsDateString()
  fecha_jornada: string;
}