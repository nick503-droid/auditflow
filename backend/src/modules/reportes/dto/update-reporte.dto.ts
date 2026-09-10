import { PartialType } from '@nestjs/mapped-types';
import { CreateReporteDto } from './create-reporte.dto';

import { IsOptional, IsNumber } from 'class-validator';

export class UpdateReporteDto extends PartialType(CreateReporteDto) {
  @IsOptional()
  @IsNumber()
  version?: number;
}
