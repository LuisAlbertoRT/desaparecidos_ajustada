"""Validaciones de contenido de BANCI, pensadas para cuando llega una entrega nueva.

`src/validacion.py` exige archivo, hoja y columnas. Esto revisa lo que trae el archivo
y lo compara con la entrega anterior, para que un archivo equivocado (más viejo,
recortado, de otra ventana de fechas) detenga el notebook 2 en vez de cambiar las
cifras sin que nadie lo note.

LA ENTREGA ANTERIOR
-------------------
El notebook 2 guarda un resumen de la BANCI que procesó en los metadatos de
`Resultado_2_Procesamiento_ETL_BANCI.parquet` (`escribir_parquet`). La siguiente corrida
lo lee (`leer_referencia`) y compara. Si el Parquet no lo trae (se escribió antes de
que existiera esto), el resumen se reconstruye con sus columnas `_banci`.

LA FECHA DE CORTE
-----------------
Es la fecha de inicio (`fha_de_ini`) más reciente: en todas las entregas cae en el
último día del mes que cubren (31-ene, 28-feb, …, 31-jul-2026). Con ella se distingue
una entrega de OTRA fecha, que tiene que traer más registros, de una versión corregida
del MISMO corte, que puede traer unos menos (mayo de 2026 llegó dos veces: la segunda
con 12 registros menos). Una fecha de inicio posterior al día en que se procesa la
entrega es un error de captura y no cuenta para el corte: agosto de 2026 trajo un 5 de
octubre, que habría hecho que la entrega de septiembre pareciera más vieja.

QUÉ NO SE COMPARA
-----------------
`LLAVE`: el Secretariado la regenera en cada entrega (de junio a julio de 2026 sólo
se conservó el 5 %). Tampoco los nombres de entidad tal cual: cambian de una entrega a
otra ("MÉXICO", "ESTADO DE MÉXICO", "MEXICO"), así que se comparan por clave INEGI.

Los umbrales están calibrados con las siete entregas de enero a julio de 2026.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import config
from src.pipeline.derivadas import _MAPA_ENTIDAD, _norm
from src.validacion import InsumoInvalido

# Clave de los metadatos del Parquet donde viaja el resumen de la entrega.
_CLAVE_METADATOS = b"banci_resumen"

# Estatus que entiende el pipeline (`derivadas.derivar_banci` busca "localiza" y
# "no localiza"). Un valor fuera de aquí se contaría en silencio como desaparecido.
_PATRON_ESTATUS = re.compile(r"^(NO )?LOCALIZAD[AO]S?$")
# Categorías de sexo vistas en las entregas. Una nueva no rompe nada, pero se avisa:
# en enero de 2026 llegaron códigos ("1", "2", "3") en lugar de texto.
_SEXOS_CONOCIDOS = {"HOMBRE", "MUJER", "SE DESCONOCE", "NO ESPECIFICA", "NO ESPECIFICADO"}

UMBRAL_LLAVE_VACIA = 0.05      # febrero de 2026 llegó con el 89 % vacío
UMBRAL_CRECIMIENTO = 0.50      # el mayor fue +58 %, cuando cambió la ventana de fechas
UMBRAL_BAJA_ENTIDAD = 0.05     # una entidad que pierde más de esto…
MINIMO_BAJA_ENTIDAD = 10       # …y al menos estos registros


def _fechas(s: pd.Series) -> pd.Series:
    """Fechas como vengan: fecha de Excel, texto o número de serie de Excel."""
    f = pd.to_datetime(s, errors="coerce", utc=True)
    num = pd.to_numeric(s, errors="coerce")
    serie = pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce", utc=True)
    return f.where(f.notna(), serie.where(num.between(1, 100_000)))


def _texto(s: pd.Series) -> pd.Series:
    return s.map(lambda v: "" if pd.isna(v) else _norm(v))


def _inicio_valido(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Fechas de inicio, y las que caen después de hoy (errores de captura)."""
    ini = _fechas(df["fha_de_ini"])
    futuras = ini > pd.Timestamp(datetime.now().date(), tz="UTC")
    return ini.where(~futuras), ini[futuras]


def resumir(df: pd.DataFrame, archivo) -> dict:
    """Resumen de una entrega de BANCI, con los nombres internos de columna."""
    ini, _ = _inicio_valido(df)
    cve = _texto(df["entidad"]).map(_MAPA_ENTIDAD)
    return {
        "archivo": Path(archivo).name,
        "procesado": datetime.now().isoformat(timespec="seconds"),
        "filas": int(len(df)),
        "fecha_corte": None if ini.isna().all() else ini.max().strftime("%Y-%m-%d"),
        "fecha_inicio_min": None if ini.isna().all() else ini.min().strftime("%Y-%m-%d"),
        "por_entidad": {str(int(k)): int(v) for k, v in cve.value_counts().items()},
    }


