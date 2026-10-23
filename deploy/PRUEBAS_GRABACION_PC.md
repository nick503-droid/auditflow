# Grabación de PC: validación después de actualizar el ejecutable

Respaldo anterior a estos cambios: `38c8073`.

## Cambios

- Pantalla completa a resolución nativa, 30 fps, H.264/yuv420p, CRF 20 (antes 15 fps/CRF 28).
- No se amplía artificialmente un video original de baja resolución. La calidad del reproductor/CCTV y la pantalla siguen siendo el límite.
- Con audio: captura loopback de la salida de Windows, normalizada a AAC estéreo/48 kHz/192 kbit/s. Sin audio: no se añade una pista de audio.
- Los tramos de video y audio conservan índices independientes de si recibieron muestras. Un tramo sin muestras lleva silencio, no desplaza el audio siguiente.
- La aplicación se oculta antes del arranque/reanudación. Sólo reaparece cuando video y audio ya dejaron de capturar, antes de procesar los archivos.
- Se intenta excluir temporalmente la ventana principal y el control flotante mediante la API de Windows. La exclusión requiere soporte de Windows/DWM. Si no se puede excluir el flotante, permanece oculto; los atajos siguen disponibles.
- Operaciones de inicio, pausa y reanudación fuera de Tk, con protección contra acciones simultáneas. Detener durante una transición queda en cola.
- Los errores conservan archivos de recuperación en `%USERPROFILE%\AuditFlow_Temp`. No borrar esa carpeta si una grabación falla.

## Prueba manual con los equipos de la empresa

Repetir en **Reportes** y **Bitácoras**, primero **sin audio** y después **con audio**:

1. Reproducir contenido permitido con movimiento y sonido. Iniciar captura.
2. Grabar 10 segundos, pausar, esperar 3 segundos, reanudar. Repetir la pausa y grabar un tercer tramo.
3. Detener con el control flotante o `Ctrl+F8`. Pausar/reanudar también con `Ctrl+K+L`.
4. Verificar que el video se adjunta a la fila/reporte original, que contiene los tres tramos y que los intervalos de pausa no aparecen.
5. Revisar cuadro a cuadro el inicio, las dos uniones y el final: no debe aparecer AuditFlow. Comprobar texto pequeño y fluidez.
6. Con audio, verificar que el segundo y tercer tramo siguen teniendo sonido sincronizado. Sin audio, verificar que no hay pista audible.
7. Repetir con una pausa casi inmediata, varias pulsaciones rápidas y detener mientras se está pausando.
8. Durante la exportación, intentar cambiar de fila o salir: primero debe completarse el adjunto; después se puede salir.
9. Repetir tras cambiar el dispositivo de salida de Windows. Si el dispositivo falla, se debe informar el error y conservar los fragmentos; no publicar silenciosamente una grabación incompleta.

La mayor calidad puede aumentar el tamaño de los archivos. Comparar una grabación de igual duración con la versión anterior y observar CPU/espacio disponible en el equipo menos potente.

## Pruebas automatizadas

Las pruebas no capturan el escritorio ni el audio reales del usuario. Usan FFmpeg real con fuentes de imagen y audio sintéticas, verifican los colores de los tres tramos, duración total, decodificación, conservación de audio y salida Full HD/30 fps. Las pruebas de interfaz comprueban el orden de ocultar/capturar/detener/mostrar, las transiciones y el registro de evidencias. Esto no sustituye la validación de drivers y dispositivos físicos.

Referencia de la exclusión de ventanas: [Microsoft: SetWindowDisplayAffinity](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity).
