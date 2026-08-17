import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  ManyToOne,
  JoinColumn,
  DeleteDateColumn,
} from 'typeorm';
import { Reporte } from '../../reportes/entities/reporte.entity';

@Entity('evidencias_reporte')
export class EvidenciaReporte {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  // Lado "muchos" de la relación: aquí SÍ existe la columna FK real
  @ManyToOne(() => Reporte, (reporte) => reporte.evidencias)
  @JoinColumn({ name: 'reporte_id' })
  reporte: Reporte;

  @Column({ name: 'reporte_id' })
  reporte_id: string;

  @Column({ type: 'varchar' })
  evidencia_url: string;

  @Column({ type: 'tinyint', default: 0 })
  con_audio: boolean;

  @Column({ type: 'int' })
  orden_reproduccion: number;

  @DeleteDateColumn()
  deleted_at: Date;
}
