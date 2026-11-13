"""Bases que se entregan con la fecha del día en el nombre, en Parquet y en Excel.

`Universo.slice(materializar=True)` escribe `<indicador>.parquet` y lo pisa en cada
corrida: es la base de trabajo. Las que se mandan fuera —p. ej. a la revisión
manual de carpetas— necesitan además una copia por día que no se pise, y en Excel
para quien la revisa:

    reg_rn-no-ba_01jul26-max_des_sfval_08102026.parquet
    reg_rn-no-ba_01jul26-max_des_sfval_08102026.xlsx

Vive aparte de src/utils.py por la misma razón que src/cortes_referencia.py: nada
del pipeline importa este módulo, así que tocarlo no invalida el caché.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.slices import Slice
from src.utils import remove_timezone_for_excel

FECHA_FORMATO = "%d%m%Y"      # 08102026


def exportar_con_fecha(universo, s: Slice, fecha: date | None = None) -> pd.DataFrame:
    """Escribe la rebanada `s` como `<indicador>_<ddmmaaaa>.parquet` y `.xlsx` en
    `cfg.resultados_dir`, junto a las de `materializar=True`.

    La fecha es la de hoy, tomada al llamar y no al importar: un kernel abierto de
    un día para otro seguiría poniendo la de ayer. Es la fecha de la entrega, no la
    del corte de los datos.
    """
    df = universo.slice(s)
    destino = universo.cfg.resultados_dir
    destino.mkdir(parents=True, exist_ok=True)
    nombre = f"{s.nombre}_{(fecha or date.today()).strftime(FECHA_FORMATO)}"
    df.to_parquet(destino / f"{nombre}.parquet", index=False, engine="pyarrow")
    
    # Remove timezone from datetime columns for Excel compatibility
    df_excel = remove_timezone_for_excel(df)
    df_excel.to_excel(destino / f"{nombre}.xlsx", index=False)
    print(f"  💾 {s.nombre}: {len(df):,} registros → {nombre}.parquet / .xlsx")
    return df
