import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Usuario } from './entities/usuario.entity';
import { CreateUsuarioDto } from './dto/create-usuario.dto';
import { UpdateUsuarioDto } from './dto/update-usuario.dto';
import * as bcrypt from 'bcryptjs';

@Injectable()
export class UsuariosService {
  constructor(
    @InjectRepository(Usuario)
    private usuariosRepo: Repository<Usuario>,
  ) {}

  findAll() {
    return this.usuariosRepo.find({ where: { activo: 1 } });
  }

  findOne(id: string) {
    return this.usuariosRepo.findOneBy({ id });
  }

  findByUsername(username: string) {
    return this.usuariosRepo.findOne({ where: { username } });
  }

  async create(dto: CreateUsuarioDto) {
    const data: Partial<Usuario> = {
      nombre: dto.nombre,
      role: dto.role,
    };

    if (dto.username) {
      data.username = dto.username;
    }
    if (dto.password) {
      data.password = await bcrypt.hash(dto.password, 10);
    }

    const nuevo = this.usuariosRepo.create(data);
    return this.usuariosRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateUsuarioDto) {
    await this.usuariosRepo.update(id, dto);
    return this.findOne(id);
  }

  async changePassword(id: string, newPassword: string) {
    const hash = await bcrypt.hash(newPassword, 10);
    await this.usuariosRepo.update(id, { 
      password: hash, 
      require_password_change: false 
    });
    return { success: true };
  }

  remove(id: string) {
    return this.usuariosRepo.softDelete(id);
  }
}
