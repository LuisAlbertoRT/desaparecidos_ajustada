"""
matching_r.py
=============
Replica la lógica exacta del script R:
  temporal/funcion_tratamiento_banci_rnpdno_con_columnas_matcheo_ari.R

Diferencias clave respecto a matching.py (versión Python original):
  - Tolerancia de fecha de hechos: hasta 1 año para desaparecidos, 30 días para localizados
  - Tolerancia de fecha de nacimiento: ±5 días (no coincidencia exacta)
  - Lógica de match por nombre: sistema de casos excluyentes tipo case_when de R
    (Caso 1/2/3), NO una disyunción OR inclusiva
  - Deduplicación activa en BANCI antes del match (por CURP y por nombre+fecha_inicio)
  - Match por FUB basado en clave compuesta (nombre + folio_rnpdno)
  - Genera columnas de trazabilidad completas:
      variables_match, verif_*, tolerancia_fecha_desaparicion,
      diferencia_dias_desaparicion, fecha_hechos_status, evaluacion_match, score

Autora original del script R: Jocelyn Rocha
"""

from __future__ import annotations

import re
import sys
import os
import unicodedata

import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from src.cleaning import limpiar_curp
from src.utils import normalize_header, standardize_columns
from src.matching import (
    col_b_entidad,
    col_b_fecha_hechos,
    col_b_fha_nac,
    col_b_nombres,
    col_b_primer_apellido,
    col_b_segundo_apellido,
    preparar_rnpdno,
    reparar_nombres_mal_formados,
)

# ---------------------------------------------------------------------------
# Columnas FUB posibles dentro del DataFrame de BANCI
# (el folio RNPDNO que la BANCI ya tiene asignado a algunos registros)
# ---------------------------------------------------------------------------
_BANCI_FUB_CANDIDATES = ["folio_rnpdno", "fub", "folio_fub", "folio"]

# Conjuntos de tolerancias válidas (réplica de R)
_TOLERANCIAS_LOCALIZADOS = frozenset({"Exacta", "1-5 días", "6-15 días", "16-30 días"})

# Columnas de RNPDNO que se traen en todos los niveles de match
_RNPDNO_EXTRA_COLS = ["indicadora_carpeta", "sexo"]


# ===========================================================================
# Utilidades internas
# ===========================================================================

def _get_banci_fub_col(df: pd.DataFrame) -> str | None:
    """Detecta el nombre de la columna FUB/folio_rnpdno dentro de BANCI."""
    # Primero búsqueda exacta
    for col in _BANCI_FUB_CANDIDATES:
        if col in df.columns:
            return col
    # Luego búsqueda normalizada (cubre 'Folio_RNPDNO', 'FOLIO RNPDNO', etc.)
    norm_map = {normalize_header(c): c for c in df.columns}
    for candidate in _BANCI_FUB_CANDIDATES:
        if candidate in norm_map:
            return norm_map[candidate]
    return None


def _normalizar_clave(series: pd.Series) -> pd.Series:
    """Normaliza texto: mayúsculas, sin acentos (conserva Ñ), espacios colapsados.
    Réplica de str_squish(toupper(...)) de R con la misma tabla de sustitución."""
    s = series.fillna("").astype(str).str.upper()
    for acento, base in [("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ü", "U")]:
        s = s.str.replace(acento, base, regex=False)
    return s.str.replace(r"\s+", " ", regex=True).str.strip()


def _construir_clave_fub(nombre_col: pd.Series, fub_col: pd.Series) -> pd.Series:
    """
    Réplica de R: str_squish(toupper(paste(nombre_completo, folio_rnpdno, sep=' '))).
    Construye la clave compuesta nombre + FUB que R usa para el match de nivel 1.
    """
    return _normalizar_clave(
        nombre_col.fillna("").astype(str) + " " + fub_col.fillna("").astype(str)
    )


def _clean_entidad(name: str) -> str:
    """Normaliza nombre de entidad: sin sufijos oficiales, sin acentos, en mayúsculas."""
    if not name:
        return ""
    for suffix in ["DE IGNACIO DE LA LLAVE", "DE ZARAGOZA", "DE OCAMPO", "ESTADO DE"]:
        name = name.replace(suffix, "")
    # Quitar diacríticos (excepto Ñ que se normaliza por sí solo)
    name = "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    )
    return name.strip()


# ===========================================================================
# Categorización de tolerancia de fechas (réplica vectorizada de R)
# ===========================================================================

def categorizar_tolerancia_fecha(
    fecha1: pd.Series,
    fecha2: pd.Series,
    tipo_match: str = "desaparecidos",
) -> pd.Series:
    """
    Versión vectorizada de la función R `categorizar_tolerancia_fecha`.

    Para tipo_match='desaparecidos':
        Exacta | 1-5 días | 6-10 días | 11-30 días (1 mes) | 2-5 meses | 6-12 meses | Más de 1 año

    Para tipo_match='localizados':
        Exacta | 1-5 días | 6-15 días | 16-30 días | Más de 30 días
    """
    diff_dias = (pd.to_datetime(fecha1, errors="coerce") -
                 pd.to_datetime(fecha2, errors="coerce")).abs().dt.days
    nan_mask = diff_dias.isna()

    if tipo_match == "desaparecidos":
        result = np.select(
            [diff_dias == 0,
             diff_dias <= 5,
             diff_dias <= 10,
             diff_dias <= 30,
             diff_dias <= 150,
             diff_dias <= 365],
            ["Exacta", "1-5 días", "6-10 días",
             "11-30 días (1 mes)", "2-5 meses", "6-12 meses"],
            default="Más de 1 año",
        )
    elif tipo_match == "localizados":
        result = np.select(
            [diff_dias == 0,
             diff_dias <= 5,
             diff_dias <= 15,
             diff_dias <= 30],
            ["Exacta", "1-5 días", "6-15 días", "16-30 días"],
            default="Más de 30 días",
        )
    else:
        return pd.Series([None] * len(fecha1), index=fecha1.index, dtype="object")

    out = pd.Series(result, index=fecha1.index, dtype="object")
    out[nan_mask] = None
    return out


