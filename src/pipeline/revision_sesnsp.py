"""CAPA C · Bases para la revisión manual del Secretariado (SESNSP).

DOS BASES
---------
Las mismas dos que antes se armaban a mano con las salidas del script de R y de
normalizar_folios_v6.py, y que el Secretariado devolvía contestadas:

    verificación de fecha   `exportar_revision_fecha_hechos`  → columna `VALIDO`
        Pares que un motor sostiene como match pero cuya fecha de hechos no lo confirma.
        Vuelve como matches_verif_fecha_hechos_SESNSP.xlsx.
    candidatos              `exportar_candidatos_revision`    → columna `VALIDA`
        El mejor candidato que el refinado propone para cada registro sin match.
        Vuelve como revision_manual_score_SESNSP.xlsx. Con la lógica del flujo R →
        normalizar_folios sale del perfil `revision_secretariado` (notebook 8).

Un par (registro de BANCI, FUB) por renglón, con los datos de las dos bases que el
revisor necesita para decidir.

DE DÓNDE SALE CADA PAR
----------------------
Las colas las arma la capa A (`motores._cola_verif_fecha`, `motores._cola_candidatos`) y
viajan en el universo (`u.matching.verif_fecha`, `u.matching.candidatos`), porque sólo ahí
existen las columnas de cada motor. En la verificación de fecha:

    estándar  `match_definitivo == "DIFIERE"`: la regla con que se partía la base del
              script de R. Más de 10 días entre las dos fechas de hechos.
    refinado  los definitivos cuya fecha no cupo en ±10 días o que no la tienen: la
              regla de normalizar_folios_v6.py (`matches_verif_fecha_hechos_v6.xlsx`).

`motor_origen` dice de cuál viene; si los dos proponen el mismo par sale una sola vez,
como "estandar, refinado".

QUÉ SE DESCUENTA
----------------
Lo que el Secretariado ya contestó, con la regla de normalizar_folios_v6.py:

    matches_verif_fecha_hechos  SI o NO  → caso cerrado, no se vuelve a mandar.
    revision_manual_score       SI       → caso cerrado.
                                NO       → sólo se bloquea ESE par.
    FUB ya emparejado en una revisión    → no se vuelve a proponer.
    sin respuesta (NA)                   → se vuelve a mandar.

FORMATO
-------
Las columnas de los archivos que el Secretariado ya devolvió, en los nombres que reconoce
`leer_revisiones_sesnsp`. Así el archivo contestado se puede volver a leer:
`validar=True` lo comprueba al escribirlo, ligando cada renglón con su registro de BANCI
igual que lo hará el motor manual.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

import config
from src.motor_refinado import (
    _hash_norm,
    descuentos_sesnsp,
    leer_revisiones_sesnsp,
    resolver_revisiones_a_banci,
)
from src.pipeline.carga import cargar_fuentes
from src.pipeline.exportacion_llaves import _corte, id_registro_banci
from src.pipeline.motores import _NOMBRES_MOTORES_BA
from src.pipeline.universo import Universo

# Columna del archivo ← columna del ETL. El lado BANCI usa las mismas columnas con que
# el motor manual liga una revisión con su registro (`resolver_revisiones_a_banci`):
# si no, el archivo contestado no se podría volver a leer.
_COLS_BANCI = {
    "carpeta_investigacion_banci": "ntra_ci_derivada_banci",
    "entidad_reporta_desaparicion": "entidad_derivada_banci",
    "municipio_desaparicion": "nom_mun_hchos_derivada_banci",
    "id_carpeta_investigacion_banci": "id_carpeta_derivada_banci",
    "fecha_de_hechos_banci": "fha_de_hchos_derivada_banci",
    "sexo_banci": "sexo_banci",
    "fecha_nacimiento_banci": "fha_nac_derivada_banci",
    "localizado_o_no_localizado_banci": "localizado_o_no_localizado_derivada_banci",
    "nombres_banci": "nombres_derivada_banci",
    "primer_apellido_banci": "primer_apellido_derivada_banci",
    "segundo_apellido_banci": "segundo_apellido_derivada_banci",
    "curp_banci": "curp_banci",
    "llave_banci": "llave_banci",
}
_COLS_RNPDNO = {
    "estado_desaparicion_rnpdno": "estado_derivada_rnpdno",
    "municipio_desaparicion_rnpdno": "municipio_derivada_rnpdno",
    "fecha_hechos_rnpdno": "fechahechos_derivada_rnpdno",
    "fecha_hechos_modificada_rnpdno": "fecha_hechos_modificada_derivada_rnpdno",
    "sexo_rnpdno": "sexo_rnpdno",
    "fecha_nacimiento_rnpdno": "fechanacimiento_derivada_rnpdno",
    "clasificacion_des_rnpdno": "clasificacion_des_derivada_rnpdno",
    "carpeta_investigacion_rnpdno": "expedientes_rnpdno",
    "nombre_vic_rnpdno": "nombre_vic_rnpdno",
    "primerapellido_vic_rnpdno": "primerapellido_vic_rnpdno",
    "segundoapellido_vic_rnpdno": "segundoapellido_vic_rnpdno",
    "curp_victima_rnpdno": "curp_vic_derivada_rnpdno",
}
_TRAZA = ["evaluacion_match", "score", "variables_match", "fecha_hechos_status"]
_VERIF = ["verif_carpeta", "verif_nombre", "verif_curp", "verif_entidad",
          "verif_sexo", "verif_fecha_nac"]


@dataclass
class ResultadoRevision:
    archivo: Path
    base: pd.DataFrame        # lo que se escribió, un par por renglón
    resumen: pd.DataFrame     # cuántos pares propuso cada motor y cuántos se descontaron


def exportar_revision_fecha_hechos(u: Universo, destino: Optional[Path] = None,
                                   validar: bool = True,
                                   verbose: bool = True) -> ResultadoRevision:
    """Base de verificación de fecha de hechos (columna de respuesta `VALIDO`)."""
    return _exportar(u, u.matching.verif_fecha, "VALIDO", "revision_fecha_hechos",
                     "verificación de fecha de hechos", destino, validar, verbose)


def exportar_candidatos_revision(u: Universo, destino: Optional[Path] = None,
                                 validar: bool = True,
                                 verbose: bool = True) -> ResultadoRevision:
    """Base de candidatos a revisión manual del refinado (columna de respuesta `VALIDA`)."""
    return _exportar(u, u.matching.candidatos, "VALIDA", "candidatos_revision",
                     "candidatos a revisión manual", destino, validar, verbose)


def _exportar(u: Universo, cola: pd.DataFrame, respuesta: str, prefijo: str,
              titulo: str, destino: Optional[Path], validar: bool,
              verbose: bool) -> ResultadoRevision:
    """Descuenta de la cola de la capa A lo ya contestado y escribe el Excel.

    La cola sale del universo que se acaba de construir (`Universo.construir(cfg)`),
    la misma corrida de los motores que alimenta los indicadores.
    """
    cfg = u.cfg

    # BANCI y RNPDNO tal como los vieron los motores. La cola apunta a BANCI por
    # POSICIÓN, así que las filas tienen que ser las mismas y en el mismo orden.
    fuentes = cargar_fuentes(cfg, verbose=False)
    ba, rn = fuentes.ba.reset_index(drop=True), fuentes.rn
    n_matching = len(u.matching.banci)
    if len(ba) != n_matching:
        raise AssertionError(
            f"❌ El BANCI del ETL tiene {len(ba):,} filas y el del universo {n_matching:,}. "
            "El ETL cambió después de construir el universo: vuelve a construirlo."
        )

    # ── Lo que el Secretariado ya contestó ───────────────────────────────────
    # Con el BANCI completo y los nombres de los motores: es exactamente lo que ve el
    # motor manual al aplicar las respuestas.
    ba_motor = ba.rename(columns=_NOMBRES_MOTORES_BA)
    p = cfg.params_motores["manual"]
    rev = leer_revisiones_sesnsp(
        p["ruta_verif_fecha_hechos"], p["ruta_revision_manual"],
        p["hoja_verif"], p["hoja_revision"], p["skiprows_verif"], p["skiprows_revision"],
        p["col_mapping_verif"], p["col_mapping_revision"], verbose=False,
    )
    cerrados, fubs_cerrados, pares_rechazados, _ = descuentos_sesnsp(ba_motor, rev, verbose=False)

    fila = cola["fila_derivada_banci"]
    fub = cola["fub_derivada_rnpdno_banci"].map(_hash_norm)
    m_cerrado = fila.isin(cerrados)
    m_fub = ~m_cerrado & fub.isin(fubs_cerrados)
    m_par = ~m_cerrado & ~m_fub & pd.Series(
        [(f, u) in pares_rechazados for f, u in zip(fila, fub)], index=cola.index)
    queda = ~(m_cerrado | m_fub | m_par)

    motor = cola["motor_derivada_rnpdno_banci"]
    orden = [m for m in ("estandar", "refinado", "estandar, refinado") if m in set(motor)]
    resumen = pd.DataFrame({
        "en la cola": motor.value_counts(),
        "caso cerrado por el Secretariado": motor[m_cerrado].value_counts(),
        "FUB ya emparejado": motor[m_fub].value_counts(),
        "par ya rechazado": motor[m_par].value_counts(),
        "a revisión": motor[queda].value_counts(),
    }).reindex(orden).fillna(0).astype(int)
    resumen.loc["total"] = resumen.sum()
    resumen = resumen.rename_axis("motor_origen").reset_index()

    # ── La base ──────────────────────────────────────────────────────────────
    sel = cola[queda].reset_index(drop=True)
    pos = sel["fila_derivada_banci"].to_numpy()
    out = pd.DataFrame({"motor_origen": sel["motor_derivada_rnpdno_banci"]})
    for c in _TRAZA:
        out[c] = sel[f"{c}_derivada_rnpdno_banci"]
    out[respuesta] = ""                     # la respuesta del revisor: SI / NO
    for c in _VERIF:
        out[c] = sel[f"{c}_derivada_rnpdno_banci"]
    out["id_registro_banci"] = id_registro_banci(ba).to_numpy()[pos]
    out["fila_origen_banci"] = pos + 2      # renglón en la hoja de BANCI (1 = encabezado)
    for destino_col, col in _COLS_BANCI.items():
        out[destino_col] = ba[col].to_numpy()[pos]
    out["fub_rnpdno"] = sel["fub_derivada_rnpdno_banci"]
    rn_por_fub = rn.drop_duplicates(subset=["fub_rnpdno"]).set_index("fub_rnpdno")
    for destino_col, col in _COLS_RNPDNO.items():
        out[destino_col] = out["fub_rnpdno"].map(rn_por_fub[col]).to_numpy()

    corte = _corte(Path(config.RNPDNO_MANUAL_FILE_2))
    destino = Path(destino) if destino else config.OUTPUT_DIR / "revision_sesnsp" / cfg.perfil
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"{prefijo}_{corte}.xlsx"
    with pd.ExcelWriter(archivo, engine="openpyxl") as w:
        out.to_excel(w, sheet_name="revision", index=False)
        resumen.to_excel(w, sheet_name="resumen", index=False)

    if verbose:
        print(f"📝 Base de {titulo} → {archivo}")
        print(resumen.to_string(index=False))
        print(f"\n   {len(out):,} pares · {out['id_registro_banci'].nunique():,} registros de "
              f"BANCI · {out['fub_rnpdno'].nunique():,} FUB")

    if validar:
        _validar_ida_y_vuelta(archivo, respuesta, ba_motor, pos, verbose)

    return ResultadoRevision(archivo=archivo, base=out, resumen=resumen)


def _validar_ida_y_vuelta(archivo: Path, respuesta: str, ba_motor: pd.DataFrame, pos,
                          verbose: bool) -> None:
    """Relee el archivo como si el Secretariado lo hubiera contestado y comprueba que
    cada renglón se liga con SU registro de BANCI, que es lo que hará el motor manual.

    Un renglón que no se liga no es un error del archivo: es una carpeta colectiva donde
    ninguna llave distingue a la víctima. Su respuesta no se aplicaría sola, y conviene
    saberlo antes de mandarlo.
    """
    if respuesta == "VALIDO":
        rev = leer_revisiones_sesnsp(archivo, None, hoja_verif=0, skiprows_verif=0,
                                     verbose=False)
    else:
        rev = leer_revisiones_sesnsp(None, archivo, hoja_revision=0, skiprows_revision=0,
                                     verbose=False)
    ligado = resolver_revisiones_a_banci(ba_motor, rev, verbose=False)
    esperado = pd.Series(pos, index=rev.index)
    malos = ligado.notna() & (ligado != esperado)
    if malos.any():
        raise AssertionError(
            f"❌ {int(malos.sum()):,} renglones de {archivo.name} se ligan con OTRO registro "
            "de BANCI: la respuesta del Secretariado se aplicaría a la persona equivocada."
        )
    sin_ligar = int(ligado.isna().sum())
    if verbose:
        print(f"\n🔎 Ida y vuelta: {len(rev) - sin_ligar:,} de {len(rev):,} renglones se "
              f"ligan con su registro de BANCI.")
        if sin_ligar:
            print(f"   ⚠️ {sin_ligar:,} no se pueden ligar (carpeta colectiva sin llave que "
                  "distinga a la víctima): su respuesta no se aplicaría sola.")
