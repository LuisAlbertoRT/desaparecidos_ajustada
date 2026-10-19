"""Registros detrás de los marcadores `_dloc` y `<actual>-<corte>` del reporte diario.

`deltas_vs_corte` (src/utils.py) CUENTA las altas y las bajas de un
indicador respecto a un corte congelado (25/03/2026 o 01/07/2026, ver
`config.CORTES_REFERENCIA`), y `diferencias_vs_corte` resta los dos totales.
Aquí se recuperan esas mismas filas para entregarlas como base: quien revisa la
baja o la diferencia necesita los registros, no el número.

Vive aparte de src/utils.py a propósito: `src.pipeline.universo` importa
`src.utils`, así que ese archivo entra en la huella de código de las dos capas
del caché (`huella.RAICES`) y editarlo obliga a repetir el matching. Nada del
pipeline importa este módulo: tocarlo no invalida el caché.
"""

from __future__ import annotations

import pandas as pd

import config
from src.pipeline.derivadas import CONSTANTES, NEGACIONES
from src.slices import BASES, Slice
from src.utils import deltas_vs_corte, fubs_corte, normalize_header

# Sufijo de las columnas que vienen del Excel de cada corte. Es otra fuente, con
# sus valores tal como llegan, y el sufijo las separa de las del universo de hoy,
# que ya traen el suyo (`_rnpdno`, `_derivada_*`). En julio no es opcional: ese
# corte salió de este mismo pipeline y sin él su `estatus_loc_derivada_rnpdno`
# chocaría con el de hoy. Un corte nuevo en config.CORTES_REFERENCIA necesita
# su línea aquí.
SUFIJOS_CORTE = {
    **{m: "_25mar26" for m in config.CORTE_25MAR26_FILES},
    **{m: "_01jul26" for m in config.CORTE_01JUL26_FILES},
}


def _sufijo_corte(corte: str) -> str:
    """El sufijo de las columnas de `corte`; falla si el corte no está declarado."""
    if corte not in config.CORTES_REFERENCIA:
        raise KeyError(
            f"'{corte}' no está en config.CORTES_REFERENCIA. "
            f"Disponibles: {sorted(config.CORTES_REFERENCIA)}"
        )
    if corte not in SUFIJOS_CORTE:
        raise KeyError(f"'{corte}' no tiene sufijo de columnas en SUFIJOS_CORTE.")
    return SUFIJOS_CORTE[corte]

_LECTURA_ESTATUS = {"des": "hoy localizados", "loc": "hoy desaparecidos"}


def _fub(valor) -> str | None:
    """El `fub` como lo lee `fubs_corte`: texto sin espacios; vacío → None."""
    if valor is None or pd.isna(valor) or valor == "":
        return None
    return str(valor).strip()


def _condiciones(universo, s: Slice) -> list[tuple[str, Slice, list[str]]]:
    """Cada filtro de `s` por separado: (lectura, rebanada con sólo ese filtro,
    columnas del universo que lo deciden).

    Un registro sale del indicador porque deja de cumplir al menos uno. Se
    resuelven con rebanadas y no comparando columnas a mano para que la regla
    sea exactamente la del rebanado (nulos de fecha, negaciones, constantes).
    """
    frame, pertenencia = BASES[s.base]
    sin_filtros = Slice(frame, "min-max")
    salida = []
    if pertenencia is not None:
        salida.append((f"ya no están en la base {s.base}", Slice(s.base, "min-max"),
                       [pertenencia[0]]))
    if s.periodo != "min-max":
        salida.append((f"con fecha fuera de {s.periodo}", sin_filtros.con(periodo=s.periodo),
                       [universo.columna(frame, "fecha")]))
    if s.estatus != "all":
        salida.append((_LECTURA_ESTATUS[s.estatus], sin_filtros.con(estatus=s.estatus),
                       [universo.columna(frame, "estatus_loc")]))
    if s.subfiltro != "all":
        for token in s.subfiltro.split("_"):
            # `cisf` se guarda como `is_sisf_*` negada; una constante no tiene columna.
            base = NEGACIONES.get(token, token)
            cols = [] if base in CONSTANTES[frame] else [universo.columna_bandera(frame, base)]
            salida.append((f"ya no cumplen {token}", sin_filtros.con(subfiltro=token), cols))
    if s.estado is not None:
        salida.append(("en otra entidad", sin_filtros.con(estado=s.estado),
                       [universo.columna(frame, "cve_ent")]))
    return salida


def _fubs(serie: pd.Series) -> set:
    """Los `fub` de una rebanada como los toma `deltas_vs_corte`."""
    return {f for f in serie.dropna().astype(str).str.strip() if f}


