import { Test, TestingModule } from '@nestjs/testing';
import { EvidenciasReporteController } from './evidencias-reporte.controller';
import { EvidenciasReporteService } from './evidencias-reporte.service';

describe('EvidenciasReporteController', () => {
  let controller: EvidenciasReporteController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [EvidenciasReporteController],
      providers: [EvidenciasReporteService],
    }).compile();

    controller = module.get<EvidenciasReporteController>(EvidenciasReporteController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });
});
