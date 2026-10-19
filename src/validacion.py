"""Lectura de insumos con validación estricta.

Regla única: **si algo falta, el proceso se detiene con un mensaje que dice qué
falta y dónde**. No hay autodetección, ni "el archivo más reciente", ni columnas
opcionales que se rellenan solas. Un insumo mal declarado tiene que fallar en la
primera celda, no producir un resultado silenciosamente distinto.

Las rutas y los mapeos de columnas se declaran en `config.py`, junto a los de
RNPDNO y BANCI. Aquí sólo está el mecanismo que los hace cumplir.

Uso típico:

    from src.validacion import leer_excel, leer_csv, leer_parquet
    import config

    df = leer_excel(config.PUI_REGISTROS_FILE,
                    config.PUI_REGISTROS_COLUMN_MAPPING,
                    hoja=config.PUI_REGISTROS_SHEET,
                    descripcion="confrontas manuales (registros)")

El DataFrame vuelve con las columnas **renombradas al nombre interno** del mapeo,
de modo que el resto del cuaderno no tiene que saber qué alias traía el archivo.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping, Optional, Union

import pandas as pd


class InsumoInvalido(Exception):
    """Un insumo no existe, le falta una hoja o le falta una columna exigida."""


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de nombres de columna
# ─────────────────────────────────────────────────────────────────────────────
def _norm(nombre: object) -> str:
    """Clave de comparación: sin acentos, sin separadores, en minúsculas.

    `"Fecha Hechos"`, `"fecha_hechos"` y `"FECHA.HECHOS"` colapsan al mismo valor,
    que es lo que permite que los alias del mapeo funcionen con archivos que
    cambian de mayúsculas o de separador entre entregas.
    """
    txt = unicodedata.normalize("NFD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s._\-]+", "", txt).lower().strip()


# ─────────────────────────────────────────────────────────────────────────────
# Validaciones
# ─────────────────────────────────────────────────────────────────────────────
def exigir_archivo(ruta: Union[str, Path], descripcion: str = "insumo") -> Path:
    """Detiene el proceso si el archivo no existe."""
    if ruta is None:
        raise InsumoInvalido(
            f"❌ No se declaró la ruta de {descripcion}.\n"
            f"   Declárala en config.py."
        )
    p = Path(ruta)
    if not p.exists():
        cercanos = ""
        if p.parent.exists():
            hermanos = sorted(x.name for x in p.parent.iterdir() if x.is_file())[:10]
            if hermanos:
                cercanos = ("\n   En esa carpeta hay:\n"
                            + "\n".join(f"     - {h}" for h in hermanos))
        raise InsumoInvalido(
            f"❌ No se encontró {descripcion}.\n"
            f"   Ruta declarada en config.py: {p}{cercanos}"
        )
    if not p.is_file():
        raise InsumoInvalido(f"❌ {descripcion} no es un archivo: {p}")
    return p


def exigir_hoja(ruta: Union[str, Path], hoja: Union[int, str],
                descripcion: str = "insumo") -> Union[int, str]:
    """Detiene el proceso si el Excel no tiene la hoja pedida."""
    p = Path(ruta)
    try:
        disponibles = pd.ExcelFile(p).sheet_names
    except Exception as e:                                    # archivo ilegible
        raise InsumoInvalido(f"❌ No se pudo abrir {descripcion} ({p}): {e}") from e

    if isinstance(hoja, int):
        if hoja >= len(disponibles):
            raise InsumoInvalido(
                f"❌ {descripcion} no tiene la hoja número {hoja}.\n"
                f"   Archivo: {p}\n"
                f"   Hojas disponibles ({len(disponibles)}): {disponibles}"
            )
    elif hoja not in disponibles:
        raise InsumoInvalido(
            f"❌ {descripcion} no tiene la hoja '{hoja}'.\n"
            f"   Archivo: {p}\n"
            f"   Hojas disponibles: {disponibles}"
        )
    return hoja


def resolver_columnas(df: pd.DataFrame, mapeo: Mapping[str, Iterable[str]],
                      descripcion: str = "insumo",
                      ruta: Optional[Union[str, Path]] = None) -> dict:
    """Devuelve {nombre_interno: columna_real}, o se detiene si falta alguna.

    Cada entrada del mapeo se da por satisfecha con el PRIMER alias presente en el
    archivo. Si ninguno aparece, el error dice qué se buscaba y qué hay.
    """
    presentes = {_norm(c): c for c in df.columns}
    resuelto, faltantes = {}, {}

    for interno, alias in mapeo.items():
        alias = [alias] if isinstance(alias, str) else list(alias)
        hallado = next((presentes[_norm(a)] for a in alias if _norm(a) in presentes), None)
        if hallado is None:
            faltantes[interno] = alias
        else:
            resuelto[interno] = hallado

    if faltantes:
        detalle = "\n".join(
            f"     - {interno}: se buscó {alias}" for interno, alias in faltantes.items()
        )
        raise InsumoInvalido(
            f"❌ A {descripcion} le faltan {len(faltantes)} columna(s) exigida(s).\n"
            + (f"   Archivo: {ruta}\n" if ruta else "")
            + f"{detalle}\n"
            f"   El archivo trae estas columnas ({len(df.columns)}):\n"
            f"     {list(df.columns)}\n"
            f"   Si el archivo cambió de nombres, actualiza el mapeo en config.py."
        )
    return resuelto


# ─────────────────────────────────────────────────────────────────────────────
# Lectores
# ─────────────────────────────────────────────────────────────────────────────
def _aplicar(df: pd.DataFrame, mapeo, descripcion, ruta, solo_mapeadas: bool):
    if not mapeo:
        return df
    resuelto = resolver_columnas(df, mapeo, descripcion, ruta)
    df = df.rename(columns={real: interno for interno, real in resuelto.items()})
    return df[list(resuelto)] if solo_mapeadas else df


def leer_excel(ruta, mapeo=None, hoja: Union[int, str] = 0, descripcion="insumo",
               solo_mapeadas: bool = True, skiprows: int = 0, **kwargs) -> pd.DataFrame:
    """Lee un Excel exigiendo archivo, hoja y columnas."""
    p = exigir_archivo(ruta, descripcion)
    exigir_hoja(p, hoja, descripcion)
    df = pd.read_excel(p, sheet_name=hoja, skiprows=skiprows, **kwargs)
    return _aplicar(df, mapeo, descripcion, p, solo_mapeadas)


def leer_csv(ruta, mapeo=None, descripcion="insumo", solo_mapeadas: bool = True,
             encodings: tuple = ("utf-8-sig", "latin1"), **kwargs) -> pd.DataFrame:
    """Lee un CSV exigiendo archivo y columnas.

    Prueba los encodings en orden (réplica de `leer_csv_pui` del script de R, que
    intenta UTF-8 y cae a Latin-1). Si todos fallan, se detiene.
    """
    p = exigir_archivo(ruta, descripcion)
    ultimo = None
    for enc in encodings:
        try:
            df = pd.read_csv(p, encoding=enc, **kwargs)
            break
        except UnicodeDecodeError as e:
            ultimo = e
    else:
        raise InsumoInvalido(
            f"❌ No se pudo leer {descripcion} con ninguno de los encodings "
            f"{encodings}.\n   Archivo: {p}\n   Último error: {ultimo}"
        )
    return _aplicar(df, mapeo, descripcion, p, solo_mapeadas)


def leer_parquet(ruta, mapeo=None, descripcion="insumo",
                 solo_mapeadas: bool = True) -> pd.DataFrame:
    """Lee un Parquet exigiendo archivo y columnas.

    Valida contra el esquema ANTES de cargar, para no traer a memoria un archivo
    grande que de todas formas va a fallar.
    """
    import pyarrow.parquet as pq

    p = exigir_archivo(ruta, descripcion)
    nombres = pq.read_schema(p).names
    if mapeo:
        vacio = pd.DataFrame(columns=nombres)
        resuelto = resolver_columnas(vacio, mapeo, descripcion, p)
        df = pd.read_parquet(p, columns=list(resuelto.values()))
        df = df.rename(columns={real: interno for interno, real in resuelto.items()})
        return df[list(resuelto)] if solo_mapeadas else df
    return pd.read_parquet(p)
