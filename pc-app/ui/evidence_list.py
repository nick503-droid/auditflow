"""Reconciliación de tarjetas sin destruir controles que no cambiaron."""
from datetime import datetime, timezone


def clave_orden_evidencia(ev):
    fecha = ev.get("agregado_en")
    if fecha:
        try:
            dt = datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (1, dt.timestamp(), int(ev.get("secuencia_adicion") or ev.get("id") or 0)
                    if str(ev.get("secuencia_adicion") or ev.get("id") or "0").isdigit() else 0,
                    str(ev.get("id") or ""))
        except (ValueError, TypeError, OverflowError):
            pass
    # Compatibilidad: no inventar fechas para evidencias anteriores.
    return (0, ev.get("orden_reproduccion") or 0, str(ev.get("creado_en") or ""),
            str(ev.get("id") or ev.get("evidencia_url") or ev.get("ruta_local") or ""))


def ordenar_evidencias(evidencias):
    return sorted(evidencias or [], key=clave_orden_evidencia)


def firma_evidencias(evidencias):
    """Ignora el orden de la respuesta y metadatos que no afectan a la tarjeta."""
    return tuple(sorted((
        str(ev.get("id") or ""), str(ev.get("evidencia_url") or ""),
        str(ev.get("ruta_local") or ""), str(ev.get("creado_en") or ""),
        str(ev.get("orden_reproduccion") or 0), bool(ev.get("con_audio")),
        str(ev.get("agregado_en") or ""), str(ev.get("secuencia_adicion") or ""),
    ) for ev in (evidencias or [])))


class ListaEvidencias:
    def __init__(self, parent):
        self.parent = parent
        self.parent.grid_columnconfigure(0, weight=1)
        self.tarjetas = {}
        self._vacio = None

    def actualizar(self, items, crear, actualizar=None, vacio=None):
        """items: (clave estable, firma de contenido, datos para renderizar)."""
        claves = {clave for clave, _, _ in items}
        for clave in list(self.tarjetas):
            if clave not in claves:
                self.tarjetas.pop(clave)[0].destroy()
        if items and self._vacio is not None:
            self._vacio.destroy()
            self._vacio = None
        for posicion, (clave, firma, datos) in enumerate(items):
            anterior = self.tarjetas.get(clave)
            if anterior is None or anterior[1] != firma:
                if anterior is not None:
                    anterior[0].destroy()
                tarjeta = crear(datos)
                tarjeta.grid(row=posicion, column=0, sticky="ew", padx=2, pady=3)
            else:
                tarjeta = anterior[0]
                if anterior[2] != datos and actualizar is not None:
                    actualizar(tarjeta, datos)
                if anterior[3] != posicion:
                    tarjeta.grid(row=posicion, column=0, sticky="ew", padx=2, pady=3)
            self.tarjetas[clave] = (tarjeta, firma, datos, posicion)
        if not items and vacio is not None and self._vacio is None:
            self._vacio = vacio()
            self._vacio.grid(row=0, column=0, pady=16)

    def widgets(self):
        return [entry[0] for entry in sorted(self.tarjetas.values(), key=lambda entry: entry[3])]
