"""Gráficas de una rebanada que se quedó sin registros.

`barras_verticales` y `barras_horizontales` (1_funciones/) truenan con una tabla
de cero filas —"Axis limits cannot be NaN or Inf"— y se llevan con ellas el
resto de la PPT. Pasa cuando un período corto (p. ej. `01ago26-max`) todavía no
tiene registros en alguna rama: `tabulado_dependencia` usa `observed=True` y
devuelve la tabla vacía.

Saltarse la gráfica no basta: el PNG de la corrida anterior sigue en disco y
`PPTReportBuilder` lo insertaría sin avisar, con datos de otro día. Por eso, en
vez de no dibujar, se escribe en ese mismo archivo un aviso con las medidas de
la caja, y la lámina sale con "Sin registros en el período" en su lugar.

Vive aparte de src/utils.py por la misma razón que src/exportacion_fechada.py:
nada del pipeline importa este módulo, así que tocarlo no invalida el caché.
"""

from __future__ import annotations

import functools
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

AVISO = "Sin registros en el período"
_FUENTES = Path(__file__).resolve().parents[1] / "0_fonts"


def sin_registros(tabla: pd.DataFrame) -> bool:
    """True si la tabla no tiene nada que graficar: cero filas o puros ceros.

    Una tabla de ceros no truena, pero dibuja un eje sin barras; el aviso se lee
    mejor y así la regla es la misma para todas las gráficas.
    """
    return tabla.empty or tabla.select_dtypes("number").to_numpy().sum() == 0


def aviso_sin_datos(nombre: str, ancho: float, alto: float, ruta: Path,
                    tipo_letra: str = "Montserrat") -> None:
    """Escribe `<ruta>/<nombre>.png` con el aviso, de `ancho` x `alto` cm.

    Las medidas son las mismas que habría recibido la gráfica: el builder inserta
    la imagen forzando ancho y alto de la caja, y con otra proporción el texto
    saldría deformado. Sólo se escribe el PNG, que es lo que entra en la plantilla;
    el SVG de una corrida anterior, si lo hay, se queda como estaba.
    """
    for fuente in font_manager.findSystemFonts(fontpaths=[_FUENTES]):
        font_manager.fontManager.addfont(fuente)

    fig = plt.figure(figsize=(ancho / 2.54, alto / 2.54), dpi=300)
    fig.text(0.5, 0.5, AVISO, ha="center", va="center",
             fontsize=14, color="#757575", family=tipo_letra)
    ruta.mkdir(parents=True, exist_ok=True)
    # Sin bbox_inches="tight": recortaría la figura al texto y perdería la proporción.
    fig.savefig(ruta / f"{nombre}.png", transparent=True, dpi=300)
    fig.savefig(ruta / f"{nombre}_scour.svg", format="svg", transparent=True)
    plt.close(fig)


def tolerar_sin_datos(funcion, ruta: Path = Path("output")):
    """Envuelve una función de 1_funciones/ para que una tabla sin registros deje
    el aviso en vez de tronar. Con datos, llama a la original sin tocar nada.

    `ruta` debe ser donde `exportar_grafica` escribe (`output/`, relativo al
    directorio de trabajo). Volver a envolver una función ya envuelta envuelve la
    original, así que re-ejecutar la celda no apila envolturas.
    """
    original = getattr(funcion, "__wrapped__", funcion)

    @functools.wraps(original)
    def envoltura(df, *args, **kwargs):
        if sin_registros(df):
            # Las llamadas del cuaderno pasan todo por nombre; 20 x 12 cm es la
            # caja de las `gr_ent_*`, por si alguna no trae medidas.
            nombre = kwargs.get("nombre", original.__name__)
            print(f"  ⚠️ {nombre}: sin registros; se deja el aviso en su lugar")
            aviso_sin_datos(nombre, kwargs.get("ancho") or 20, kwargs.get("alto") or 12,
                            ruta, tipo_letra=kwargs.get("tipo_letra", "Montserrat"))
            return None
        return original(df, *args, **kwargs)

    return envoltura
