# Verificación de evidencias: Reportes y Bitácoras

Estos cambios son de la app PC. No modifican Android ni el backend y requieren
un ejecutable/paquete PC generado con este código, no la versión anterior.

## Dos PCs conectadas al mismo servidor

1. Abrir el mismo reporte en ambas PCs. Agregar fotografías, un video y un archivo.
2. Comprobar que aparecen automáticamente en la otra PC; el texto debe seguir sincronizándose.
3. Dejar ambas ventanas abiertas entre 30 y 60 minutos, escribiendo de vez en cuando.
   La lista no debe vaciarse, reiniciar sus miniaturas ni parpadear cuando nada cambió.
4. Repetir con una bitácora y su panel de evidencias abierto en ambas PCs.
5. Subir una foto desde Android: confirmar que aumentan los contadores en las dos PCs.
6. Adjuntar varios archivos juntos en Bitácoras. Las tarjetas existentes deben conservarse.
7. Marcar evidencias para descargar y agregar otra desde la segunda PC.
   Las selecciones anteriores deben permanecer marcadas.
8. Eliminar una evidencia y confirmar que desaparece en la otra PC sin reiniciar el resto.
9. Cerrar el editor/panel y volver a abrirlo varias veces. No deben quedar tareas de
   previsualización actualizando widgets de pantallas cerradas.

## Sin conexión y reconexión

1. Desconectar una PC del servidor (no basta con quitar acceso a Internet si la LAN sigue activa).
2. Escribir y adjuntar una captura, video y archivo en Reportes y Bitácoras.
3. Confirmar que quedan visibles como pendientes locales y que un error de red no
   vacía las evidencias remotas que ya se estaban mostrando en Bitácoras.
4. Reconectar: comprobar que la cola se envía automáticamente y aparece en la segunda PC.
5. Confirmar que se limpia la copia administrada por AuditFlow sólo después de
   vincularla correctamente, sin borrar los archivos originales seleccionados por el usuario.

## Si vuelve a quedarse sin responder

La app PC registra excepciones en `%LOCALAPPDATA%\AuditFlow\logs\application.log`.
Si la interfaz deja de responder durante más de 15 segundos, intenta guardar los
stacks de los hilos en `%LOCALAPPDATA%\AuditFlow\logs\hang.log`.
Compartir esos archivos, la versión del título de la ventana y qué acción se realizó.
Los registros tienen tamaño limitado; no contienen capturas ni contenido del reporte.
Un fallo nativo que cierre el proceso inmediatamente puede no alcanzar a generar un stack.

## Validación de desarrollo

```powershell
py -3.10 -B -m unittest discover -s tests -p "test_pc*.py" -v
```

Las pruebas aisladas no usan el servidor, dispositivos de grabación ni la base de
datos del usuario. No sustituyen la prueba prolongada del ejecutable en las PCs reales.
