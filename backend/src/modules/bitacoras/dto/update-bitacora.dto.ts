import { PartialType } from '@nestjs/mapped-types';
import { CreateBitacoraDto } from './create-bitacora.dto';

import { IsOptional, IsNumber } from 'class-validator';

export class UpdateBitacoraDto extends PartialType(CreateBitacoraDto) {
  @IsOptional()
  @IsNumber()
  version?: number;
}
