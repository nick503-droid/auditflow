import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  CreateDateColumn,
  DeleteDateColumn,
} from 'typeorm';
import { Bitacora } from './bitacora.entity';

/**
 * Una bitácora puede tener múltiples evidencias (videos o fotos).
 * Se crea una fila aquí cada vez que alguien sube o vincula evidencia
 * usando el código corto de la bitácora — sin límite de cantidad.
 */
@Entity('evidencias_bitacora')
export class EvidenciaBitacora {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @ManyToOne(() => Bitacora, (b) => b.evidencias, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'bitacora_id' })
  bitacora: Bitacora;

  @Column({ name: 'bitacora_id' })
  bitacora_id: string;

  @Column({ type: 'varchar' })
  evidencia_url: string;

  @Column({ type: 'tinyint', default: 0 })
  con_audio: boolean;

  @CreateDateColumn()
  creado_en: Date;

  @DeleteDateColumn()
  deleted_at: Date;
}
