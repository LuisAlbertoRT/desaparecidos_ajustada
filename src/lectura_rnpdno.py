"""Lectura del archivo del RNPDNO, venga en Parquet o en Excel.

El RNPDNO llega en dos presentaciones con el mismo contenido (ver
`config.RNPDNO_FORMATOS`), y el formato se reconoce por la extensión:

    Parquet  Una tabla con las tres hojas apiladas. No guarda de qué hoja vino cada
             fila, así que se reconstruye con `estatus` + `conidentidad`.
    Excel    El libro con las tres hojas de `config.SHEET_NAMES`. La hoja de cada
             fila es la hoja de la que se leyó.

`leer_rnpdno` devuelve lo mismo en los dos casos, para que el notebook 1 no tenga que
distinguir de dónde vino a partir de ahí:

    tabla        Una sola tabla con los nombres de columna del Parquet (el Excel, y el
                 Parquet que llegue con otra variante, se renombran con
                 `config.RNPDNO_EXCEL_A_PARQUET`), todo como texto y los faltantes
                 como nulo.
    hoja_origen  Para cada fila, la llave de `config.SHEET_NAMES` de la que viene:
                 PENDIENTES, LOCALIZADAS o DESAPARECIDAS.

Lo único que no se iguala es cómo vienen escritos algunos números: el Parquet trae
"5.0" en `idmunicipio` donde el Excel tiene un 5. La copia `_rnpdno` conserva cada uno
tal como vino; la columna de trabajo y las derivadas pasan a número y quedan iguales.

Sólo lo importa el notebook 1: está fuera del cierre de código de la huella del caché
(`src/pipeline/huella.py`), así que editarlo no invalida el matching.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from pandas._libs.parsers import STR_NA_VALUES

import config


def leer_rnpdno(ruta, verbose: bool = True) -> tuple[pd.DataFrame, pd.Series]:
    """La tabla del RNPDNO y la hoja de cada fila, sea cual sea el formato del archivo."""
    ruta = Path(ruta)
    if config.formato_rnpdno(ruta) == "parquet":
        tabla, hoja_origen = _leer_parquet(ruta)
    else:
        tabla, hoja_origen = _leer_excel(ruta, verbose=verbose)

    sin_clasificar = len(tabla) - hoja_origen.isin(list(config.SHEET_NAMES)).sum()
    if sin_clasificar:
        raise ValueError(f"❌ Error crítico: {sin_clasificar} filas no cayeron en ninguna hoja.")
    return tabla, hoja_origen


def _nombres_del_parquet(df: pd.DataFrame, origen: str) -> pd.DataFrame:
    """Renombra a su nombre del Parquet las columnas que cambian de nombre según la entrega.

    El RNPDNO no siempre escribe igual la misma columna: el Excel trae `curp_victima` y
    `expediente`, y los Parquet han llegado con `expediente`, `Expediente` o
    `Expedientes` según el corte. Se compara sin distinguir mayúsculas contra
    `config.RNPDNO_EXCEL_A_PARQUET` (y contra el nombre destino), para que la copia
    `_rnpdno` se llame igual venga de donde venga. Sólo cambia el nombre.
    """
    destino = {v.lower(): v for v in config.RNPDNO_EXCEL_A_PARQUET.values()}
    destino |= {k.lower(): v for k, v in config.RNPDNO_EXCEL_A_PARQUET.items()}
    df = df.rename(columns=lambda c: destino.get(c.strip().lower(), c) if isinstance(c, str) else c)
    repetidas = df.columns[df.columns.duplicated()].tolist()
    if repetidas:
        raise ValueError(
            f"❌ Error crítico: {origen} queda con columnas repetidas {repetidas} al "
            "renombrarla con config.RNPDNO_EXCEL_A_PARQUET.")
    return df


def _leer_parquet(ruta: Path) -> tuple[pd.DataFrame, pd.Series]:
    tabla = _nombres_del_parquet(pd.read_parquet(ruta), f"el Parquet {ruta.name!r}")

    # El Parquet marca los faltantes con cadena vacía y conserva literales como "N/A";
    # `read_excel` los convierte en NaN. Se replica aquí ese mismo criterio para que el
    # notebook vea los mismos nulos que leyendo el Excel (de lo contrario `dropna`, la
    # validación de CURP y la deduplicación tratan el "" o el "N/A" como un valor
    # real). STR_NA_VALUES es la lista que pandas usa por defecto al leer archivos:
    # '', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan',
    # '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'None', 'n/a', 'nan', 'null'
    tabla = tabla.replace(list(STR_NA_VALUES), pd.NA)

    # El Parquet no guarda de qué hoja vino cada fila; `estatus` + `conidentidad`
    # la reconstruyen (ver RNPDNO_ESTATUS_LOCALIZADAS en config.py).
    faltantes = [c for c in ("estatus", "conidentidad") if c not in tabla.columns]
    if faltantes:
        raise ValueError(f"❌ Error crítico: el Parquet no trae {faltantes}, "
                         "necesarias para separar las hojas.")

    es_localizada = tabla["estatus"].isin(config.RNPDNO_ESTATUS_LOCALIZADAS)
    con_identidad = tabla["conidentidad"].astype(str).str.strip().str.lower() == "true"

    hoja_origen = pd.Series("PENDIENTES", index=tabla.index)
    hoja_origen[con_identidad] = "DESAPARECIDAS"
    hoja_origen[es_localizada] = "LOCALIZADAS"   # el estatus manda sobre conidentidad
    return tabla, hoja_origen


def _leer_excel(ruta: Path, verbose: bool = True) -> tuple[pd.DataFrame, pd.Series]:
    hojas = []
    with pd.ExcelFile(ruta) as xls:
        faltantes = [h for h in config.SHEET_NAMES.values() if h not in xls.sheet_names]
        if faltantes:
            raise ValueError(
                f"❌ Error crítico: Faltan hojas obligatorias en el archivo Excel: {faltantes}")

        for key, nombre_hoja in config.SHEET_NAMES.items():
            if verbose:
                print(f"  📖 Leyendo hoja {nombre_hoja}...")
            # Todo como texto, igual que el Parquet. `read_excel` ya deja como nulo las
            # celdas vacías y los literales de STR_NA_VALUES: el mismo criterio que se
            # le aplica al Parquet en `_leer_parquet`.
            df = pd.read_excel(xls, sheet_name=nombre_hoja, dtype=str)
            df = _nombres_del_parquet(df, f"la hoja {nombre_hoja!r}")
            hojas.append((key, df))

    tabla = pd.concat([df for _, df in hojas], ignore_index=True)
    hoja_origen = pd.Series(
        np.repeat([key for key, _ in hojas], [len(df) for _, df in hojas]), index=tabla.index)
    return tabla, hoja_origen
