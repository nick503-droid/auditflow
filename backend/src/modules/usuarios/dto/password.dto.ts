import { IsString, MinLength, MaxLength } from 'class-validator';

export class PasswordDto {
  @IsString()
  @MinLength(6)
  @MaxLength(72)
  newPassword: string;
}
