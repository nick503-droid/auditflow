import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Usuario } from './entities/usuario.entity';
import { CreateUsuarioDto } from './dto/create-usuario.dto';
import { UpdateUsuarioDto } from './dto/update-usuario.dto';

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

  create(dto: CreateUsuarioDto) {
    const nuevo = this.usuariosRepo.create(dto);
    return this.usuariosRepo.save(nuevo);
  }

  async update(id: string, dto: UpdateUsuarioDto) {
    await this.usuariosRepo.update(id, dto);
    return this.findOne(id);
  }

  remove(id: string) {
    return this.usuariosRepo.softDelete(id);
  }
}