def bajas_vs_corte(universo, s: Slice, corte: str, sufijo: str = "",
                   materializar: bool = False, verbose: bool = True) -> pd.DataFrame:
    """Filas del corte cuyo `fub` hoy ya no está en `s`: el `_dloc` como base.

    Es el cruce de `deltas_vs_corte` —`fub` del corte menos `fub` de la
    rebanada de hoy—, pero devuelve las filas en vez de contarlas. Antes de
    devolverlas se comprueba que sus `fub` distintos sean exactamente el `_dloc`
    que calcula esa función: el archivo respalda un número de la PPT y no se
    entrega si no cuadra con él.

    `corte` es un marcador de `config.CORTES_REFERENCIA`, de donde salen el
    archivo y la columna del `fub`. `sufijo` es el de `deltas_vs_corte`: el
    nombre del marcador no dice contra qué corte se cruzó, así que el de marzo
    va sin sufijo (`_dloc`) y el de julio con `"_v2"` (`_dloc_v2`).

    Columnas:
    - las del Excel del corte, tal como llegan, con el sufijo de su fecha
      (`_25mar26`, `_01jul26`; ver `SUFIJOS_CORTE`). La columna sin encabezado
      se descarta: es el índice con que se guardó el Excel, no un dato;
    - del universo de hoy, `expedientes_rnpdno` y las que deciden si el
      registro pertenece a `s` (estatus, fecha, banderas del subfiltro…),
      cruzadas por `fub`. Quedan vacías cuando el `fub` ya no está en el RNPDNO.

    Con `verbose` imprime cuántas bajas se explican por cada filtro de `s`: es
    la lectura de por qué `_dloc` es una cota superior de las localizaciones.

    `materializar=True` la escribe en `cfg.resultados_dir` como
    `<indicador>_dloc<sufijo>.parquet`, junto a las rebanadas de
    `u.slice(…, materializar=True)`.
    """
    frame = BASES[s.base][0]
    if frame != "rn":
        raise ValueError(
            f"'{s.nombre}': los cortes de referencia se cruzan por `fub`, que sólo "
            f"existe en la base `rn`."
        )
    sufijo_cols = _sufijo_corte(corte)
    ruta, col_id_corte = config.CORTES_REFERENCIA[corte]
    if not ruta.exists():
        raise FileNotFoundError(f"Falta el archivo del corte de referencia: {ruta}")
    marcador = f"{s.nombre}_dloc{sufijo}"

    # El `fub` se lee como texto: leído como número, uno entero junto a una
    # celda vacía llegaría como "123.0" y dejaría de cruzar.
    encabezado = pd.read_excel(ruta, nrows=0).columns
    col_id = normalize_header(col_id_corte)
    col_fub = next((c for c in encabezado if normalize_header(c) == col_id), None)
    if col_fub is None:
        raise KeyError(f"{ruta.name} no trae la columna '{col_id_corte}'. "
                       f"Encabezado: {list(encabezado)}")
    df_corte = pd.read_excel(ruta, dtype={col_fub: str})
    df_corte = df_corte.drop(columns=[c for c in df_corte.columns
                                      if str(c).startswith("Unnamed:")])

    llave = df_corte[col_fub].map(_fub)
    bajas = llave.notna() & ~llave.isin(_fubs(universo.slice(s)["fub_rnpdno"]))
    df_corte, llave = df_corte[bajas], llave[bajas]

    n_dloc = deltas_vs_corte(universo, {s: corte}, sufijo=sufijo, verbose=False)[marcador]
    if llave.nunique() != n_dloc:
        raise AssertionError(
            f"{marcador}: {llave.nunique():,} fub distintos en las filas contra "
            f"{n_dloc:,} del marcador. El cruce ya no es el de deltas_vs_corte."
        )

    condiciones = _condiciones(universo, s)
    # El expediente no decide nada, pero lo lleva toda base exportada con datos
    # del RNPDNO, y el corte de julio no trae el suyo.
    cols_hoy = list(dict.fromkeys(["expedientes_rnpdno",
                                   *(c for _, _, cols in condiciones for c in cols)]))
    rn = universo.rn
    con_fub = rn["fub_rnpdno"].notna().to_numpy()
    fub_rn = rn.loc[con_fub, "fub_rnpdno"].astype(str).str.strip()
    hoy = rn.loc[con_fub, cols_hoy].assign(_llave=fub_rn.to_numpy())
    # Una bandera de un `fub` que ya no está en el RNPDNO queda vacía: con `bool`
    # el cruce la volvería `object`; `boolean` admite el nulo sin cambiar valores.
    hoy = hoy.astype({c: "boolean" for c in cols_hoy if hoy[c].dtype == bool})

    salida = (df_corte.rename(columns=lambda c: f"{c}{sufijo_cols}")
                      .assign(_llave=llave)
                      .merge(hoy, on="_llave", how="left", validate="many_to_one")
                      .drop(columns="_llave"))

    if verbose:
        presentes = llave.isin(set(fub_rn))
        print(f"  ⇣ {marcador}: {len(salida):,} registros de {corte} "
              f"que hoy no están en {s.nombre}")
        print(f"     · {(~presentes).sum():>7,} ya no están en el RNPDNO")
        motivos = pd.DataFrame({
            lectura: presentes & ~llave.isin(_fubs(universo.slice(sub)["fub_rnpdno"]))
            for lectura, sub, _ in condiciones
        })
        for lectura, n in motivos.sum().items():
            print(f"     · {n:>7,} {lectura}")
        varios = (motivos.sum(axis=1) > 1).sum()
        if varios:
            print(f"       ({varios:,} caen en más de un motivo)")

    if materializar:
        universo.cfg.resultados_dir.mkdir(parents=True, exist_ok=True)
        destino = universo.cfg.resultados_dir / f"{marcador}.parquet"
        salida.to_parquet(destino, index=False, engine="pyarrow")
        print(f"  💾 {marcador}: {len(salida):,} registros → {destino.name}")
    return salida


