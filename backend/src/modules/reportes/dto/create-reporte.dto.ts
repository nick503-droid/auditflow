import { IsString, IsOptional, IsNotEmpty, IsDateString } from 'class-validator';

export class CreateReporteDto {
  @IsString()
  @IsNotEmpty()
  usuario_id: string;

  @IsString()
  @IsNotEmpty()
  restaurante_id: string;

  @IsString()
  @IsOptional()
  titulo?: string;

  @IsString()
  @IsOptional()
  notas_finales?: string;
  
  @IsOptional()
  @IsDateString()
  fecha_jornada?: string;
}