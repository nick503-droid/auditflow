import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  OneToMany,
  DeleteDateColumn,
} from 'typeorm';
import { Usuario } from '../../usuarios/entities/usuario.entity';
import { Restaurante } from '../../restaurantes/entities/restaurante.entity';
import { EvidenciaReporte } from '../../evidencias-reporte/entities/evidencia-reporte.entity';

@Entity('reportes')
export class Reporte {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  // ----------------------------------------------------
  // ¡NUEVAS COLUMNAS! (Añadidas para el nuevo flujo)
  // ----------------------------------------------------
  
  @Column({ type: 'varchar', length: 255, default: 'Reporte de Auditoría' })
  titulo: string;

  @Column({ type: 'varchar', length: 6, default: 'SINCOD' })
  codigo: string;

  // ----------------------------------------------------

  @ManyToOne(() => Restaurante)
  @JoinColumn({ name: 'restaurante_id' })
  restaurante: Restaurante;

  @Column({ name: 'restaurante_id' })
  restaurante_id: string;

  @ManyToOne(() => Usuario)
  @JoinColumn({ name: 'usuario_id' })
  usuario: Usuario;

  @Column({ name: 'usuario_id' })
  usuario_id: string;

  @Column({ type: 'longtext' })
  notas_finales: string;

  @Column({ type: 'date' })
  fecha_jornada: Date;

  // Un reporte -> muchas evidencias. 'reporte' es el nombre del campo
  // inverso que vamos a crear en EvidenciaReporte.
  @OneToMany(() => EvidenciaReporte, (evidencia) => evidencia.reporte)
  evidencias: EvidenciaReporte[];

  @DeleteDateColumn()
  deleted_at: Date;
}