# ===========================================================================
# Preparación de BANCI (con deduplicación activa — réplica exacta de R)
# ===========================================================================

# Identidad de la fila de BANCI, sembrada ANTES de cualquier dedup/concat.
#
# El motor reordena, deduplica y renumera su copia de BANCI varias veces
# (`pd.concat(..., ignore_index=True)`). Sin una columna que sobreviva a eso, el
# resultado sólo se puede devolver "por posición", y como el marco final no tiene ni
# las mismas filas ni el mismo orden que la entrada, cada match terminaba pegado a la
# carpeta equivocada. Se detectó porque de 1,410 matches por CURP —criterio que exige
# CURP idéntica— NINGUNO tenía la misma CURP que el FUB asignado.
COL_IDX_ORIGEN = "_idx_banci_origen"


def preparar_banci_r(
    df_banci: pd.DataFrame,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    filtrar_no_localizados: bool = True,
) -> pd.DataFrame:
    """
    Prepara BANCI replicando el flujo de R:
      1. Estandariza columnas
      2. Filtra por estatus 'No Localizado' y rango de fechas
      3. Valida CURP y nombre completo
      4. Deduplicación (pasos 1.7 y 1.8 del script R):
           - Por CURP limpia (mantiene el más reciente por fecha_hechos)
           - Por nombre_completo + fecha_inicio (mantiene el más reciente)
      5. Marca registros con identidad inválida (skip_match=True) sin eliminarlos
    """
    print("--- [1/2] Preparando BANCI (lógica R) ---")

    df = df_banci.copy()
    df[COL_IDX_ORIGEN] = df.index
    df = standardize_columns(df, config.BANCI_COLUMN_MAPPING, strict=False, verbose=True)

    # Normalizar columna FUB en BANCI (si existe)
    banci_fub_col = _get_banci_fub_col(df)
    if banci_fub_col:
        df[banci_fub_col] = (
            df[banci_fub_col]
            .astype(str)
            .replace({"": np.nan, "nan": np.nan, "0": np.nan, "None": np.nan})
        )

    # Limpiar columnas de nombre (ceros → NA)
    for col in ["nombres", "primer_apellido", "segundo_apellido"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .replace(r"^0$", np.nan, regex=True)
                .replace("nan", np.nan)
            )

    # Reparar nombres mal formados (apellidos mezclados en el campo nombre)
    df = reparar_nombres_mal_formados(df)

    # Convertir fechas
    for col in [col_b_fecha_hechos, "fha_de_ini", "fecha_inicio", col_b_fha_nac]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # ---------- Filtro de estatus: solo No Localizados ----------
    # Lo gobierna `filtrar_banci_no_localizados` del perfil. En false el motor ve
    # también las carpetas de personas ya localizadas: es lo que hace falta para un
    # cruce total, y lo que el R original nunca contempló.
    col_estatus = next(
        (k for k, v in config.BANCI_COLUMN_MAPPING.items()
         if "estatus" in [x.lower() for x in v] or k == "localizado_o_no_localizado"),
        "localizado_o_no_localizado",
    )
    if not filtrar_no_localizados:
        print("  > Filtro 'No Localizado' DESACTIVADO: entra BANCI completo "
              f"({len(df):,} registros).")
    elif col_estatus in df.columns:
        norm = df[col_estatus].astype(str).str.strip().str.upper()
        mask_no_loc = (
            norm.isin(["NO LOCALIZADA", "NO LOCALIZADO", "NO", "DESAPARECIDA", "DESAPARECIDO"])
            | norm.str.match(r"^NO\s*LOCALIZAD[OA]", na=False)
        )
        df = df[mask_no_loc].copy()
        print(f"  > Registros tras filtro 'No Localizado': {len(df)}")

    # ---------- Filtro de fechas ----------
    if fecha_inicio and col_b_fecha_hechos in df.columns:
        df = df[df[col_b_fecha_hechos] >= pd.to_datetime(fecha_inicio, utc=True)]
    if fecha_fin and col_b_fecha_hechos in df.columns:
        df = df[df[col_b_fecha_hechos] < pd.to_datetime(fecha_fin, utc=True)]

    if df.empty:
        print("  > ⚠️ BANCI vacío tras filtros.")
        return df

    # ---------- CURP ----------
    # La validez ya viene del ETL (`curp_valida_derivada_banci`); aquí sólo se arma
    # la llave de comparación, con la misma limpieza que la del RNPDNO.
    df["curp_limpia"] = limpiar_curp(df["curp_banci"])

    # ---------- Nombre completo ----------
    def _col(name):
        return df[name].fillna("").astype(str) if name in df.columns else pd.Series([""] * len(df), index=df.index)

    df["nombre_completo"] = _normalizar_clave(
        _col(col_b_nombres) + " " + _col(col_b_primer_apellido) + " " + _col(col_b_segundo_apellido)
    )

    # ---------- Validar nombre ----------
    patron_ruido = (
        r"SE DESCONOCE|RESTOS OSEOS|CUERPO|SIN VIDA|DESCONOCIDO|"
        r"NO IDENTIFICADO|\bSD\b|\bNA\b|^M$|([a-z]\.){2,}[a-z]?"
    )
    s_nom = df["nombre_completo"].fillna("")
    df["es_nombre_valido"] = (
        df["nombre_completo"].notna()
        & ~s_nom.str.contains(r"\d", regex=True)
        & ~s_nom.str.contains(patron_ruido, flags=re.IGNORECASE, regex=True)
        & (s_nom.str.len() >= 11)
    )

    # ---------- Deduplicación (réplica pasos 1.7 y 1.8 del script R) ----------

    # Ordenar desc por fha_de_hchos (R: arrange(desc(fha_de_hchos)) antes de dedup)
    if col_b_fecha_hechos in df.columns:
        df = df.sort_values(col_b_fecha_hechos, ascending=False, na_position="last")

    # Paso 1.7: distinct(curp, .keep_all=T) solo en registros con CURP válida
    df_curp_v = df[df["curp_valida_derivada_banci"]].drop_duplicates(subset=["curp_limpia"], keep="first")
    df_curp_inv = df[~df["curp_valida_derivada_banci"]]
    df = pd.concat([df_curp_v, df_curp_inv], ignore_index=True)

    # Paso 1.8: distinct(nombre_concat, .keep_all=T) solo en registros con nombre válido
    # nombre_concat = nombre_completo + fha_de_ini (como string — réplica de R)
    col_fecha_ini = next((c for c in ["fha_de_ini", "fecha_inicio"] if c in df.columns), None)
    if col_fecha_ini:
        df["_nombre_concat"] = df["nombre_completo"].fillna("NA") + df[col_fecha_ini].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "NA"
        )
        df_nom_v = df[df["es_nombre_valido"]].drop_duplicates(subset=["_nombre_concat"], keep="first")
        df_nom_inv = df[~df["es_nombre_valido"]]
        df = pd.concat([df_nom_v, df_nom_inv], ignore_index=True)
        df = df.drop(columns=["_nombre_concat"], errors="ignore")

    print(f"  > Registros tras deduplicación: {len(df)}")

    # ---------- Marcar identidad inválida (sin eliminar del DataFrame) ----------
    cond_invalido = (~df["curp_valida_derivada_banci"]) & (~df["es_nombre_valido"])
    if banci_fub_col:
        # Si tiene folio_rnpdno puede seguir intentando match por FUB
        cond_invalido = cond_invalido & df[banci_fub_col].isna()

    df["skip_match"] = cond_invalido
    n_inv = cond_invalido.sum()
    if n_inv > 0:
        print(f"  > ℹ️ Registros con identidad inválida (conservados, sin match): {n_inv}")

    print(f"  > Registros finales para confronta: {len(df)}")
    return df


