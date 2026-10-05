import { BitacorasService } from './bitacoras.service';

describe('BitacorasService', () => {
  let service: BitacorasService;
  let bitacorasRepo: {
    findOne: jest.Mock;
    create: jest.Mock;
    save: jest.Mock;
  };

  beforeEach(() => {
    bitacorasRepo = {
      findOne: jest.fn(),
      create: jest.fn((datos) => datos),
      save: jest.fn(),
    };
    service = new BitacorasService(
      bitacorasRepo as any,
      {} as any,
      {} as any,
      {} as any,
    );
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('returns the existing record when a client retries the same client_id', async () => {
    const existente = { id: 'bitacora-1', codigo: 'ABC123' };
    bitacorasRepo.findOne.mockResolvedValueOnce(existente);

    await expect(
      service.create({
        client_id: 'cfa63b35-4379-423a-b99f-2fa88019b21f',
        restaurante_id: 'restaurante-1',
        usuario_id: 'usuario-1',
      }),
    ).resolves.toBe(existente);

    expect(bitacorasRepo.create).not.toHaveBeenCalled();
    expect(bitacorasRepo.save).not.toHaveBeenCalled();
  });

  it('returns the winning record when two first attempts race on the unique key', async () => {
    const existente = { id: 'bitacora-1', codigo: 'ABC123' };
    bitacorasRepo.findOne
      .mockResolvedValueOnce(null) // lookup by client_id
      .mockResolvedValueOnce(null) // code collision check
      .mockResolvedValueOnce(existente); // lookup after unique-key conflict
    bitacorasRepo.save.mockRejectedValueOnce({
      driverError: { code: 'ER_DUP_ENTRY' },
    });

    await expect(
      service.create({
        client_id: 'cfa63b35-4379-423a-b99f-2fa88019b21f',
        restaurante_id: 'restaurante-1',
        usuario_id: 'usuario-1',
      }),
    ).resolves.toBe(existente);
  });
});
