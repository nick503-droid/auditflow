import { ConfigService } from '@nestjs/config';
import { readFileSync } from 'fs';
import { SystemController } from './system.controller';

jest.mock('fs', () => ({ readFileSync: jest.fn() }));

describe('Identidad de la imagen desplegada', () => {
  const controller = new SystemController({} as ConfigService);
  const read = jest.mocked(readFileSync);
  const originalCommit = process.env.AUDITFLOW_DEPLOY_COMMIT;

  afterEach(() => {
    if (originalCommit === undefined) delete process.env.AUDITFLOW_DEPLOY_COMMIT;
    else process.env.AUDITFLOW_DEPLOY_COMMIT = originalCommit;
    jest.resetAllMocks();
  });

  it('devuelve el SHA incluido en la imagen incluso sin variable de runtime', () => {
    delete process.env.AUDITFLOW_DEPLOY_COMMIT;
    read.mockReturnValue(JSON.stringify({ commit: 'a'.repeat(40) }));
    expect(controller.deployment()).toEqual({ commit: 'a'.repeat(40) });
  });

  it('no permite falsificar la identidad cambiando la variable de entorno', () => {
    process.env.AUDITFLOW_DEPLOY_COMMIT = 'b'.repeat(40);
    read.mockReturnValue(JSON.stringify({ commit: 'a'.repeat(40) }));
    expect(controller.deployment()).toEqual({ commit: 'a'.repeat(40) });
  });

  it('no considera desplegada una imagen antigua sin metadatos', () => {
    process.env.AUDITFLOW_DEPLOY_COMMIT = 'b'.repeat(40);
    read.mockImplementation(() => { throw new Error('ENOENT'); });
    expect(controller.deployment()).toEqual({ commit: 'development' });
  });

  it.each(['{}', 'null', '{"commit":"development"}', '{"commit":"short"}', 'invalid json'])('rechaza metadatos inválidos: %s', (value) => {
    read.mockReturnValue(value);
    expect(controller.deployment()).toEqual({ commit: 'development' });
  });
});