# ===========================================================================
# Nivel 1: Match por FUB + Nombre Completo (sección 4.1 del script R)
# ===========================================================================

def _match_fub_r(
    banci: pd.DataFrame,
    rnpdno_no_loc: pd.DataFrame,
    rnpdno_loc: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Match nivel 1 replicando exactamente R (sección 4.1).

    Lógica:
      - Construye clave compuesta: normalizar(nombre_completo + " " + folio_rnpdno)
      - vs No Localizados: coincidencia directa de la clave (sin condición de fecha)
      - vs Localizados: coincidencia de clave + tolerancia_fecha ∈ {≤ 30 días}

    Returns
    -------
    matched   : filas de banci que hicieron match (con columnas RNPDNO añadidas)
    remanente : filas que NO hicieron match (sin columnas RNPDNO)
    """
    banci_fub_col = _get_banci_fub_col(banci)
    if banci_fub_col is None:
        print("  > ⚠️ Sin columna FUB en BANCI. Saltando match por FUB.")
        return pd.DataFrame(), banci.copy()

    mask_eligible = ~banci.get("skip_match", pd.Series(False, index=banci.index))
    mask_tiene_fub = banci[banci_fub_col].notna()

    # Nada elegible → devolver todo como remanente
    if not (mask_eligible & mask_tiene_fub).any():
        print("  > Matches por FUB: 0")
        return pd.DataFrame(), banci.copy()

    banci = banci.copy()
    banci["_clave_fub"] = _construir_clave_fub(banci["nombre_completo"], banci[banci_fub_col])

    # Columnas que se traen de RNPDNO
    base_cols = ["fub", "fechahechos", "estado", "fechanacimiento", "clasificacion_des"]
    extra_cols = [c for c in _RNPDNO_EXTRA_COLS if c in rnpdno_no_loc.columns]
    rnpdno_cols = base_cols + extra_cols

    # Construir clave en RNPDNO
    rnpdno_no_loc = rnpdno_no_loc.copy()
    rnpdno_no_loc["_clave_fub"] = _construir_clave_fub(
        rnpdno_no_loc["nombre_completo_rnpdno"], rnpdno_no_loc["fub"]
    )
    rnpdno_loc = rnpdno_loc.copy()
    rnpdno_loc["_clave_fub"] = _construir_clave_fub(
        rnpdno_loc["nombre_completo_rnpdno"], rnpdno_loc["fub"]
    )

    # ---- Paso 4.1.1: match vs No Localizados (sin condición de fecha) ----
    claves_no_loc = set(rnpdno_no_loc["_clave_fub"].dropna())
    mask_match_no_loc = mask_eligible & mask_tiene_fub & banci["_clave_fub"].isin(claves_no_loc)

    # ---- Paso 4.1.2: match vs Localizados (tolerancia ≤ 30 días) ----
    candidatos_loc_mask = mask_eligible & mask_tiene_fub & ~mask_match_no_loc
    mask_match_loc = pd.Series(False, index=banci.index)

    if candidatos_loc_mask.any():
        cands = banci[candidatos_loc_mask][["_clave_fub", col_b_fecha_hechos]].copy()
        loc_lookup = rnpdno_loc[["_clave_fub", "fub", "fechahechos"]].copy()
        merged = cands.merge(loc_lookup, on="_clave_fub", how="inner")
        if not merged.empty:
            tol = categorizar_tolerancia_fecha(
                merged[col_b_fecha_hechos], merged["fechahechos"], tipo_match="localizados"
            )
            valid_claves = set(merged.loc[tol.isin(_TOLERANCIAS_LOCALIZADOS), "_clave_fub"].dropna())
            mask_match_loc = mask_eligible & mask_tiene_fub & banci["_clave_fub"].isin(valid_claves)

    mask_total = mask_match_no_loc | mask_match_loc

    if not mask_total.any():
        print("  > Matches por FUB: 0")
        return pd.DataFrame(), banci.drop(columns=["_clave_fub"], errors="ignore")

    matched = banci[mask_total].copy()

    # Traer datos de RNPDNO (priorizar no_loc, luego loc como fallback)
    rename_rnpdno = {
        "fub": "fub_rnpdno",
        "fechahechos": "fecha_hechos_rnpdno",
        "estado": "entidad_hechos_rnpdno",
        "fechanacimiento": "fecha_nacimiento_rnpdno",
        "clasificacion_des": "clasificacion_des_rnpdno",
        "sexo": "sexo_rnpdno",
    }
    nl_cols = ["_clave_fub"] + [c for c in rnpdno_cols if c in rnpdno_no_loc.columns]
    lo_cols = ["_clave_fub"] + [c for c in rnpdno_cols if c in rnpdno_loc.columns]

    matched = matched.merge(
        rnpdno_no_loc[nl_cols].rename(columns={k: v for k, v in rename_rnpdno.items() if k in nl_cols}),
        on="_clave_fub", how="left", suffixes=("", "_nl"),
    )
    matched = matched.merge(
        rnpdno_loc[lo_cols].rename(columns={k: f"{v}_loc" for k, v in rename_rnpdno.items() if k in lo_cols}),
        on="_clave_fub", how="left",
    )

    # Consolidar: priorizar no_loc
    for canonical, loc_name in [
        ("fub_rnpdno", "fub_rnpdno_loc"),
        ("fecha_hechos_rnpdno", "fecha_hechos_rnpdno_loc"),
        ("entidad_hechos_rnpdno", "entidad_hechos_rnpdno_loc"),
        ("fecha_nacimiento_rnpdno", "fecha_nacimiento_rnpdno_loc"),
        ("clasificacion_des_rnpdno", "clasificacion_des_rnpdno_loc"),
        ("sexo_rnpdno", "sexo_rnpdno_loc"),
    ]:
        if canonical in matched.columns and loc_name in matched.columns:
            matched[canonical] = matched[canonical].combine_first(matched[loc_name])
            matched = matched.drop(columns=[loc_name], errors="ignore")

    # Metadata del match
    matched["tipo_match"] = "match_fub"
    matched["variables_match"] = "NOMBRE 1.00 + FUB"
    matched["verif_nombre"] = "COINCIDE"
    matched["verif_curp"] = "NO APLICA"
    matched["verif_fecha_nac"] = "NO APLICA"
    matched["verif_entidad"] = "NO APLICA"
    matched["verif_sexo"] = "NO APLICA"

    matched["tolerancia_fecha_desaparicion"] = categorizar_tolerancia_fecha(
        matched[col_b_fecha_hechos], matched.get("fecha_hechos_rnpdno"), tipo_match="desaparecidos"
    )
    matched["diferencia_dias_desaparicion"] = (
        pd.to_datetime(matched[col_b_fecha_hechos], errors="coerce")
        - pd.to_datetime(matched.get("fecha_hechos_rnpdno"), errors="coerce")
    ).dt.days

    matched = matched.drop(columns=["_clave_fub"], errors="ignore")
    print(f"  > Matches por FUB: {len(matched)}")

    remanente = banci[~mask_total].drop(columns=["_clave_fub"], errors="ignore")
    return matched, remanente


# ===========================================================================
# Nivel 2: Match por CURP (sección 4.2 del script R)
# ===========================================================================

def _match_curp_r(
    banci: pd.DataFrame,
    rnpdno_no_loc: pd.DataFrame,
    rnpdno_loc: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Match nivel 2 replicando R (sección 4.2).

    Lógica:
      - Solo candidatos con CURP válida y no marcados para saltar
      - Dedup interno por curp_limpia (más reciente por fha_de_ini — réplica de R 4.2.2)
      - vs No Localizados: match directo por CURP, sin condición de fecha
        (RNPDNO también se deduplica tomando la fecha_hechos más reciente por CURP)
      - vs Localizados: match por CURP + tolerancia_fecha ∈ {≤ 30 días}

    Returns
    -------
    matched   : filas con match (con columnas RNPDNO)
    remanente : filas sin match (incluye las que tenían CURP inválida)
    """
    mask_eligible = ~banci.get("skip_match", pd.Series(False, index=banci.index))
    mask_curp = banci["curp_valida_derivada_banci"] == True

    candidates = banci[mask_eligible & mask_curp].copy()
    no_candidates = banci[~(mask_eligible & mask_curp)].copy()

    if candidates.empty:
        print("  > Matches por CURP: 0")
        return pd.DataFrame(), banci.copy()

    # Dedup interno de candidatos (R: group_by(curp_limpia) |> slice_max(fha_de_ini))
    col_ini = next((c for c in ["fha_de_ini", "fecha_inicio"] if c in candidates.columns), None)
    if col_ini:
        candidates = candidates.sort_values(col_ini, ascending=False, na_position="last")
    candidates = candidates.drop_duplicates(subset=["curp_limpia"], keep="first")

    # Columnas de RNPDNO. El ETL entrega la CURP tal como viene (`curp_vic_rnpdno`);
    # aquí se limpia igual que la de BANCI (`curp_limpia`) para compararlas.
    curp_src_rn = "curp_vic_rnpdno" if "curp_vic_rnpdno" in rnpdno_no_loc.columns else "curp_vic"
    rnpdno_curp_col = "curp_limpia_rnpdno"
    rnpdno_no_loc = rnpdno_no_loc.assign(**{rnpdno_curp_col: limpiar_curp(rnpdno_no_loc[curp_src_rn])})
    if curp_src_rn in rnpdno_loc.columns:
        rnpdno_loc = rnpdno_loc.assign(**{rnpdno_curp_col: limpiar_curp(rnpdno_loc[curp_src_rn])})
    base_cols = ["fub", "fechahechos", "estado", "fechanacimiento", "clasificacion_des"]
    extra_cols = [c for c in _RNPDNO_EXTRA_COLS if c in rnpdno_no_loc.columns]
    nl_cols = [rnpdno_curp_col] + base_cols + extra_cols

    rename_rnpdno = {
        "fub": "fub_rnpdno",
        "fechahechos": "fecha_hechos_rnpdno",
        "estado": "entidad_hechos_rnpdno",
        "fechanacimiento": "fecha_nacimiento_rnpdno",
        "clasificacion_des": "clasificacion_des_rnpdno",
        "sexo": "sexo_rnpdno",
    }

    # ---- Match vs No Localizados (CURP directa, sin condición de fecha) ----
    # RNPDNO deduplicado por CURP (más reciente por fecha_hechos — réplica de R 4.2.2)
    lookup_nl = (
        rnpdno_no_loc[[c for c in nl_cols if c in rnpdno_no_loc.columns]]
        .sort_values("fechahechos", ascending=False, na_position="last")
        .drop_duplicates(rnpdno_curp_col, keep="first")
        .rename(columns={k: v for k, v in rename_rnpdno.items() if k != rnpdno_curp_col})
    )

    merged_nl = candidates.merge(
        lookup_nl, left_on="curp_limpia", right_on=rnpdno_curp_col, how="left"
    ).drop(columns=[rnpdno_curp_col], errors="ignore")

    matched_nl = merged_nl[merged_nl["fub_rnpdno"].notna()].copy()
    remaining = merged_nl[merged_nl["fub_rnpdno"].isna()].copy()
    # Limpiar columnas RNPDNO vacías del remanente
    rnpdno_result_cols = list(rename_rnpdno.values())
    remaining = remaining.drop(columns=[c for c in rnpdno_result_cols if c in remaining.columns], errors="ignore")

    # ---- Match vs Localizados (CURP + tolerancia ≤ 30 días) ----
    matched_loc = pd.DataFrame()
    rnpdno_curp_col_loc = rnpdno_curp_col
    lo_cols = [c for c in ([rnpdno_curp_col_loc] + base_cols + extra_cols) if c in rnpdno_loc.columns]

    if not remaining.empty and lo_cols:
        lookup_loc = rnpdno_loc[lo_cols].rename(
            columns={k: v for k, v in rename_rnpdno.items() if k != rnpdno_curp_col_loc}
        )
        merged_loc = remaining.merge(
            lookup_loc, left_on="curp_limpia", right_on=rnpdno_curp_col_loc, how="left"
        ).drop(columns=[rnpdno_curp_col_loc], errors="ignore")

        if not merged_loc.empty and "fub_rnpdno" in merged_loc.columns:
            tol = categorizar_tolerancia_fecha(
                merged_loc[col_b_fecha_hechos], merged_loc["fecha_hechos_rnpdno"],
                tipo_match="localizados",
            )
            matched_loc = merged_loc[
                merged_loc["fub_rnpdno"].notna() & tol.isin(_TOLERANCIAS_LOCALIZADOS)
            ].copy()

    # ---- Combinar ----
    all_matched = pd.concat([matched_nl, matched_loc], ignore_index=True)

    if all_matched.empty:
        print("  > Matches por CURP: 0")
        return pd.DataFrame(), banci.copy()

    # Metadata
    all_matched["tipo_match"] = "match_curp"
    all_matched["variables_match"] = "CURP"
    all_matched["verif_curp"] = "COINCIDE"
    all_matched["verif_nombre"] = "NO APLICA"
    all_matched["verif_fecha_nac"] = "NO APLICA"
    all_matched["verif_entidad"] = "NO APLICA"
    all_matched["verif_sexo"] = "NO APLICA"

    all_matched["tolerancia_fecha_desaparicion"] = categorizar_tolerancia_fecha(
        all_matched[col_b_fecha_hechos], all_matched.get("fecha_hechos_rnpdno"),
        tipo_match="desaparecidos",
    )
    all_matched["diferencia_dias_desaparicion"] = (
        pd.to_datetime(all_matched[col_b_fecha_hechos], errors="coerce")
        - pd.to_datetime(all_matched.get("fecha_hechos_rnpdno"), errors="coerce")
    ).dt.days

    print(f"  > Matches por CURP: {len(all_matched)}")

    # Remanente = candidatos que no matchearon + los que nunca fueron candidatos
    matched_curps = set(all_matched["curp_limpia"].dropna())
    remanente_cands = banci[mask_eligible & mask_curp & ~banci["curp_limpia"].isin(matched_curps)]
    remanente = pd.concat([remanente_cands, no_candidates], ignore_index=True)

    return all_matched, remanente


# ===========================================================================
# Nivel 3: Match por Nombre Completo (sección 4.3 del script R)
# ===========================================================================

def _validar_match_nombre_r(row: pd.Series, tipo: str = "desaparecidos") -> bool:
    """
    Replica la lógica case_when del script R para el match por nombre (sección 4.3).

    Columnas esperadas en `row` (después de la operación merge):
      BANCI : col_b_fha_nac, col_b_fecha_hechos, col_b_entidad
      RNPDNO: fecha_nacimiento_rnpdno, fecha_hechos_rnpdno, entidad_hechos_rnpdno

    Para tipo='desaparecidos':
      Caso 1: ambas bases tienen fecha_nac Y |diff_nac| ≤ 5 días
              → acepta si fecha_hechos ∈ rango hasta 1 año
      Caso 2: ambas bases tienen fecha_nac Y diff_nac > 5 días
              → RECHAZA (NA en R)
      Caso 3: alguna base carece de fecha_nac
              → acepta si entidad coincide Y fecha_hechos ∈ rango hasta 1 año

    Para tipo='localizados':
      → acepta si fecha_hechos ≤ 30 días Y (fecha_nac ≤ 5 días O entidad coincide)
    """
    fha_nac_b = row.get(col_b_fha_nac)
    fecha_nac_r = row.get("fecha_nacimiento_rnpdno")
    fha_hchos_b = row.get(col_b_fecha_hechos)
    fecha_hchos_r = row.get("fecha_hechos_rnpdno")
    ent_b = _clean_entidad(str(row.get(col_b_entidad, "") or "").upper())
    ent_r = _clean_entidad(str(row.get("entidad_hechos_rnpdno", "") or "").upper())

    entidad_coincide = bool(ent_b and ent_r and (ent_b == ent_r or ent_b in ent_r or ent_r in ent_b))

    # Diferencia de días en fecha de hechos
    diff_hchos: int | None = None
    if pd.notna(fha_hchos_b) and pd.notna(fecha_hchos_r):
        try:
            diff_hchos = abs((pd.to_datetime(fha_hchos_b) - pd.to_datetime(fecha_hchos_r)).days)
        except Exception:
            pass

    # Diferencia de días en fecha de nacimiento
    diff_nac: int | None = None
    if pd.notna(fha_nac_b) and pd.notna(fecha_nac_r):
        try:
            diff_nac = abs((pd.to_datetime(fha_nac_b) - pd.to_datetime(fecha_nac_r)).days)
        except Exception:
            pass

    if tipo == "desaparecidos":
        tolerancia_max_hchos = 365  # hasta 1 año
        if diff_nac is not None:
            # Caso 1: fecha_nac coincide dentro de 5 días
            if diff_nac <= 5:
                return diff_hchos is not None and diff_hchos <= tolerancia_max_hchos
            # Caso 2: fecha_nac existe pero difiere > 5 días → RECHAZAR
            return False
        # Caso 3: sin fecha_nac → requiere entidad + fecha_hechos dentro del año
        return entidad_coincide and diff_hchos is not None and diff_hchos <= tolerancia_max_hchos

    elif tipo == "localizados":
        if diff_hchos is None or diff_hchos > 30:
            return False
        return (diff_nac is not None and diff_nac <= 5) or entidad_coincide

    return False


def _match_nombre_r(
    banci: pd.DataFrame,
    rnpdno_no_loc: pd.DataFrame,
    rnpdno_loc: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Match nivel 3 replicando R (sección 4.3).

    Lógica:
      - Solo candidatos con nombre válido y no marcados para saltar
      - Match exacto de nombre_completo con RNPDNO
      - Aplica _validar_match_nombre_r para filtrar falsos positivos
      - Primero vs No Localizados (tipo='desaparecidos'), luego vs Localizados (tipo='localizados')
      - Genera verif_fecha_nac, verif_entidad, verif_sexo y variables_match compuesto

    Returns
    -------
    matched   : filas con match (con columnas RNPDNO y metadata)
    sin_match : filas sin match
    """
    mask_eligible = ~banci.get("skip_match", pd.Series(False, index=banci.index))
    mask_nombre = banci["es_nombre_valido"] == True

    candidates = banci[mask_eligible & mask_nombre].copy()
    sin_identidad = banci[~(mask_eligible & mask_nombre)].copy()

    if candidates.empty:
        print("  > Matches por Nombre: 0")
        return pd.DataFrame(), banci.copy()

    # Columnas de RNPDNO
    base_cols = ["nombre_completo_rnpdno", "fub", "fechahechos", "estado",
                 "fechanacimiento", "clasificacion_des"]
    extra_cols = [c for c in _RNPDNO_EXTRA_COLS if c in rnpdno_no_loc.columns]
    nl_use = [c for c in base_cols + extra_cols if c in rnpdno_no_loc.columns]
    lo_use = [c for c in base_cols + extra_cols if c in rnpdno_loc.columns]

    rename_rnpdno = {
        "fub": "fub_rnpdno",
        "fechahechos": "fecha_hechos_rnpdno",
        "estado": "entidad_hechos_rnpdno",
        "fechanacimiento": "fecha_nacimiento_rnpdno",
        "clasificacion_des": "clasificacion_des_rnpdno",
        "sexo": "sexo_rnpdno",
    }

    def _make_merge(df_left: pd.DataFrame, df_right: pd.DataFrame, right_cols: list) -> pd.DataFrame:
        merged = df_left.reset_index().merge(
            df_right[right_cols].rename(columns={k: v for k, v in rename_rnpdno.items() if k in right_cols}),
            left_on="nombre_completo",
            right_on="nombre_completo_rnpdno",
            how="inner",
        ).drop(columns=["nombre_completo_rnpdno"], errors="ignore")
        # Asegurar tipos de fecha en el merged
        for col in [col_b_fecha_hechos, "fecha_hechos_rnpdno", col_b_fha_nac, "fecha_nacimiento_rnpdno"]:
            if col in merged.columns:
                merged[col] = pd.to_datetime(merged[col], errors="coerce")
        return merged

    # ---- Paso 4.3.2: match vs No Localizados ----
    merged_nl = _make_merge(candidates, rnpdno_no_loc, nl_use)

    matched_nl_idx: set[int] = set()
    merged_nl_valid = pd.DataFrame()
    if not merged_nl.empty:
        merged_nl["_es_match"] = merged_nl.apply(
            lambda r: _validar_match_nombre_r(r, tipo="desaparecidos"), axis=1
        )
        merged_nl_valid = merged_nl[merged_nl["_es_match"]].drop_duplicates(subset=["index"], keep="first")
        matched_nl_idx = set(merged_nl_valid["index"])

    # ---- Paso 4.3.3: match vs Localizados (solo para los que no matchearon) ----
    remaining_idx = [i for i in candidates.index if i not in matched_nl_idx]
    remaining = candidates.loc[remaining_idx] if remaining_idx else pd.DataFrame()

    matched_loc_idx: set[int] = set()
    merged_loc_valid = pd.DataFrame()
    if not remaining.empty and lo_use:
        merged_loc = _make_merge(remaining, rnpdno_loc, lo_use)
        if not merged_loc.empty:
            merged_loc["_es_match"] = merged_loc.apply(
                lambda r: _validar_match_nombre_r(r, tipo="localizados"), axis=1
            )
            merged_loc_valid = merged_loc[merged_loc["_es_match"]].drop_duplicates(subset=["index"], keep="first")
            matched_loc_idx = set(merged_loc_valid["index"])

    all_matched_idx = matched_nl_idx | matched_loc_idx

    if not all_matched_idx:
        print("  > Matches por Nombre: 0")
        sin_match = banci.copy()
        sin_match["tolerancia_fecha_desaparicion"] = None
        sin_match["diferencia_dias_desaparicion"] = None
        return pd.DataFrame(), sin_match

    # ---- Construir DataFrame de matches ----
    # Partimos de los merges ya validados (tienen las columnas de RNPDNO)
    parts: list[pd.DataFrame] = []
    if not merged_nl_valid.empty:
        parts.append(merged_nl_valid[merged_nl_valid["index"].isin(matched_nl_idx)])
    if not merged_loc_valid.empty:
        loc_only = merged_loc_valid[
            merged_loc_valid["index"].isin(matched_loc_idx - matched_nl_idx)
        ]
        if not loc_only.empty:
            parts.append(loc_only)

    matched = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    matched = matched.drop(columns=["index", "_es_match"], errors="ignore")

    # ---- Metadata ----
    matched["tipo_match"] = "match_nombre"
    matched["variables_match"] = "NOMBRE 1.00"
    matched["verif_nombre"] = "COINCIDE"
    matched["verif_curp"] = "NO APLICA"

    # verif_fecha_nac: coincide si |diff| ≤ 5 días
    diff_nac = (
        pd.to_datetime(matched[col_b_fha_nac], errors="coerce")
        - pd.to_datetime(matched.get("fecha_nacimiento_rnpdno"), errors="coerce")
    ).abs().dt.days
    matched["verif_fecha_nac"] = np.where(
        diff_nac.notna() & (diff_nac <= 5),
        "COINCIDE (" + diff_nac.fillna(0).astype(int).astype(str) + " DIAS)",
        "NO APLICA",
    )
    mask_nac = matched["verif_fecha_nac"] != "NO APLICA"
    matched.loc[mask_nac, "variables_match"] += " + FECHA NAC (+- 5 DIAS)"

    # verif_entidad
    if col_b_entidad in matched.columns and "entidad_hechos_rnpdno" in matched.columns:
        ent_b = matched[col_b_entidad].fillna("").astype(str).str.upper().str.strip()
        ent_r = matched["entidad_hechos_rnpdno"].fillna("").astype(str).str.upper().str.strip()
        mask_ent = ent_b == ent_r
        matched["verif_entidad"] = np.where(mask_ent, "COINCIDE", "NO APLICA")
        matched.loc[mask_ent, "variables_match"] += " + ENTIDAD FEDERATIVA"
    else:
        matched["verif_entidad"] = "NO APLICA"

    # verif_sexo
    if "sexo" in matched.columns and "sexo_rnpdno" in matched.columns:
        mask_sexo = (
            matched["sexo"].fillna("").str.upper() == matched["sexo_rnpdno"].fillna("").str.upper()
        )
        matched["verif_sexo"] = np.where(mask_sexo, "COINCIDE", "NO APLICA")
        matched.loc[mask_sexo, "variables_match"] += " + SEXO"
    else:
        matched["verif_sexo"] = "NO APLICA"

    # Tolerancia y diferencia de días
    matched["tolerancia_fecha_desaparicion"] = categorizar_tolerancia_fecha(
        matched[col_b_fecha_hechos], matched.get("fecha_hechos_rnpdno"), tipo_match="desaparecidos"
    )
    matched["diferencia_dias_desaparicion"] = (
        pd.to_datetime(matched[col_b_fecha_hechos], errors="coerce")
        - pd.to_datetime(matched.get("fecha_hechos_rnpdno"), errors="coerce")
    ).dt.days

    print(f"  > Matches por Nombre: {len(matched)}")

    # Remanente
    sin_match = banci[~banci.index.isin(all_matched_idx)].copy()
    sin_match["tolerancia_fecha_desaparicion"] = None
    sin_match["diferencia_dias_desaparicion"] = None

    return matched, sin_match


# ===========================================================================
# Post-procesamiento: metadata final (réplica de sección 5 del script R)
# ===========================================================================

def _agregar_metadata_final_r(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade las columnas de trazabilidad finales que R genera en la sección 5:
      evaluacion_match, score, verif_carpeta, fecha_hechos_status,
      y enriquece variables_match con '+FECHA DE HECHOS (+- 10 DIAS)'.
    """
    df = df.copy()
    df["evaluacion_match"] = "DEFINITIVO"
    df["score"] = 100
    df["verif_carpeta"] = "NO APLICA"

    for col in ["verif_nombre", "verif_curp", "verif_entidad", "verif_sexo", "verif_fecha_nac"]:
        if col not in df.columns:
            df[col] = "NO APLICA"
        else:
            df[col] = df[col].fillna("NO APLICA")

    # fecha_hechos_status: COINCIDE si |diff| ≤ 10 días, DIFIERE si no. Sin
    # diferencia (falta alguna de las dos fechas) queda nulo: no hay nada que
    # comparar. R escribía ahí "NA (NA DIAS)", que es lo que deja `paste0` con NA.
    diff_abs = pd.to_numeric(df.get("diferencia_dias_desaparicion"), errors="coerce").abs()
    df["fecha_hechos_status"] = np.where(
        diff_abs.notna() & (diff_abs <= 10),
        "COINCIDE (" + diff_abs.fillna(0).astype(int).astype(str) + " DIAS)",
        "DIFIERE (" + diff_abs.fillna(0).astype(int).astype(str) + " DIAS)",
    )
    df.loc[diff_abs.isna(), "fecha_hechos_status"] = None

    # match_definitivo: la regla con que se separaba la base de R antes de mandarla al
    # Secretariado. DIFIERE va a revisión de fecha de hechos; lo demás es definitivo.
    # Un estado nulo (sin diferencia que medir) cuenta como COINCIDE, que es lo que
    # pasaba en R: ahí el estado era el texto "NA (NA DIAS)", que no contiene DIFIERE.
    df["match_definitivo"] = np.where(
        df["fecha_hechos_status"].str.contains("DIFIERE", case=False, na=False),
        "DIFIERE", "COINCIDE",
    )

    # Enriquecer variables_match con fecha de hechos
    mask_coincide = df["fecha_hechos_status"].str.startswith("COINCIDE", na=False)
    if "variables_match" in df.columns:
        df.loc[mask_coincide, "variables_match"] = (
            df.loc[mask_coincide, "variables_match"] + "; +FECHA DE HECHOS (+- 10 DIAS)"
        )

    # Renombrar ntra_ci → carpeta_investigacion_banci (como en R)
    if "ntra_ci" in df.columns:
        df = df.rename(columns={"ntra_ci": "carpeta_investigacion_banci"})

    return df


# ===========================================================================
# Función principal
# ===========================================================================

def ejecutar_confronta_r(
    df_banci: pd.DataFrame,
    df_rnpdno: pd.DataFrame,
    fecha_inicio_banci: str | None = None,
    fecha_fin_banci: str | None = None,
    fecha_inicio_rnpdno: str | None = None,
    fecha_fin_rnpdno: str | None = None,
    filtrar_banci_no_localizados: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Ejecuta el matching jerárquico BANCI vs RNPDNO replicando la lógica exacta del script R.

    Flujo:
      1. Preparar BANCI (con deduplicación activa)
      2. Preparar RNPDNO (No Localizados y Localizados)
      3. Match por FUB + Nombre  (sin condición de fecha para no_loc; ≤ 30 días para loc)
      4. Match por CURP           (sin condición de fecha para no_loc; ≤ 30 días para loc)
      5. Match por Nombre Completo (case_when jerárquico: hasta 1 año des., ≤ 30 días loc.)
      6. Dedup final por fub_rnpdno (R: group_by(fub_rnpdno) |> filter(row_number()==1))
      7. Metadata final (evaluacion_match, score, fecha_hechos_status, etc.)

    Parameters
    ----------
    df_banci, df_rnpdno        : DataFrames crudos (antes de preparación)
    fecha_inicio_banci         : "YYYY-MM-DD" para filtrar BANCI (≥)
    fecha_fin_banci            : "YYYY-MM-DD" para filtrar BANCI (<)
    fecha_inicio_rnpdno        : fecha de inicio para RNPDNO (se pasa a preparar_rnpdno)
    fecha_fin_rnpdno           : fecha de fin para RNPDNO

    Returns
    -------
    Base_BANCI_con_match_con_RNPDNO : registros de BANCI con match en RNPDNO
    Base_BANCI_sin_match_con_RNPDNO : registros de BANCI sin match
    """
    print("=" * 60)
    print("CONFRONTA R-COMPATIBLE: inicio")
    print("=" * 60)

    # 1. Preparar bases
    banci_proc = preparar_banci_r(df_banci, fecha_inicio_banci, fecha_fin_banci,
                                  filtrar_no_localizados=filtrar_banci_no_localizados)
    rnpdno_no_loc, rnpdno_loc = preparar_rnpdno(df_rnpdno, fecha_inicio_rnpdno, fecha_fin_rnpdno)

    if banci_proc.empty:
        print("⚠️  No hay registros en BANCI para realizar el match.")
        return pd.DataFrame(), pd.DataFrame()

    # 2. Nivel 1: FUB
    print("\n[NIVEL 1] Match por FUB + Nombre")
    matched_fub, remanente = _match_fub_r(banci_proc, rnpdno_no_loc, rnpdno_loc)

    # 3. Nivel 2: CURP
    print("\n[NIVEL 2] Match por CURP")
    matched_curp, remanente = _match_curp_r(remanente, rnpdno_no_loc, rnpdno_loc)

    # 4. Nivel 3: Nombre
    print("\n[NIVEL 3] Match por Nombre Completo")
    matched_nombre, sin_match = _match_nombre_r(remanente, rnpdno_no_loc, rnpdno_loc)

    # 5. Consolidar base con match
    con_match = pd.concat([matched_fub, matched_curp, matched_nombre], ignore_index=True)

    # 6. Dedup final por fub_rnpdno (réplica de R sección 5: group_by(fub_rnpdno) |> filter(row_number()==1))
    if "fub_rnpdno" in con_match.columns:
        con_match = con_match[
            con_match["fub_rnpdno"].isna()
            | ~con_match["fub_rnpdno"].duplicated(keep="first")
        ]

    # 7. Metadata final
    con_match = _agregar_metadata_final_r(con_match)

    # 8. Base sin match: remanente del nivel 3 + registros marcados skip_match
    skip_mask = banci_proc.get("skip_match", pd.Series(False, index=banci_proc.index))
    skip_registros = banci_proc[skip_mask]

    sin_match_final = pd.concat([sin_match, skip_registros], ignore_index=True).drop_duplicates()
    for col in ["tolerancia_fecha_desaparicion", "diferencia_dias_desaparicion"]:
        if col not in sin_match_final.columns:
            sin_match_final[col] = None

    print("\n" + "=" * 60)
    print("RESULTADO FINAL:")
    print(f"  Con match en RNPDNO    : {len(con_match):,}")
    print(f"  Sin match (solo BANCI) : {len(sin_match_final):,}")
    print("=" * 60)

    return con_match, sin_match_final
