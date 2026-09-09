import { Entity, PrimaryGeneratedColumn, Column, DeleteDateColumn } from 'typeorm';

export enum RolUsuario {
  ADMIN   = 'ADMIN',
  EMPLEADO = 'EMPLEADO',
}

@Entity('usuarios')
export class Usuario {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column({ type: 'varchar' })
  nombre: string;

  @Column({ type: 'varchar', unique: true, nullable: true })
  username: string | null;

  @Column({ type: 'varchar', nullable: true })
  password: string | null;

  @Column({ type: 'enum', enum: RolUsuario, default: RolUsuario.EMPLEADO })
  role: RolUsuario;

  @Column({ type: 'tinyint', default: 1 })
  activo: number;

  @DeleteDateColumn()
  deleted_at: Date;
}