def leer_referencia(ruta_parquet) -> Optional[dict]:
    """El resumen de la última BANCI procesada, o None si nunca se procesó una."""
    ruta = Path(ruta_parquet)
    if not ruta.exists():
        return None
    meta = pq.read_schema(ruta).metadata or {}
    if _CLAVE_METADATOS in meta:
        return json.loads(meta[_CLAVE_METADATOS])
    # Parquet anterior a este módulo: se reconstruye con las columnas tal como vinieron.
    cols = {"fha_de_ini_banci": "fha_de_ini", "entidad_banci": "entidad"}
    df = pd.read_parquet(ruta, columns=list(cols)).rename(columns=cols)
    ref = resumir(df, "(reconstruido de " + ruta.name + ")")
    ref["procesado"] = None
    return ref


def escribir_parquet(df: pd.DataFrame, ruta, resumen: dict) -> None:
    """`df.to_parquet`, con el resumen de la entrega en los metadatos del archivo."""
    tabla = pa.Table.from_pandas(df, preserve_index=False)
    meta = dict(tabla.schema.metadata or {})
    meta[_CLAVE_METADATOS] = json.dumps(resumen, ensure_ascii=False).encode("utf-8")
    pq.write_table(tabla.replace_schema_metadata(meta), ruta)


def validar(df: pd.DataFrame, archivo, referencia: Optional[dict] = None,
            estricta: bool = True, verbose: bool = True) -> dict:
    """Revisa la entrega y la compara con `referencia`. Devuelve su resumen.

    Con `estricta=True` un error detiene el proceso (InsumoInvalido); con False sólo
    se avisa. Los avisos nunca detienen: son cosas que pueden ser legítimas pero que
    alguien tiene que ver antes de publicar cifras.
    """
    res = resumir(df, archivo)
    errores, avisos = [], []

    # ── La entrega por sí sola ───────────────────────────────────────────────
    if res["filas"] == 0:
        errores.append("El archivo no trae registros.")

    ini, futuras = _inicio_valido(df)
    ilegibles = int((ini.isna() & ~ini.index.isin(futuras.index)).sum())
    if len(futuras):
        avisos.append(f"{len(futuras):,} fechas de inicio posteriores a hoy "
                      f"({', '.join(sorted(futuras.dt.strftime('%Y-%m-%d').unique())[:3])}): "
                      "error de captura; no cuentan para el corte.")
    if res["fecha_corte"] is None:
        errores.append("Ninguna fecha de inicio (FHA_DE_INI) se pudo leer: no se puede saber "
                       "de qué corte es la entrega.")
    elif ilegibles:
        avisos.append(f"{ilegibles:,} registros sin fecha de inicio legible.")

    estatus = _texto(df["localizado_o_no_localizado"])
    raros = estatus[~estatus.str.match(_PATRON_ESTATUS)].replace("", "(vacío)")
    if len(raros):
        errores.append(
            f"{len(raros):,} registros con estatus de localización que el pipeline no "
            f"entiende, y que contaría como desaparecidos: {raros.value_counts().head(5).to_dict()}.")

    ent = _texto(df["entidad"])
    sin_clave = ent[ent.map(_MAPA_ENTIDAD).isna()].replace("", "(vacío)")
    if len(sin_clave):
        errores.append(
            f"{len(sin_clave):,} registros con una entidad que no tiene clave INEGI: "
            f"{sin_clave.value_counts().head(5).to_dict()}. Quedarían fuera de los reportes "
            "estatales; agrega el alias a `_MAPA_ENTIDAD` en src/pipeline/derivadas.py.")

    sexo = _texto(df["sexo"])
    nuevos = sexo[(sexo != "") & ~sexo.isin(_SEXOS_CONOCIDOS)]
    if len(nuevos):
        avisos.append(f"Categorías de sexo nuevas: {nuevos.value_counts().head(5).to_dict()}.")

    vacias = df["llave"].isna() | (df["llave"].astype(str).str.strip() == "")
    if vacias.mean() > UMBRAL_LLAVE_VACIA:
        errores.append(f"{int(vacias.sum()):,} registros ({vacias.mean():.0%}) sin LLAVE.")
    elif vacias.any():
        avisos.append(f"{int(vacias.sum()):,} registros sin LLAVE.")

    if res["fecha_corte"]:
        hechos = _fechas(df["fha_de_hchos"])
        futuras = int((hechos > pd.Timestamp(res["fecha_corte"], tz="UTC")).sum())
        if futuras:
            avisos.append(f"{futuras:,} fechas de hechos posteriores al corte "
                          f"({res['fecha_corte']}); el notebook les resta años.")

    # ── Contra la entrega anterior ───────────────────────────────────────────
    comparacion = "sin entrega anterior: esta queda como referencia"
    if referencia and referencia.get("fecha_corte") and res["fecha_corte"]:
        ant, nue = referencia["fecha_corte"], res["fecha_corte"]
        n_ant, n_nue = referencia["filas"], res["filas"]
        if nue < ant:
            errores.append(f"La entrega es de un corte ANTERIOR ({nue}) al de la última "
                           f"procesada ({ant}, {referencia['archivo']}). ¿Es el archivo correcto?")
            comparacion = "corte anterior"
        elif nue == ant:
            comparacion = "mismo corte"
            if n_nue != n_ant:
                avisos.append(f"Mismo corte ({nue}) que la última procesada, pero con "
                              f"{n_nue - n_ant:+,} registros: ¿versión corregida?")
        else:
            comparacion = "corte nuevo"
            if n_nue <= n_ant:
                errores.append(f"De un corte a otro la base tiene que crecer, y bajó o se quedó "
                               f"igual: {n_ant:,} ({ant}) → {n_nue:,} ({nue}).")
            elif n_nue / n_ant - 1 > UMBRAL_CRECIMIENTO:
                avisos.append(f"Creció {n_nue / n_ant - 1:.0%} ({n_ant:,} → {n_nue:,}); "
                              "revisa que sea la misma base y no otra más amplia.")
            meses = (pd.Timestamp(nue, tz="UTC").to_period("M") - pd.Timestamp(ant, tz="UTC").to_period("M")).n
            if meses > 1:
                avisos.append(f"Entre {ant} y {nue} hay {meses} meses: ¿falta una entrega?")
            if res["fecha_inicio_min"] != referencia.get("fecha_inicio_min"):
                avisos.append(f"Cambió la fecha de inicio más antigua "
                              f"({referencia.get('fecha_inicio_min')} → {res['fecha_inicio_min']}): "
                              "la entrega cubre otra ventana.")
            pe_ant, pe_nue = referencia.get("por_entidad", {}), res["por_entidad"]
            for cve, n in sorted(pe_ant.items(), key=lambda kv: int(kv[0])):
                m = pe_nue.get(cve, 0)
                nombre = config.ENTIDADES.get(int(cve), cve)
                if m == 0 and n >= MINIMO_BAJA_ENTIDAD:
                    errores.append(f"La entidad {nombre} desaparece ({n:,} → 0 registros).")
                elif n - m >= MINIMO_BAJA_ENTIDAD and (n - m) / n > UMBRAL_BAJA_ENTIDAD:
                    avisos.append(f"La entidad {nombre} baja {(n - m) / n:.0%} ({n:,} → {m:,}).")

    if verbose:
        print(f"\n🔎 Validación de la entrega de BANCI: {res['archivo']}")
        print(f"   {res['filas']:,} registros · corte {res['fecha_corte']} · "
              f"inicio desde {res['fecha_inicio_min']} · {len(res['por_entidad'])} entidades")
        if referencia:
            print(f"   Anterior: {referencia['archivo']} · {referencia['filas']:,} registros · "
                  f"corte {referencia.get('fecha_corte')} → {comparacion}")
        else:
            print(f"   {comparacion}")
        for a in avisos:
            print(f"   ⚠️ {a}")
        for e in errores:
            print(f"   ❌ {e}")
        if not errores and not avisos:
            print("   ✅ Sin observaciones.")

    if errores:
        mensaje = ("❌ La entrega de BANCI no pasó las validaciones:\n"
                   + "\n".join(f"   - {e}" for e in errores)
                   + "\n   Revisa config.BANCI_FILE. Si ya sabes por qué la entrega es así, "
                     "config.VALIDACION_BANCI_ESTRICTA = False deja pasar con aviso.")
        if estricta:
            raise InsumoInvalido(mensaje)
        print(mensaje.replace("❌", "⚠️", 1) + "\n   (modo no estricto: se continúa)")
    return res
