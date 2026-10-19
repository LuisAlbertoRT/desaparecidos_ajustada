"""CAPA C · Exportación de las bases de origen con llave de cruce.

Devuelve BANCI y RNPDNO **idénticos a sus archivos de origen** —mismas filas, en
el mismo orden; mismas columnas, con el mismo nombre; mismo formato y mismo nombre
de archivo— con un bloque de columnas nuevas al final:

    id_cruce            la llave que aparea las dos bases
    metodo_match, …     cómo se decidió ese apareamiento

POR QUÉ LA LLAVE ES EL FUB Y NO UN IDENTIFICADOR NUEVO
------------------------------------------------------
`id_cruce` es el FUB del RNPDNO. Es estable entre cortes, es legible y cualquiera
puede verificar un par a ojo. Inventar un identificador opaco es justo el error
que ya costó caro aquí: el `id_registro` sha1 del SESNSP no se podía reproducir y
cruzar por él daba cero, así que 561 confirmaciones humanas nunca se aplicaban
(ver docs/3_metodologia_de_matching.md §3.3).

La relación es **N:1**: varias carpetas de BANCI pueden apuntar a la misma
persona. Del lado del RNPDNO va `n_registros_banci` para que nadie multiplique
filas sin darse cuenta al hacer el cruce.

POR QUÉ HACE FALTA `id_registro_banci`
--------------------------------------
BANCI no tiene llave única: 34,777 filas contra 31,744 valores distintos de
`LLAVE` (carpetas colectivas, varias víctimas en un mismo expediente). Cruzar por
`LLAVE` duplicaría filas. `id_registro_banci` = carpeta + ordinal de la víctima
dentro de la carpeta, en el orden del archivo, y se puede regenerar desde el
Excel de origen sin correr el pipeline: ésa es la propiedad que hace confiable a
una llave.

CADA BASE SALE EN EL FORMATO EN QUE ENTRÓ
-----------------------------------------
BANCI es un Excel y sale como Excel: se reescribe hoja por hoja y se compara celda
por celda. El RNPDNO (`config.RNPDNO_MANUAL_FILE_2`) puede llegar de dos formas
(`config.formato_rnpdno`), y en las dos las columnas nuevas se aparean por FUB:

- Parquet → Parquet: se lee la tabla, se le pegan las columnas y se reescribe.
- Excel → Excel: las tres hojas se reescriben como las de BANCI, cada una con el
  bloque de columnas al final.

QUÉ SE CONSERVA Y QUÉ NO
------------------------
Se conservan filas, columnas, orden, valores y tipos (las fechas siguen siendo
fechas; en el Parquet los dtypes viajan intactos, sin el redondeo de flotantes que
mete la reescritura de Excel). En los Excel NO se conservan estilos, anchos de
columna ni objetos de tabla dinámica: una reescritura no los mantiene. Decisión
tomada: aquí importan los valores, no el formato.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
import openpyxl
import pandas as pd

import config
from src.settings import Settings

if TYPE_CHECKING:
    from src.pipeline.universo import Universo

# ─────────────────────────────────────────────────────────────────────────────
# Contrato de columnas nuevas. El orden de estas listas es el orden en que
# aparecen en el archivo exportado, y la validación exige que sea exactamente
# éste: si alguien agrega o mueve una columna a mano, la validación lo delata.
# ─────────────────────────────────────────────────────────────────────────────
COLUMNAS_BANCI: tuple[str, ...] = (
    "id_registro_banci",         # identidad de la fila (carpeta + ordinal de víctima)
    "fila_origen_banci",         # renglón físico en la hoja de origen (ancla de auditoría)
    "id_cruce",                  # ← LA LLAVE. FUB pareado; vacío si no hubo match
    "estatus_match",             # con_cruce | candidato_revision_manual | sin_cruce
    "metodo_match",              # manual | estandar | refinado (ganador de la cascada)
    "submetodo_match",           # match_fub | match_curp | match_nombre | definitivo | …
    "nivel_match",               # 1 | 2 | 3 — sólo el embudo del motor estándar
    "metodos_concurrentes",      # todos los motores que sostienen ese FUB
    "fub_candidato_revision",    # FUB propuesto por el refinado y NO confirmado
    "fubs_adicionales_manual",   # otros FUB que esta misma revisión validó
    "score_match",
    "evidencia_match",           # variables que sostuvieron el match
    "corte_match",
    "version_match",             # cfg.clave_matching: identifica la corrida exacta
)

COLUMNAS_RNPDNO: tuple[str, ...] = (
    "id_cruce",                  # ← LA LLAVE. El propio FUB si BANCI lo reclamó
    "estatus_match",
    "metodo_match",
    "submetodo_match",
    "nivel_match",
    "metodos_concurrentes",
    "n_registros_banci",         # cuántas filas de BANCI apuntan a este FUB (N:1)
    "id_registro_banci_principal",
    "carpeta_banci_principal",
    "corte_match",
    "version_match",
)

# El embudo del motor estándar, traducido a nivel (docs/3_metodologia_de_matching.md §3.2).
NIVEL_ESTANDAR = {"match_fub": 1, "match_curp": 2, "match_nombre": 3}

# Prioridad de la cascada, para elegir de forma estable el registro de BANCI que
# representa a un FUB alcanzado desde varias carpetas.
PRIORIDAD_CASCADA = {"manual": 0, "estandar": 1, "refinado": 2}

CON_CRUCE = "con_cruce"
CANDIDATO = "candidato_revision_manual"
SIN_CRUCE = "sin_cruce"


@dataclass
class ResultadoExportacion:
    banci: Path
    rnpdno: Path
    mapa: Path
    manifiesto: Path
    resumen: pd.DataFrame


# ─────────────────────────────────────────────────────────────────────────────
# Cómo se aparea cada hoja con sus columnas nuevas
#
# Sólo para los Excel. El RNPDNO en Parquet no pasa por aquí: su apareo por llave
# vive en `_escribir_parquet`.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class BloqueColumnas:
    """Las columnas nuevas de una hoja y de dónde sale el valor de cada fila.

    Dos formas de aparear, y la diferencia importa:

    - **posicional** (BANCI): la fila i de datos del Excel con la fila i del
      pipeline. Vale porque el ETL de BANCI no filtra ni reordena; el conteo de
      filas y `validar_export` lo comprueban.
    - **por llave** (RNPDNO en Excel): por FUB. No depende del orden, así que sigue
      siendo correcto si el archivo cambia.
    """
    columnas: tuple[str, ...]
    filas: list[tuple]
    nombre_llave: Optional[str] = None
    posicion: dict = field(default_factory=dict)
    encontrados: set = field(default_factory=set)
    idx_llave: Optional[int] = None

    @property
    def vacio(self) -> tuple:
        return (None,) * len(self.columnas)

    def fijar_llave(self, encabezado: list) -> None:
        if self.nombre_llave is None:
            return
        if self.nombre_llave not in encabezado:
            raise KeyError(f"La hoja no tiene la columna llave {self.nombre_llave!r}.")
        self.idx_llave = encabezado.index(self.nombre_llave)

    def valores(self, i_dato: int, fila: tuple) -> tuple:
        if self.nombre_llave is None:
            return self.filas[i_dato] if i_dato < len(self.filas) else self.vacio
        clave = fila[self.idx_llave] if self.idx_llave is not None else None
        if clave is None:
            return self.vacio
        pos = self.posicion.get(str(clave).strip())
        if pos is None:
            return self.vacio
        self.encontrados.add(str(clave).strip())
        return self.filas[pos]


def bloque_posicional(llaves: pd.DataFrame, columnas: tuple[str, ...]) -> BloqueColumnas:
    return BloqueColumnas(columnas=columnas, filas=_matriz(llaves, columnas))


def bloque_por_llave(llaves: pd.DataFrame, columnas: tuple[str, ...],
                     nombre_llave: str) -> BloqueColumnas:
    return BloqueColumnas(
        columnas=columnas,
        filas=_matriz(llaves, columnas),
        nombre_llave=nombre_llave,
        posicion={str(k).strip(): i for i, k in enumerate(llaves.index)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entrada principal
# ─────────────────────────────────────────────────────────────────────────────
def exportar_bases_con_llave(u: Universo, destino: Optional[Path] = None,
                             validar: bool = True, verbose: bool = True) -> ResultadoExportacion:
    """Escribe BANCI y RNPDNO con llave de cruce, y valida que sean fieles al origen.

    Consume la CAPA A del universo ya construido (`Universo.construir(cfg)`): no
    reejecuta los motores.
    """
    cfg = u.cfg
    banci_src = Path(config.BANCI_FILE)
    rnpdno_src = Path(config.RNPDNO_MANUAL_FILE_2)
    # Una subcarpeta por perfil: `reporte_diario` y `cruce_total` producen archivos
    # con el MISMO nombre (el del origen) y contenido distinto. Sin separarlos, la
    # segunda corrida pisaría a la primera sin avisar.
    destino = Path(destino) if destino else (config.OUTPUT_DIR / "bases_con_llave" / cfg.perfil)
    destino.mkdir(parents=True, exist_ok=True)

    ba = u.matching.banci
    fubs, mapa_tipo = u.matching.fubs_matcheados, u.matching.mapa_tipo_match
    corte = _corte(rnpdno_src)
    version = cfg.clave_matching

    if verbose:
        print(f"📇 Construyendo llaves ({len(ba):,} filas de BANCI, "
              f"{len(fubs):,} FUB matcheados)...")

    llaves_ba = construir_llaves_banci(ba, corte, version)
    llaves_rn = construir_llaves_rnpdno(llaves_ba, fubs, mapa_tipo, corte, version)
    _verificar_coherencia(llaves_ba, llaves_rn, fubs)

    # ── BANCI: sólo la hoja de datos lleva columnas; el resto se copia igual ──
    hoja_banci = config.BANCI_SHEET or _primera_hoja(banci_src)
    bloques_ba = {hoja_banci: bloque_posicional(llaves_ba, COLUMNAS_BANCI)}
    salida_ba = destino / banci_src.name
    if verbose:
        print(f"\n📤 BANCI → {salida_ba}")
    filas_ba = _escribir_workbook(banci_src, salida_ba, bloques_ba, verbose=verbose)
    if filas_ba[hoja_banci] != len(llaves_ba):
        raise AssertionError(
            f"❌ La hoja {hoja_banci!r} tiene {filas_ba[hoja_banci]:,} filas de datos y el "
            f"pipeline {len(llaves_ba):,}. El apareo posicional no es válido: vuelve a "
            "correr 2_Procesamiento_ETL_BANCI con este mismo archivo."
        )

    # ── RNPDNO: apareado por FUB, en el formato en que entró ─────────────────
    salida_rn = destino / rnpdno_src.name
    formato_rn = config.formato_rnpdno(rnpdno_src)
    if verbose:
        print(f"\n📤 RNPDNO → {salida_rn}")
    if formato_rn == "parquet":
        _, fubs_en_origen = _escribir_parquet(rnpdno_src, salida_rn, llaves_rn,
                                              COLUMNAS_RNPDNO, "fub", verbose=verbose)
    else:
        # Las tres hojas llevan el bloque; cada fila toma el de su FUB.
        bloques_rn = {h: bloque_por_llave(llaves_rn, COLUMNAS_RNPDNO, "fub")
                      for h in config.SHEET_NAMES.values()}
        _escribir_workbook(rnpdno_src, salida_rn, bloques_rn, verbose=verbose)
        fubs_en_origen = set().union(*(b.encontrados for b in bloques_rn.values()))
    _verificar_cobertura(fubs_en_origen, llaves_rn)

    if validar:
        if verbose:
            print("\n🔎 Validando fidelidad contra los archivos de origen...")
        validar_export(banci_src, salida_ba, bloques_ba, verbose=verbose)
        if formato_rn == "parquet":
            validar_export_parquet(rnpdno_src, salida_rn, COLUMNAS_RNPDNO, verbose=verbose)
        else:
            validar_export(rnpdno_src, salida_rn, bloques_rn, verbose=verbose)

    # ── Sidecar: la tabla puente, que es lo que se usa desde R o SQL ──────────
    ruta_mapa = destino / f"mapa_cruce_{corte}.parquet"
    puente = llaves_ba.loc[llaves_ba["id_cruce"].notna(),
                           ["id_registro_banci", "fila_origen_banci", "id_cruce",
                            "metodo_match", "submetodo_match", "nivel_match",
                            "metodos_concurrentes", "score_match", "evidencia_match"]
                           ].reset_index(drop=True)
    puente.to_parquet(ruta_mapa, index=False)
    puente.to_csv(ruta_mapa.with_suffix(".csv"), index=False, encoding="utf-8-sig")

    resumen = _resumen(llaves_ba, llaves_rn)
    ruta_manif = destino / f"manifiesto_{corte}.json"
    _escribir_manifiesto(ruta_manif, cfg, banci_src, rnpdno_src, salida_ba, salida_rn,
                         corte, version, resumen)

    if verbose:
        print("\n" + resumen.to_string(index=False))
        print(f"\n✅ Listo. Llave de cruce: `id_cruce` (FUB). Manifiesto: {ruta_manif.name}")

    return ResultadoExportacion(banci=salida_ba, rnpdno=salida_rn, mapa=ruta_mapa,
                                manifiesto=ruta_manif, resumen=resumen)


def _corte(rnpdno_src: Path) -> str:
    """Fecha de corte, tomada del nombre del archivo (reporte_personas_DDMMYYYY)."""
    m = re.search(r"(\d{2})(\d{2})(\d{4})", rnpdno_src.stem)
    if m:
        d, mes, a = m.groups()
        return f"{a}-{mes}-{d}"
    return date.fromtimestamp(rnpdno_src.stat().st_mtime).isoformat()


def _primera_hoja(ruta: Path) -> str:
    wb = openpyxl.load_workbook(ruta, read_only=True)
    try:
        return wb.sheetnames[0]
    finally:
        wb.close()


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de las columnas nuevas
# ─────────────────────────────────────────────────────────────────────────────
def id_registro_banci(ba: pd.DataFrame) -> pd.Series:
    """`ENTIDAD/carpeta#NN`: la carpeta y el ordinal de la víctima dentro de ella, en
    el orden del archivo. Se regenera desde el Excel de origen sin correr el pipeline."""
    ba = ba.reset_index(drop=True)
    carpeta = _txt(ba["id_carpeta_derivada_banci"])
    ent = _txt(ba["entidad_derivada_banci"])
    base = pd.Series([c if c else f"{e or 'SIN-ENTIDAD'}/SIN-CARPETA"
                      for c, e in zip(carpeta, ent)])
    ordinal = base.groupby(base).cumcount() + 1
    return base + "#" + ordinal.astype(str).str.zfill(2)


def construir_llaves_banci(ba: pd.DataFrame, corte: str, version: str) -> pd.DataFrame:
    """Una fila por fila de BANCI, en el MISMO orden que el archivo de origen."""
    ba = ba.reset_index(drop=True)
    n = len(ba)
    out = pd.DataFrame(index=range(n), dtype=object)

    # ── Identidad de fila ────────────────────────────────────────────────────
    out["id_registro_banci"] = id_registro_banci(ba)
    out["fila_origen_banci"] = np.arange(2, n + 2)   # +2: la fila 1 es el encabezado

    # ── La llave ─────────────────────────────────────────────────────────────
    id_cruce = _txt(ba["fub_derivada_rnpdno_banci"])
    con_match = id_cruce.notna()
    out["id_cruce"] = id_cruce

    # ── Candidatos a revisión manual: no son match, pero no son "nada" ───────
    # El refinado los propuso y `excluir_revision_manual` los retiró de la oferta,
    # dejándolos indistinguibles de las filas donde ningún motor encontró nada.
    # Se marcan aquí para que la cola de revisión sea visible y trabajable, sin
    # contaminar la llave: `id_cruce` sigue vacío.
    cand = pd.Series([None] * n, dtype=object)
    for motor in ("refinado", "estandar", "manual"):
        col_tipo = f"tipo_match_{motor}_anulado_derivada_rnpdno_banci"
        col_id = f"id_match_{motor}_anulado_derivada_rnpdno_banci"
        if col_tipo in ba.columns and col_id in ba.columns:
            m = (~con_match) & cand.isna() & (ba[col_tipo] == "revision manual")
            cand = cand.where(~m, _txt(ba[col_id]))
    es_cand = (~con_match) & cand.notna()

    out["estatus_match"] = np.where(con_match, CON_CRUCE,
                                    np.where(es_cand, CANDIDATO, SIN_CRUCE))
    out["fub_candidato_revision"] = cand.where(es_cand, None)

    # ── Procedencia del match ────────────────────────────────────────────────
    sub = _txt(ba.get("subcriterio_match_derivada_rnpdno_banci")).where(con_match, None)
    out["metodo_match"] = _txt(ba.get("metodo_origen_derivada_rnpdno_banci")).where(con_match, None)
    out["submetodo_match"] = sub
    out["nivel_match"] = pd.array(
        pd.to_numeric(sub.map(NIVEL_ESTANDAR), errors="coerce"), dtype="Int64")
    concurrentes = ba.get("tipo_match_derivada_rnpdno_banci")
    out["metodos_concurrentes"] = _txt(concurrentes).where(con_match, None)

    # ── FUB extra de una misma revisión manual (relación muchos a muchos) ────
    # Una revisión del SESNSP puede haber validado varios FUB para el mismo
    # registro; `id_cruce` sólo puede llevar uno. Los demás se listan aquí para
    # que no se pierdan personas por una limitación del formato.
    extra = ba.get("fubs_confirmados_manual_derivada_rnpdno_banci")
    out["fubs_adicionales_manual"] = (
        [_fubs_extra(v, p) for v, p in zip(extra, id_cruce)] if extra is not None else None)

    if "score_derivada_rnpdno_banci" in ba.columns:
        score = pd.to_numeric(ba["score_derivada_rnpdno_banci"], errors="coerce").round(2)
        out["score_match"] = score.where(con_match)
    else:
        out["score_match"] = None
    out["evidencia_match"] = _txt(ba.get("variables_match_derivada_rnpdno_banci")).where(con_match, None)
    out["corte_match"] = corte
    out["version_match"] = version

    return out[list(COLUMNAS_BANCI)]


def construir_llaves_rnpdno(llaves_ba: pd.DataFrame, fubs: set[str], mapa_tipo: dict,
                            corte: str, version: str) -> pd.DataFrame:
    """Una fila por FUB con algo que decir. Se indexa por `fub`.

    Sólo se materializan los FUB reclamados o propuestos (~12k de 408,600): el
    archivo se recorre en streaming y lo que no está aquí se escribe en blanco.
    """
    con = llaves_ba[llaves_ba["id_cruce"].notna()].copy()

    # El "principal" es el registro de BANCI que sostiene el match ganador. Con
    # varias carpetas apuntando a la misma persona hay que elegir una de forma
    # estable: la de mayor prioridad en la cascada y, a igualdad, la primera del
    # archivo. Elegir por orden de aparición a secas movería la atribución entre
    # cortes sin que nada más hubiera cambiado.
    con["_p"] = con["metodo_match"].map(PRIORIDAD_CASCADA).fillna(9)
    con = con.sort_values(["_p", "fila_origen_banci"], kind="stable")
    principal = con.drop_duplicates(subset=["id_cruce"], keep="first").set_index("id_cruce")
    conteo = con.groupby("id_cruce").size()

    out = pd.DataFrame(index=principal.index.rename("fub"))
    out["id_cruce"] = out.index
    out["estatus_match"] = CON_CRUCE
    out["metodo_match"] = principal["metodo_match"]
    out["submetodo_match"] = principal["submetodo_match"]
    out["nivel_match"] = principal["nivel_match"]
    out["metodos_concurrentes"] = [mapa_tipo.get(f) or principal.loc[f, "metodo_match"]
                                   for f in out.index]
    out["n_registros_banci"] = pd.array(conteo.reindex(out.index), dtype="Int64")
    out["id_registro_banci_principal"] = principal["id_registro_banci"]
    out["carpeta_banci_principal"] = principal["id_registro_banci"].str.rsplit("#", n=1).str[0]

    # ── FUB confirmados a mano que ninguna fila lleva como `id_cruce` ────────
    # Vienen de `fubs_adicionales_manual`: personas distintas validadas en la misma
    # revisión. Sin esto se perderían del lado del RNPDNO, que es donde se cuentan
    # personas.
    filas_extra = []
    con_extra = llaves_ba[llaves_ba["fubs_adicionales_manual"].notna()]
    vistos = set(out.index)
    for _, fila in con_extra.iterrows():
        for f in re.split(r"[;,]", str(fila["fubs_adicionales_manual"])):
            f = f.strip()
            if f and f in fubs and f not in vistos:
                vistos.add(f)
                filas_extra.append({
                    "fub": f, "id_cruce": f, "estatus_match": CON_CRUCE,
                    "metodo_match": "manual", "submetodo_match": "match_confirmado_sesnsp",
                    "nivel_match": pd.NA, "metodos_concurrentes": mapa_tipo.get(f, "manual"),
                    "n_registros_banci": 0,
                    "id_registro_banci_principal": fila["id_registro_banci"],
                    "carpeta_banci_principal": str(fila["id_registro_banci"]).rsplit("#", 1)[0],
                })

    # ── Candidatos a revisión, del lado del RNPDNO ───────────────────────────
    cand = llaves_ba.loc[llaves_ba["estatus_match"] == CANDIDATO, "fub_candidato_revision"]
    for f in cand.dropna().astype(str).unique():
        if f and f not in vistos:
            vistos.add(f)
            filas_extra.append({"fub": f, "id_cruce": None, "estatus_match": CANDIDATO,
                                "metodo_match": None, "submetodo_match": None,
                                "nivel_match": pd.NA, "metodos_concurrentes": None,
                                "n_registros_banci": 0,
                                "id_registro_banci_principal": None,
                                "carpeta_banci_principal": None})
    if filas_extra:
        out = pd.concat([out, pd.DataFrame(filas_extra).set_index("fub")])

    out["corte_match"] = corte
    out["version_match"] = version
    return out[list(COLUMNAS_RNPDNO)]


def _verificar_coherencia(llaves_ba: pd.DataFrame, llaves_rn: pd.DataFrame,
                          fubs: set[str]) -> None:
    """Integridad referencial entre las dos bases, antes de escribir nada."""
    cruces_ba = set(llaves_ba["id_cruce"].dropna().astype(str))
    con_cruce_rn = set(llaves_rn.index[llaves_rn["estatus_match"] == CON_CRUCE].astype(str))

    huerfanos = cruces_ba - con_cruce_rn
    if huerfanos:
        raise ValueError(f"❌ {len(huerfanos)} `id_cruce` de BANCI sin fila en RNPDNO. "
                         f"Ejemplos: {sorted(huerfanos)[:3]}")
    esperados = {str(f) for f in fubs}
    if con_cruce_rn != esperados:
        raise ValueError(
            f"❌ Los FUB con cruce no coinciden con `fubs_matcheados` de la CAPA A: "
            f"faltan {len(esperados - con_cruce_rn)}, sobran {len(con_cruce_rn - esperados)}."
        )
    if llaves_rn.index.has_duplicates:
        dup = llaves_rn.index[llaves_rn.index.duplicated()][:3].tolist()
        raise ValueError(f"❌ FUB repetido en el mapa del RNPDNO: {dup}")


def _verificar_cobertura(encontrados: set, llaves_rn: pd.DataFrame) -> None:
    """Todo FUB del mapa tiene que existir en el RNPDNO de origen.

    Si uno no aparece, el cruce estaría afirmando una pareja con un registro que
    el archivo no contiene: mejor detenerse que exportar una llave que no ancla.
    """
    faltan = set(llaves_rn.index.astype(str)) - encontrados
    if faltan:
        raise AssertionError(
            f"❌ {len(faltan)} FUB del mapa no existen en el RNPDNO exportado. "
            f"Ejemplos: {sorted(faltan)[:3]}. Probablemente el Parquet del ETL y el "
            "archivo de origen son de cortes distintos."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Escritura del Parquet (RNPDNO)
#
# El origen es una tabla única, no un libro de hojas: se lee entera, se le pegan
# las columnas nuevas apareadas por FUB y se reescribe. El apareo es por llave y
# no posicional, así que sigue siendo correcto aunque el archivo cambie de orden.
#
# Aquí no hay pérdida de tipos que vigilar: pandas conserva los dtypes tal cual,
# a diferencia del Excel, donde la reescritura redondea los flotantes al 16º
# dígito (ver `_redondeo_de_excel`).
# ─────────────────────────────────────────────────────────────────────────────
def _escribir_parquet(origen: Path, destino: Path, llaves: pd.DataFrame,
                      columnas: tuple[str, ...], nombre_llave: str,
                      verbose: bool = True) -> tuple[int, set]:
    """Copia el Parquet de origen con `columnas` añadidas al final.

    Devuelve cuántas filas se escribieron y qué llaves del mapa se encontraron en
    el origen, que es lo que `_verificar_cobertura` necesita para confirmar que
    ninguna llave quedó apuntando al vacío.
    """
    df = pd.read_parquet(origen)
    _verificar_colision(list(df.columns), columnas)
    if nombre_llave not in df.columns:
        raise KeyError(
            f"❌ El RNPDNO de origen no tiene la columna llave {nombre_llave!r}. "
            f"Columnas presentes: {list(df.columns)[:8]}…"
        )

    # El FUB se compara como texto limpio de los dos lados: el mapa viene del
    # pipeline y el archivo del RNPDNO, y no tienen por qué coincidir en dtype.
    clave = df[nombre_llave].astype(str).str.strip()
    mapa = llaves.copy()
    mapa.index = mapa.index.astype(str).str.strip()

    nuevas = mapa.reindex(clave)[list(columnas)]
    nuevas.index = df.index          # reindex trae el índice del FUB; se descarta

    salida = pd.concat([df, nuevas], axis=1)
    salida.to_parquet(destino, index=False)

    encontrados = set(clave[clave.isin(mapa.index)])
    if verbose:
        n_con_llave = int(nuevas["id_cruce"].notna().sum()) if "id_cruce" in nuevas else 0
        print(f"   · {origen.name:<34} {len(df):>8,} filas   "
              f"(+{len(columnas)} columnas, {n_con_llave:,} con `id_cruce`)")
    return len(df), encontrados


def validar_export_parquet(origen: Path, destino: Path, columnas: tuple[str, ...],
                           max_errores: int = 5, verbose: bool = True) -> None:
    """Compara columna por columna contra el origen. Falla ruidosamente a la primera.

    El equivalente de `validar_export` para el RNPDNO en Parquet. Misma razón de existir: el
    valor de este archivo depende por completo de que se pueda usar en lugar del
    original, así que una diferencia silenciosa es inaceptable.
    """
    a = pd.read_parquet(origen)
    b = pd.read_parquet(destino)

    if len(a) != len(b):
        raise AssertionError(
            f"❌ distinto número de filas: origen {len(a):,}, salida {len(b):,}.")

    n_orig = len(a.columns)
    if list(b.columns[:n_orig]) != list(a.columns):
        raise AssertionError(
            "❌ las columnas de origen no se conservaron con el mismo nombre y orden.")
    nuevas = list(b.columns[n_orig:])
    if nuevas != list(columnas):
        raise AssertionError(
            f"❌ columnas nuevas inesperadas: {nuevas} (se esperaban {list(columnas)}).")

    errores = []
    for c in a.columns:
        x, y = a[c], b[c]
        if x.dtype != y.dtype:
            errores.append((c, f"el tipo cambió: {x.dtype} → {y.dtype}"))
        else:
            distintas = ~((x == y) | (x.isna() & y.isna()))
            n = int(distintas.sum())
            if n:
                i = distintas.idxmax()
                errores.append(
                    (c, f"{n:,} filas distintas (p. ej. fila {i}: {x[i]!r} vs {y[i]!r})"))
        if len(errores) >= max_errores:
            break

    if errores:
        detalle = "\n".join(f"      {c}: {d}" for c, d in errores)
        raise AssertionError(f"❌ el contenido original no se conservó:\n{detalle}")

    if verbose:
        print(f"   ✓ {destino.name:<34} {len(b):>8,} filas idénticas, "
              f"+{len(nuevas)} columnas nuevas")


# ─────────────────────────────────────────────────────────────────────────────
# Escritura del Excel (BANCI, y el RNPDNO cuando llega en Excel)
#
# `write_only` + `read_only` es lo único viable en memoria para un libro grande:
# la hoja LOCALIZADAS del RNPDNO sola son ~270,000 × 61 celdas. Cargar el libro
# completo con openpyxl normal pediría decenas de GB.
# ─────────────────────────────────────────────────────────────────────────────
def _escribir_workbook(origen: Path, destino: Path, bloques: dict,
                       verbose: bool = True) -> dict[str, int]:
    filas_datos: dict[str, int] = {}
    wb_in = openpyxl.load_workbook(origen, read_only=True, data_only=False)
    wb_out = openpyxl.Workbook(write_only=True)
    try:
        for nombre in wb_in.sheetnames:
            ws_in, ws_out = wb_in[nombre], wb_out.create_sheet(title=nombre)
            bloque = bloques.get(nombre)
            filas_datos[nombre] = _copiar_hoja(ws_in, ws_out, bloque)
            if verbose:
                marca = f"+{len(bloque.columnas)} columnas" if bloque else "sin cambios"
                print(f"   · {nombre:<26} {filas_datos[nombre]:>8,} filas   ({marca})")
        wb_out.save(destino)
    finally:
        wb_in.close()
        wb_out.close()
    return filas_datos


def _copiar_hoja(ws_in, ws_out, bloque: Optional[BloqueColumnas]) -> int:
    if bloque is None:
        n = 0
        for fila in ws_in.iter_rows(values_only=True):
            ws_out.append(list(fila))
            n += 1
        return max(n - 1, 0)

    n_datos = 0
    for i, fila in enumerate(ws_in.iter_rows(values_only=True)):
        if i == 0:
            encabezado = list(fila)
            _verificar_colision(encabezado, bloque.columnas)
            bloque.fijar_llave(encabezado)
            ws_out.append(encabezado + list(bloque.columnas))
            continue
        ws_out.append(list(fila) + list(bloque.valores(n_datos, fila)))
        n_datos += 1
    return n_datos


def _verificar_colision(encabezado: list, columnas: tuple[str, ...]) -> None:
    choque = sorted(set(encabezado) & set(columnas))
    if choque:
        raise ValueError(
            f"❌ El archivo de origen ya trae columnas con estos nombres: {choque}. "
            "Renombra las columnas nuevas antes de exportar: sobrescribir una columna "
            "de origen rompería la promesa de fidelidad."
        )


# ─────────────────────────────────────────────────────────────────────────────
# El contrato: el archivo exportado ES el de origen, más columnas
# ─────────────────────────────────────────────────────────────────────────────
_AUSENTE = object()


def validar_export(origen: Path, destino: Path, bloques: dict,
                   max_errores: int = 5, verbose: bool = True) -> None:
    """Compara celda por celda contra el origen. Falla ruidosamente a la primera.

    No es paranoia: el valor de estos archivos depende por completo de que se
    puedan usar en lugar de los originales. Una diferencia silenciosa —una fecha
    convertida a texto, una fila corrida— haría que todo lo que se cruce después
    esté mal sin que nadie se entere.
    """
    wb_a = openpyxl.load_workbook(origen, read_only=True, data_only=False)
    wb_b = openpyxl.load_workbook(destino, read_only=True, data_only=False)
    try:
        if wb_a.sheetnames != wb_b.sheetnames:
            raise AssertionError(f"❌ Hojas distintas: {wb_a.sheetnames} vs {wb_b.sheetnames}")

        for nombre in wb_a.sheetnames:
            ws_a, ws_b = wb_a[nombre], wb_b[nombre]
            bloque = bloques.get(nombre)
            nuevas = list(bloque.columnas) if bloque else []
            errores, n_filas, n_vaciadas, n_redondeadas = [], 0, 0, 0

            for i, (fa, fb) in enumerate(zip_longest(
                    ws_a.iter_rows(values_only=True),
                    ws_b.iter_rows(values_only=True), fillvalue=_AUSENTE)):
                if fa is _AUSENTE or fb is _AUSENTE:
                    raise AssertionError(
                        f"❌ [{nombre}] distinto número de filas: la salida "
                        f"{'sobra' if fa is _AUSENTE else 'se queda corta'} en la fila {i + 1}.")
                n_filas += 1
                if i == 0 and list(fb[len(fa):]) != nuevas:
                    raise AssertionError(
                        f"❌ [{nombre}] columnas nuevas inesperadas: "
                        f"{list(fb[len(fa):])} (se esperaban {nuevas}).")
                n_vaciadas += sum(1 for a, b in zip(fa, fb) if a == "" and b is None)
                original_a, original_b = _sin_relleno(fa), _sin_relleno(fb[:len(fa)])
                if original_a != original_b:
                    difs = []
                    for j, (a, b) in enumerate(
                            zip_longest(original_a, original_b, fillvalue=None)):
                        if a == b:
                            continue
                        if _redondeo_de_excel(a, b):
                            n_redondeadas += 1
                        else:
                            difs.append((j, a, b))
                    if difs:
                        errores.append((i + 1, difs[:3]))
                        if len(errores) >= max_errores:
                            break

            if errores:
                detalle = "\n".join(f"      fila {f}: {d}" for f, d in errores)
                raise AssertionError(
                    f"❌ [{nombre}] el contenido original no se conservó:\n{detalle}")
            if verbose:
                notas = []
                if n_vaciadas:
                    notas.append(f"{n_vaciadas:,} cadenas vacías → celda vacía")
                if n_redondeadas:
                    notas.append(f"{n_redondeadas:,} decimales al 16º dígito")
                nota = f"  ({'; '.join(notas)})" if notas else ""
                print(f"   ✓ {nombre:<26} {n_filas:>8,} filas idénticas, "
                      f"+{len(nuevas)} columnas nuevas{nota}")
    finally:
        wb_a.close()
        wb_b.close()


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────
def _redondeo_de_excel(a, b) -> bool:
    """¿La diferencia entre dos números es sólo el redondeo de la reescritura?

    openpyxl serializa los flotantes con 16 dígitos significativos, así que un
    valor de 17 dígitos pierde el último (20.197756476636552 → 20.19775647663655).
    Excel guarda 15: la diferencia está por debajo de lo que la hoja representa, y
    en las coordenadas de BANCI —donde aparece— equivale a 1e-10 metros.

    Se acepta con tolerancia explícita y se cuenta. Cualquier diferencia mayor
    sigue siendo un error: esto no es un `isclose` genérico que tape errores de
    conversión, es exactamente el ancho del redondeo de la biblioteca.
    """
    if not (isinstance(a, float) and isinstance(b, float)):
        return False
    return a == b or abs(a - b) <= 1e-15 * max(abs(a), abs(b))


def _sin_relleno(fila) -> list:
    """Fila normalizada para comparar: cadena vacía = celda vacía, sin relleno final.

    Dos diferencias que openpyxl introduce al reescribir y que NO son pérdida de
    información:

    1. Las celdas vacías del final de una fila no se materializan, así que la fila
       queda más corta. Excel no distingue entre celda vacía y celda ausente (la
       `Hoja1` de BANCI, que es una tabla dinámica, es casi todo relleno).
    2. Una celda que contenía la cadena vacía `''` se escribe como celda vacía.
       BANCI trae miles (`COORD_X`, `COORD_Y`…). pandas lee las dos como NaN.

    Se normalizan para no delatar como diferencia algo que no lo es, pero
    `validar_export` cuenta las del caso 2 y las reporta: la deformación queda a
    la vista en vez de silenciada.
    """
    fila = [None if v == "" else v for v in fila]
    while fila and fila[-1] is None:
        fila.pop()
    return fila


def _matriz(df: pd.DataFrame, columnas: tuple[str, ...]) -> list[tuple]:
    """DataFrame → filas de tipos nativos de Python (openpyxl no acepta numpy)."""
    bloque = df[list(columnas)].to_numpy(dtype=object)
    return [tuple(_py(v) for v in fila) for fila in bloque]


def _py(v):
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _txt(s) -> pd.Series:
    """Serie de texto limpio: los vacíos quedan como None, nunca como 'nan'."""
    if s is None:
        return pd.Series(dtype=object)
    s = pd.Series(s).reset_index(drop=True)
    out = s.astype(object).where(s.notna(), None)
    return out.map(_limpiar_texto)


def _limpiar_texto(v):
    if v is None:
        return None
    v = v.strip() if isinstance(v, str) else str(v)
    return None if v in ("", "nan", "None", "<NA>") else v


def _fubs_extra(valor, principal) -> Optional[str]:
    """Los FUB adicionales de una revisión manual, sin el que ya viaja en `id_cruce`."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if isinstance(valor, str):
        # El motor manual los junta con coma (`",".join(confirmados[i])`); se acepta
        # también el punto y coma para no depender de ese detalle.
        lista = re.split(r"[;,]", valor)
    else:
        try:
            lista = list(valor)
        except TypeError:
            return None
    limpios = [str(v).strip() for v in lista]
    limpios = [v for v in limpios if v and v.lower() != "nan" and v != principal]
    return "; ".join(dict.fromkeys(limpios)) or None


