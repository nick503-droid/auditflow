import {
  Controller,
  Get,
  Post,
  Body,
  UnauthorizedException,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { AuthService } from './auth.service';
import { IsString, IsNotEmpty } from 'class-validator';

class LoginDto {
  @IsString()
  @IsNotEmpty()
  username: string;

  @IsString()
  @IsNotEmpty()
  password: string;
}

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Post('login')
  @HttpCode(HttpStatus.OK)
  async login(@Body() dto: LoginDto) {
    try {
      return await this.authService.login(dto.username, dto.password);
    } catch (error) {
      // No filtramos si es "usuario no existe" vs "contraseña incorrecta"
      // para no dar pistas de enumeración de usuarios
      throw new UnauthorizedException('Usuario o contraseña incorrectos');
    }
  }

  /** Directorio mínimo que las PC guardan para validar accesos sin red. */
  @Get('offline-directory')
  offlineDirectory() {
    return this.authService.directorioOffline();
  }
}
