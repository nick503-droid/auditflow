import { Test, TestingModule } from '@nestjs/testing';
import { BitacorasController } from './bitacoras.controller';
import { BitacorasService } from './bitacoras.service';

describe('BitacorasController', () => {
  let controller: BitacorasController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [BitacorasController],
      providers: [BitacorasService],
    }).compile();

    controller = module.get<BitacorasController>(BitacorasController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });
});