# Columna de la base de una diferencia que dice a qué corriente del saldo
# pertenece cada fila. Se calcula cruzando el universo de hoy contra el corte,
# así que lleva las dos fuentes en el sufijo: la del corte es su fecha
# (`movimiento_derivada_rnpdno_25mar26`). Sus valores son los sufijos
# `_ddes` / `_dloc` del catálogo, en palabras.
def col_movimiento(corte: str) -> str:
    return f"movimiento_derivada_rnpdno{_sufijo_corte(corte)}"


MOVIMIENTO_ALTA = "alta"    # `_ddes`: en el indicador de hoy y no en el corte
MOVIMIENTO_BAJA = "baja"    # `_dloc`: en el corte y no en el indicador de hoy


def movimientos_vs_corte(universo, s: Slice, corte: str, materializar: bool = False,
                         verbose: bool = True) -> pd.DataFrame:
    """Registros detrás del marcador `<s.nombre>-<corte>`: las altas y las bajas juntas.

    El marcador de diferencia resta dos totales, y esa resta es por construcción
    `_ddes − _dloc` (ver `deltas_vs_corte`). Su base son entonces las dos
    corrientes, una fila por registro, con la columna `col_movimiento(corte)`
    (`movimiento_derivada_rnpdno_25mar26` contra marzo):

        alta → está en `s` hoy y NO en el corte    (filas del universo de hoy)
        baja → está en el corte y NO en `s` hoy    (filas de `bajas_vs_corte`)

    de modo que  altas − bajas = el marcador. Antes de devolverla se comprueba que
    cuadre con `u.contar(s)` menos los `fub` del corte, que es la resta que imprime
    la PPT: el archivo respalda ese número y no se entrega si no cuadra con él.

    Las altas traen las columnas de la rebanada de hoy. Las bajas, las mismas que
    su base `_dloc`: las del Excel del corte con el sufijo de su fecha y, del universo
    de hoy, el expediente y las que deciden si el registro pertenece a `s`. Cada
    fila deja vacías las columnas que sólo tiene el otro lado.

    `materializar=True` la escribe en `cfg.resultados_dir` con el nombre del
    marcador, `<indicador>-<corte>.parquet`, junto a las demás bases.
    """
    nombre = f"{s.nombre}-{corte}"
    hoy = universo.slice(s)
    previos, _ = fubs_corte(corte, verbose=False)

    llave = hoy["fub_rnpdno"].map(_fub)
    altas = hoy[llave.notna() & ~llave.isin(previos)]
    bajas = bajas_vs_corte(universo, s, corte, verbose=False)

    # La resta de la PPT es `contar(s)` menos los `fub` distintos del corte
    # (`contar_corte`). Sólo coincide con altas − bajas si cada fila de hoy
    # trae un `fub` propio; si no, la base no explicaría el número.
    n_dloc = len(previos - _fubs(hoy["fub_rnpdno"]))
    n_marcador = universo.contar(s) - len(previos)
    if len(altas) - n_dloc != n_marcador:
        raise AssertionError(
            f"{nombre}: {len(altas):,} altas − {n_dloc:,} bajas = {len(altas) - n_dloc:,}, "
            f"pero el marcador vale {n_marcador:,}. Hay filas de hoy sin `fub` o con "
            f"`fub` repetido, y la base ya no cuadra con la resta."
        )

    # Las banderas de las bajas ya vienen como `boolean` (admiten el vacío de un
    # `fub` que salió del RNPDNO); las de las altas se igualan para que la columna
    # no termine como `object` al concatenar.
    altas = altas.astype({c: "boolean" for c in altas.columns if altas[c].dtype == bool})
    col = col_movimiento(corte)
    salida = pd.concat([altas.assign(**{col: MOVIMIENTO_ALTA}),
                        bajas.assign(**{col: MOVIMIENTO_BAJA})], ignore_index=True)
    salida = salida[[col, *(c for c in salida.columns if c != col)]]

    if verbose:
        print(f"  ± {nombre}: +{len(altas):,} altas − {len(bajas):,} bajas "
              f"= {n_marcador:+,} (cuadra con el marcador)")

    if materializar:
        universo.cfg.resultados_dir.mkdir(parents=True, exist_ok=True)
        destino = universo.cfg.resultados_dir / f"{nombre}.parquet"
        salida.to_parquet(destino, index=False, engine="pyarrow")
        print(f"  💾 {nombre}: {len(salida):,} registros → {destino.name}")
    return salida