def _resumen(llaves_ba: pd.DataFrame, llaves_rn: pd.DataFrame) -> pd.DataFrame:
    filas = []
    est = llaves_ba["estatus_match"].value_counts()
    for k in (CON_CRUCE, CANDIDATO, SIN_CRUCE):
        filas.append({"base": "BANCI", "concepto": k, "registros": int(est.get(k, 0))})
    for metodo, n in llaves_ba["metodo_match"].value_counts().items():
        filas.append({"base": "BANCI", "concepto": f"  metodo={metodo}", "registros": int(n)})
    for sub, n in llaves_ba["submetodo_match"].value_counts().items():
        filas.append({"base": "BANCI", "concepto": f"    submetodo={sub}", "registros": int(n)})
    filas.append({"base": "RNPDNO", "concepto": CON_CRUCE,
                  "registros": int((llaves_rn["estatus_match"] == CON_CRUCE).sum())})
    filas.append({"base": "RNPDNO", "concepto": CANDIDATO,
                  "registros": int((llaves_rn["estatus_match"] == CANDIDATO).sum())})
    filas.append({"base": "RNPDNO", "concepto": "FUB con >1 carpeta de BANCI",
                  "registros": int((llaves_rn["n_registros_banci"].fillna(0) > 1).sum())})
    return pd.DataFrame(filas)


def _escribir_manifiesto(ruta: Path, cfg: Settings, banci_src: Path, rnpdno_src: Path,
                         salida_ba: Path, salida_rn: Path, corte: str, version: str,
                         resumen: pd.DataFrame) -> None:
    ruta.write_text(json.dumps({
        "generado": datetime.now().isoformat(timespec="seconds"),
        "perfil": cfg.perfil,
        "corte_match": corte,
        "version_match": version,
        "clave_universo": cfg.clave_universo,
        "cascada": list(cfg.orden_prioridad_cascada),
        "reglas_post": list(cfg.reglas_post),
        "origen": {"banci": str(banci_src), "rnpdno": str(rnpdno_src)},
        "salida": {"banci": str(salida_ba), "rnpdno": str(salida_rn)},
        "columnas_nuevas": {"banci": list(COLUMNAS_BANCI), "rnpdno": list(COLUMNAS_RNPDNO)},
        "resumen": resumen.to_dict(orient="records"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
