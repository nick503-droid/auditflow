import { ExceptionFilter, Catch, ArgumentsHost, HttpStatus } from '@nestjs/common';
import { TypeORMError } from 'typeorm';

@Catch(TypeORMError)
export class OptimisticLockFilter implements ExceptionFilter {
  catch(exception: TypeORMError, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse();
    
    // TypeORM lanza OptimisticLockVersionMismatchError cuando la versión enviada
    // no coincide con la versión en la base de datos.
    if (exception.name === 'OptimisticLockVersionMismatchError') {
      response
        .status(HttpStatus.CONFLICT)
        .json({
          statusCode: HttpStatus.CONFLICT,
          message: 'El registro fue modificado por otro usuario (Conflicto de versión).',
          error: 'Conflict',
        });
    } else {
      // Si es otro tipo de error de TypeORM, lo dejamos pasar al filtro global
      // o devolvemos un 500 por defecto.
      response
        .status(HttpStatus.INTERNAL_SERVER_ERROR)
        .json({
          statusCode: HttpStatus.INTERNAL_SERVER_ERROR,
          message: 'Error interno de base de datos.',
          error: exception.name,
        });
    }
  }
}
