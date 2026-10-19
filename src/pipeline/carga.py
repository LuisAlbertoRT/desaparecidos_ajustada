"""CAPA A · Carga de fuentes.

Lee los tres insumos del pipeline de indicadores SIN filtrar por entidad: el
universo se construye siempre nacional y la entidad se aplica al rebanar
(ver `src.slices`). Esa es la razón por la que una sola corrida de matching
alcanza para las 32 PPT estatales.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import config
from src.settings import Settings


@dataclass
class Fuentes:
    """Insumos crudos ya normalizados y cruzados con confrontas."""
    rn: pd.DataFrame          # RNPDNO del ETL + indicadora de la PUI + municipio
    ba: pd.DataFrame          # BANCI limpio
    n_confrontas: int


def cargar_fuentes(cfg: Settings, verbose: bool = True) -> Fuentes:
    _verificar_universo_nacional()
    rn = _cargar_rnpdno(cfg, verbose)
    ba = _cargar_banci(cfg, verbose)
    rn, n_conf = _integrar_confrontas(rn, cfg, verbose)

    if verbose:
        print(f"\n✅ Fuentes listas (universo NACIONAL). "
              f"RNPDNO: {len(rn):,}  |  BANCI: {len(ba):,}")
    return Fuentes(rn=rn, ba=ba, n_confrontas=n_conf)


def _verificar_universo_nacional() -> None:
    """El universo debe construirse nacional; la entidad se aplica al rebanar.

    `config.ESTADO` sólo lo leen los notebooks ETL 1 y 2. Si quedó activo, los
    Parquet de origen están filtrados por entidad y el universo sería parcial
    sin que nada lo delate: los conteos de las demás entidades saldrían en cero.
    """
    estado = getattr(config, "ESTADO", None)
    if estado:
        nombre = config.ENTIDADES.get(estado, estado)
        raise RuntimeError(
            f"❌ config.ESTADO está en {estado!r} ({nombre}).\n"
            "   El universo debe construirse NACIONAL: la entidad es una dimensión de\n"
            "   rebanada, no un filtro previo al matching. Con ESTADO activo, los Parquet\n"
            "   del ETL quedan filtrados y el universo sería parcial en silencio.\n\n"
            "   Solución: pon config.ESTADO = None, vuelve a correr los notebooks 1 y 2,\n"
            "   y pide la entidad al rebanar:\n"
            f"       Slice('rn', '01oct24-max', estatus='des', estado={estado})"
        )


# ─────────────────────────────────────────────────────────────────────────────
def _cargar_rnpdno(cfg: Settings, verbose: bool) -> pd.DataFrame:
    ruta = cfg.rnpdno_etl_parquet
    if not ruta.exists():
        raise FileNotFoundError(
            f"❌ No se encontró el maestro RNPDNO: {ruta}\n"
            "   Ejecuta primero 1_Procesamiento_ETL_RNPDNO.ipynb."
        )
    df = pd.read_parquet(ruta)
    if df.empty:
        raise ValueError("❌ El DataFrame consolidado de RNPDNO está vacío.")

    # Un Parquet de otra versión del notebook 1 trae otros nombres, y el pipeline
    # leería columnas equivocadas sin avisar (p. ej. la CURP imputada donde espera
    # la original). Las fechas ya llegan convertidas en sus `_derivada_rnpdno`.
    faltan = [c for c in config.RNPDNO_OUTPUT_COLUMNS if c not in df.columns]
    if faltan:
        raise ValueError(
            f"❌ {ruta.name} no trae {len(faltan)} columnas que espera el pipeline "
            f"(p. ej. {faltan[:3]}).\n"
            "   Vuelve a ejecutar 1_Procesamiento_ETL_RNPDNO.ipynb."
        )

    df = _derivar_municipio_rnpdno(df, verbose)

    if verbose:
        print(f"✅ RNPDNO cargado: {len(df):,} registros, {len(df.columns)} columnas.")
    return df


def _derivar_municipio_rnpdno(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    """Añade `municipio_derivada_rnpdno`: el NOMBRE del municipio de desaparición.

    El motor refinado compara municipios con fuzzy match (`UMBRAL_MUNICIPIO = 0.80`),
    una métrica pensada para nombres ("GENERAL ESCOBEDO" vs "ESCOBEDO"). El RNPDNO
    sólo trae la clave (`idmunicipio`, además con formato float: "75.0") y BANCI usa
    otra codificación, así que comparar claves daba intersección CERO y `_muni_igual`
    era siempre False. Aquí la clave se traduce a nombre con el catálogo del INEGI
    (`CVE_ENT` + `CVE_MUN` → `NOM_MUN`), que es la codificación que usa el RNPDNO.

    Se deriva al cargar —y no en el ETL— porque sólo necesita columnas que el Parquet
    ya trae: no obliga a reejecutar el notebook 1.
    """
    if "municipio_derivada_rnpdno" in df.columns:
        return df

    col_ent = next((c for c in ["idestado_derivada_rnpdno", "idestado"] if c in df.columns), None)
    col_mun = next((c for c in ["idmunicipio_derivada_rnpdno", "idmunicipio"] if c in df.columns), None)
    ruta = getattr(config, "CATALOGO_MUNICIPIOS_FILE", None)

    if not (col_ent and col_mun) or ruta is None or not Path(ruta).exists():
        df["municipio_derivada_rnpdno"] = pd.NA
        if verbose:
            falta = "columnas idestado/idmunicipio" if not (col_ent and col_mun) else str(ruta)
            print(f"  ⚠️ Sin `municipio_derivada_rnpdno` (falta {falta}): el motor "
                  f"refinado no podrá usar el municipio como variable de apoyo.")
        return df

    cat = pd.read_csv(ruta, dtype=str, encoding="utf-8")
    llave_cat = (pd.to_numeric(cat["CVE_ENT"], errors="coerce").astype("Int64").astype(str)
                 + "_"
                 + pd.to_numeric(cat["CVE_MUN"], errors="coerce").astype("Int64").astype(str))
    mapa = dict(zip(llave_cat, cat["NOM_MUN"]))

    llave = (pd.to_numeric(df[col_ent], errors="coerce").astype("Int64").astype(str)
             + "_"
             + pd.to_numeric(df[col_mun], errors="coerce").astype("Int64").astype(str))
    df["municipio_derivada_rnpdno"] = llave.map(mapa)

    if verbose:
        n = int(df["municipio_derivada_rnpdno"].notna().sum())
        print(f"  🗺️ municipio_derivada_rnpdno: {n:,} de {len(df):,} resueltos "
              f"con el catálogo INEGI.")
    return df


def _cargar_banci(cfg: Settings, verbose: bool) -> pd.DataFrame:
    ruta = cfg.banci_etl_parquet
    if not ruta.exists():
        fallback = config.OUTPUT_DIR / "df_banci_limpio.parquet"
        if not fallback.exists():
            raise FileNotFoundError(f"❌ No se encontró el BANCI limpio: {ruta}")
        ruta = fallback
    df = pd.read_parquet(ruta)
    if df.empty:
        raise ValueError("❌ El DataFrame de BANCI está vacío.")
    # Mismo motivo que en el RNPDNO: un Parquet de otra versión trae otros nombres.
    faltan = [c for c in config.BANCI_OUTPUT_COLUMNS if c not in df.columns]
    if faltan:
        raise ValueError(
            f"❌ {ruta.name} no trae {len(faltan)} columnas que espera el pipeline "
            f"(p. ej. {faltan[:3]}).\n"
            "   Vuelve a ejecutar 2_Procesamiento_ETL_BANCI.ipynb."
        )
    if verbose:
        print(f"✅ BANCI cargado: {len(df):,} registros.")
        _avisar_columnas_refinado(df)
    return df


# Columnas que el motor refinado necesita y que sólo puede producir el ETL de BANCI
# (vienen de la hoja de origen, no se pueden derivar de lo que ya está en el Parquet).
_COLS_REFINADO_BANCI = {
    "id_ci_derivada_banci": (
        "consecutivo de respaldo cuando NTRA_CI trae <= 2 dígitos "
        "(≈1 de cada 3 registros no localizados se queda sin folio comparable sin ella)"
    ),
    "nom_mun_hchos_derivada_banci": (
        "NOMBRE del municipio de los hechos; sin ella el municipio nunca coincide "
        "y se pierde como corroborador y como variable de apoyo"
    ),
    "id_carpeta_derivada_banci": (
        "identificador único de carpeta; sin él la multiplicidad se calcula con el "
        "folio crudo y los registros con NTRA_CI='0' se marcan colectivos entre sí, "
        "lo que OMITE la guarda anti-homónimo del motor refinado"
    ),
}


def _avisar_columnas_refinado(df: pd.DataFrame) -> None:
    faltantes = [c for c in _COLS_REFINADO_BANCI if c not in df.columns]
    if not faltantes:
        return
    print("  ⚠️ El BANCI del ETL no trae columnas que el motor refinado necesita:")
    for c in faltantes:
        print(f"       {c}: {_COLS_REFINADO_BANCI[c]}")
    print("     Vuelve a ejecutar 2_Procesamiento_ETL_BANCI.ipynb para generarlas.")


def _integrar_confrontas(rn: pd.DataFrame, cfg: Settings, verbose: bool) -> tuple[pd.DataFrame, int]:
    """Trae de Resultado_3 la indicadora de indicio de vida de cada FUB.

    Se colapsa a binaria ("…en PUI" cuenta como registro administrativo) y queda
    en `indicadora_indicio_de_vida_derivada_pui`.
    """
    mapeo = config.CONFRONTAS_COLUMN_MAPPING
    alias_fub = {a.lower() for a in mapeo["fub"]}
    alias_ind = {a.lower() for a in mapeo["indicadora_registro"]}

    def usecols(col):
        c = str(col).lower().strip()
        return c in alias_fub or c in alias_ind

    # El archivo de confrontas lo produce 3_Procesamiento_ETL_PUI.ipynb como Parquet, pero
    # antes se entregaba a mano en Excel y los perfiles pueden seguir apuntando a un .xlsx.
    # Se aceptan los dos: `read_parquet` no admite un callable en `columns`, así que para
    # Parquet el predicado se aplica sobre los nombres del esquema.
    ruta_conf = Path(cfg.confrontas_file)
    if ruta_conf.suffix.lower() == ".parquet":
        nombres = pq.read_schema(ruta_conf).names
        conf = pd.read_parquet(ruta_conf, columns=[c for c in nombres if usecols(c)])
    else:
        conf = pd.read_excel(ruta_conf, usecols=usecols)
    col_fub = next(c for c in conf.columns if c.lower() in alias_fub)
    conf = conf.rename(columns={col_fub: "fub"})
    conf["fub"] = conf["fub"].astype(str).str.strip()
    conf = conf.drop_duplicates(subset=["fub"])

    col_ind = next((c for c in conf.columns if c.lower() in alias_ind), None)
    if col_ind is None:
        raise KeyError(
            f"No se encontró columna indicadora en confrontas ({cfg.confrontas_file.name}). "
            f"Alias buscados: {sorted(alias_ind)}"
        )

    clave = rn["fub_rnpdno"].astype(str).str.strip()
    s = clave.map(conf.set_index("fub")[col_ind]).fillna("sin registro administrativo")
    s = s.astype(str).str.lower().str.strip()
    s = s.replace("con registro administrativo en pui", "con registro administrativo")
    rn["indicadora_indicio_de_vida_derivada_pui"] = s

    if verbose:
        print(f"✅ Confrontas integradas ({len(conf):,} FUBs con registro).")
    return rn, len(conf)
