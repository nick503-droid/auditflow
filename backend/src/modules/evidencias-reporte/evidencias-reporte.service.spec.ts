import { Test, TestingModule } from '@nestjs/testing';
import { EvidenciasReporteService } from './evidencias-reporte.service';

describe('EvidenciasReporteService', () => {
  let service: EvidenciasReporteService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [EvidenciasReporteService],
    }).compile();

    service = module.get<EvidenciasReporteService>(EvidenciasReporteService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
