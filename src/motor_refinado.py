"""
motor_refinado.py
=================
Motor de matching "refinado" basado en la lógica de normalizar_folios_v6.py.

Implementa el cruce por normalización de folios de carpeta, CURP, nombre
y FUB, con guardianes anti-homónimo y scoring ponderado.

Firma estándar del motor (compatible con MultiMatchOrchestrator):
    motor_match_refinado(df_banci, df_rnpdno, **kwargs) -> pd.DataFrame

Salida
------
El DataFrame devuelto tiene el mismo índice que df_banci y contiene:
    id_match_refinado         fub del RNPDNO emparejado (o None)
    tipo_match_refinado       'definitivo' | 'parcial (algun caracter distinto)' |
                              'revision manual' | 'sin_match'
    score_refinado            puntaje 0-100
    variables_match_refinado  descripción del cruce
    evaluacion_match_refinado alias de tipo_match_refinado
    fecha_hechos_status_refinado estado de la fecha de hechos como soporte
    verif_*_refinado          verificaciones descriptivas por variable

Parámetros opcionales (kwargs)
-------------------------------
    conf_banci       : set de índices de df_banci ya confirmados (no se vuelven a proponer)
    conf_fub         : set de fub del RNPDNO ya emparejados (no se vuelven a proponer)
    pares_rechazados : set de (índice de df_banci, fub_rnpdno) ya descartados
    ruta_verif_fecha_hechos  : Path al Excel matches_verif_fecha_hechos_SESNSP.xlsx
    ruta_revision_manual     : Path al Excel revision_manual_score_SESNSP.xlsx
    hoja_verif    : hoja del primer archivo (default 0)
    hoja_revision : hoja del segundo archivo (default 1)

Insumos necesarios
------------------
Colocar en config.REFINADO_REVISIONES_DIR (ver config.py):
    - matches_verif_fecha_hechos_SESNSP.xlsx   (revisiones de fecha de hechos, SESNSP)
    - revision_manual_score_SESNSP.xlsx        (revisiones manuales por score, SESNSP)
Ambos son OPCIONALES. Si no existen, el descuento se omite silenciosamente.

Prerrequisitos
--------------
Los DataFrames de entrada deben ser los ya procesados por el ETL:
    - df_banci  : salida de 2_Procesamiento_ETL_BANCI.ipynb  (No Localizados del sexenio)
    - df_rnpdno : salida de 1_Procesamiento_ETL_RNPDNO.ipynb (Desaparecidos/Pendientes
                  del sexenio, ya filtrados por fecha_hechos_modificada >= 2024-10-01)
El motor NO modifica los DataFrames de entrada.

Nota sobre normalizar_folios_v4_excel
--------------------------------------
El script original normalizar_folios_v6.py importa el módulo externo
normalizar_folios_v4_excel para normalización de folios, similitud de nombres y
detección de columnas. Este motor reimplementa toda esa funcionalidad internamente
para ser completamente autosuficiente dentro del proyecto.
La lógica de matching (umbrales, guardianes, scoring y salidas) es idéntica a v6.
"""

from __future__ import annotations

import re
import time as _time
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import pandas as pd


class _ProgressBar:
    """
    Barra de progreso compatible con Jupyter / VS Code.
    Imprime una línea nueva por cada ~5 % de avance (sin \\r ni overwriting,
    que no funcionan en las celdas de Jupyter).
    """
    def __init__(self, total: int, desc: str = ""):
        self.total      = total
        self.desc       = desc
        self._count     = 0
        self._t0        = _time.monotonic()
        self._last_pct5 = -1          # último múltiplo de 5 % reportado

    def update(self, n: int = 1) -> None:
        self._count += n
        pct      = int(100.0 * self._count / self.total)
        pct5     = pct // 5           # múltiplo de 5 actual
        finished = self._count >= self.total

        # Imprimir en cada nuevo múltiplo de 5 % o al terminar
        if pct5 > self._last_pct5 or finished:
            self._last_pct5 = pct5
            elapsed = _time.monotonic() - self._t0
            rate    = self._count / elapsed if elapsed > 0 else 1e-9
            remain  = (self.total - self._count) / rate
            filled  = int(25 * self._count / self.total)
            bar     = "█" * filled + "░" * (25 - filled)

            if finished:
                print(f"  {self.desc} [{'█' * 25}] 100.0%  "
                      f"{self.total:,}/{self.total:,}  "
                      f"completado en {elapsed:.1f}s")
            else:
                print(f"  {self.desc} [{bar}] {pct:5.1f}%  "
                      f"{self._count:,}/{self.total:,}  "
                      f"~{remain:.0f}s restantes")


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTES (idénticas a normalizar_folios_v6.py — no modificar sin actualizar v6)
# ──────────────────────────────────────────────────────────────────────────────

UMBRAL_NOMBRE_100          = 0.90   # sólo para la etiqueta verif_nombre
UMBRAL_NOMBRE_MIN          = 0.50   # piso para que el nombre CUENTE en scoring
UMBRAL_NOMBRE_SOLO         = 0.66   # nombre >= ~67% basta SOLO para revisión
CORROBORADORES_MIN_CARPETA = 2      # variables extra exigidas sin nombre suficiente
LONGITUD_CONSEC_ESPECIFICO = 4      # consecutivo >= 4 dígitos: admite revisión solo
MAX_BLOQUE_NOMBRE          = 3000   # máx registros por bloque de apellido
# ── Constantes transcritas de normalizar_folios_v4_excel.py ──────────────────
# v6 importa ese módulo; aquí se replica su lógica para no depender de un archivo
# en notebooks/. Los valores DEBEN coincidir: son los que deciden qué se considera
# código de oficina y qué token numérico es año.
UMBRAL_TOKEN_CODIGO_OFICINA = 20    # v4: mínimo de folios DISTINTOS para ser oficina
ANIO_MIN, ANIO_MAX = 1990, 2035     # rango que cuenta como "año de carpeta"
MIN_DIGITOS_CONSECUTIVO_CONFIABLE = 3

W_FOLIO_LIMPIO  = 45
W_FOLIO_PARCIAL = 25
W_CURP10        = 25
W_FNAC          = 15
W_NOMBRE        = 25
W_MUNICIPIO     = 8
UMBRAL_MUNICIPIO = 0.80
MIN_TOKENS_NOMBRE = 2
UMBRAL_NOMBRE_EXACTO = 0.999
DIAS_FHECHOS_EXIGE_FNAC = 360
VENTANA_FECHA_HECHOS_DIAS = 10
W_ENTIDAD  = 3
W_SEXO     = 2
W_PUENTE   = 15

# Partículas y abreviaturas: transcritas de v4. La lista NO es la "obvia": es la
# que usa el original, y cambiarla mueve `similitud_nombres` y con ella el umbral
# de 0.66 que separa definitivo de revisión.
_PARTICULAS_NOMBRE: FrozenSet[str] = frozenset({
    "DE", "DEL", "LA", "LAS", "LOS", "Y", "MC", "VAN", "DA", "DI", "SAN",
})
# Abreviaturas frecuentes en registros mexicanos: se expanden ANTES de comparar,
# así "MA GUADALUPE" y "MARIA GUADALUPE" cuentan como el mismo token.
_ABREV_NOMBRE: Dict[str, str] = {
    "MA": "MARIA", "GPE": "GUADALUPE", "FCO": "FRANCISCO",
    "FRANC": "FRANCISCO", "JOSF": "JOSEFINA",
}

# ──────────────────────────────────────────────────────────────────────────────
# CANDIDATOS DE COLUMNAS
# (orden de preferencia: columnas derivadas del ETL primero, luego crudas)
# ──────────────────────────────────────────────────────────────────────────────

# Folio / carpeta de investigación
_C_FOLIO_BANCI = [
    # NTRA_CI = Número de Trámite de Carpeta de Investigación (columna real de carpeta)
    # Es la que hace match con expediente del RNPDNO. El ETL la mapea como ntra_ci_derivada_banci.
    "ntra_ci_derivada_banci", "ntra_ci", "NTRA_CI",
    "llave", "carpeta_investigacion", "no_averiguacion", "num_averiguacion",
    "folio_carpeta", "clave_carpeta", "carpeta", "nuc",
    "folio_carpeta_banci", "folio_investigacion", "carpeta_banci",
]
_C_FOLIO_RNPDNO = [
    "expediente", "folio", "carpeta", "folio_carpeta",
    "expediente_rnpdno", "nuc_rnpdno", "folio_rnpdno_carpeta",
]
# Identificador secundario de carpeta en BANCI (sirve cuando el folio es muy corto)
_C_ID_CI = ["id_ci_derivada_banci", "id_ci", "id_ci_banci", "idci"]

# FUB / folio RNPDNO ya asignado en BANCI
_C_FUB_BANCI = [
    "fub_banci", "fub_derivada_banci", "folio_rnpdno", "fub",
    "folio_rnpdno_banci", "fub_ok",
]
# FUB del registro RNPDNO (identificador único de persona)
_C_FUB_RNPDNO = [
    "fub_derivada_rnpdno", "fub_rnpdno", "fub",
    "id_persona_rnpdno", "folio_fub",
]
# Nombre completo
_C_NOMBRE_BANCI  = ["nombre_completo_derivada_banci",  "nombre_completo_banci",  "nombre_completo", "nombres"]
_C_NOMBRE_RNPDNO = ["nombre_completo_derivada_rnpdno", "nombre_completo_rnpdno", "nombre_completo", "nombre_vic"]

# Primer apellido (para índice de bloqueo)
_C_APEPAT_BANCI  = ["primer_apellido_derivada_banci",  "primer_apellido", "paterno", "apellido_paterno"]
_C_APEPAT_RNPDNO = ["primer_apellido_derivada_rnpdno", "primerapellido_vic", "primer_apellido"]

# CURP
_C_CURP_BANCI  = ["curp_banci",  "curp_limpia", "curp", "curp_victima"]
_C_CURP_RNPDNO = ["curp_vic_rnpdno", "curp_limpia_rnpdno", "curp_vic", "curp"]

# Fecha de nacimiento
_C_FNAC_BANCI  = ["fechanacimiento_derivada_banci",  "fha_nac", "fecha_nacimiento", "fechanacimiento"]
_C_FNAC_RNPDNO = ["fechanacimiento_derivada_rnpdno", "fechanacimiento", "fecha_nacimiento"]

# Fecha de hechos / desaparición
_C_FHEC_BANCI  = ["fecha_hechos_derivada_banci",  "fha_de_hchos", "fecha_hechos", "fechahechos"]
_C_FHEC_RNPDNO = ["fecha_hechos_modificada", "fechahechos_derivada_rnpdno", "fechahechos", "fecha_hechos"]

# Entidad federativa
_C_ENTIDAD_BANCI  = ["entidad_derivada_banci",  "entidad", "entidad_federativa", "estado_reporta"]
_C_ENTIDAD_RNPDNO = ["estado_derivada_rnpdno",  "idestado_derivada_rnpdno", "idestado", "estado", "entidad"]

# Municipio de desaparición.
# SÓLO nombres: `_muni_igual` compara con fuzzy match (UMBRAL_MUNICIPIO = 0.80),
# pensado para variantes ortográficas ("GENERAL ESCOBEDO" vs "ESCOBEDO"). Las claves
# numéricas (`id_mun_hchos` de BANCI, `idmunicipio` del RNPDNO) NO comparten
# codificación —su intersección literal es cero— y además el RNPDNO las trae con
# formato float ("75.0"), así que incluirlas dejaba `_muni_igual` siempre en False.
_C_MUNICIPIO_BANCI  = ["nom_mun_hchos_derivada_banci",  "nom_mun_hchos", "municipio", "municipio_hechos"]
_C_MUNICIPIO_RNPDNO = ["municipio_derivada_rnpdno", "municipio", "nom_mun"]

# Sexo
_C_SEXO_BANCI  = ["sexo_derivada_banci",  "sexo"]
_C_SEXO_RNPDNO = ["sexo_derivada_rnpdno", "sexo"]

# Identificador único de registro/persona (para el descuento)
_C_IDREG_BANCI  = ["id_registro_banci",  "id_registro", "id_persona_banci",  "id_persona"]

# ──────────────────────────────────────────────────────────────────────────────
# NORMALIZACIÓN DEL RNPDNO: mapa de ID numérico → nombre de entidad
# ──────────────────────────────────────────────────────────────────────────────
_ENTIDAD_NUM_MAP: Dict[str, str] = {
    "1": "AGUASCALIENTES", "2": "BAJA CALIFORNIA", "3": "BAJA CALIFORNIA SUR",
    "4": "CAMPECHE", "5": "COAHUILA", "6": "COLIMA", "7": "CHIAPAS",
    "8": "CHIHUAHUA", "9": "CIUDAD DE MEXICO", "10": "DURANGO",
    "11": "GUANAJUATO", "12": "GUERRERO", "13": "HIDALGO", "14": "JALISCO",
    "15": "ESTADO DE MEXICO", "16": "MICHOACAN", "17": "MORELOS",
    "18": "NAYARIT", "19": "NUEVO LEON", "20": "OAXACA", "21": "PUEBLA",
    "22": "QUERETARO", "23": "QUINTANA ROO", "24": "SAN LUIS POTOSI",
    "25": "SINALOA", "26": "SONORA", "27": "TABASCO", "28": "TAMAULIPAS",
    "29": "TLAXCALA", "30": "VERACRUZ", "31": "YUCATAN", "32": "ZACATECAS",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE TEXTO
# ══════════════════════════════════════════════════════════════════════════════

def _quitar_acentos(texto: str) -> str:
    """Quita diacríticos conservando el resto del carácter (transcrito de v4).

    Usa NFKD y descarta las marcas combinantes, NO `encode('ascii','ignore')`:
    esa variante además borra cualquier carácter no-ASCII que no se descomponga,
    lo que cambia tokens de nombre y de folio.
    """
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _es_anio(token: str) -> bool:
    """True si el token es un año de carpeta (4 dígitos dentro de ANIO_MIN..MAX)."""
    return token.isdigit() and len(token) == 4 and ANIO_MIN <= int(token) <= ANIO_MAX


def _pelar_anio_pegado(run: str) -> Tuple[str, str, str]:
    """Separa el año (y el mes) pegados al final de un run largo de dígitos.

    Caso real: '1214162025' = consecutivo 121416 + año 2025; y el patrón CDMX
    '...\\d{5}-MM-AAAA' capturado sin guiones. Devuelve (consecutivo, anio, mes),
    con anio/mes vacíos si no se detectaron.
    """
    m = re.match(r"^(\d{3,})(0[1-9]|1[0-2])((?:19|20)\d{2})$", run)
    if m and ANIO_MIN <= int(m.group(3)) <= ANIO_MAX:
        return m.group(1), m.group(3), m.group(2)
    m = re.match(r"^(\d{3,})((?:19|20)\d{2})$", run)
    if m and ANIO_MIN <= int(m.group(2)) <= ANIO_MAX:
        return m.group(1), m.group(2), ""
    return run, "", ""


def _limpia_curp(s) -> str:
    """Elimina todo carácter que no sea letra o dígito y convierte a mayúsculas."""
    return re.sub(r"[^A-Z0-9]", "", _quitar_acentos(str(s)).upper())


def _detectar_col(df: pd.DataFrame, candidatas: List[str]) -> str:
    """
    Devuelve el nombre de la primera columna candidata encontrada en el DataFrame,
    normalizando espacios, puntos y guiones para la comparación.
    Devuelve '' si ninguna candidata coincide.
    """
    def _k(x: str) -> str:
        return re.sub(r"[\s._-]+", "", str(x)).upper()
    mapa = {_k(c): c for c in df.columns}
    for cand in candidatas:
        if _k(cand) in mapa:
            return mapa[_k(cand)]
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE FOLIOS
# ══════════════════════════════════════════════════════════════════════════════

def normalizar_folio(folio, tokens_ignorar: FrozenSet[str] = frozenset()) -> dict:
    """Extrae la LLAVE de match de un folio de carpeta de investigación.

    Transcripción de `normalizar_folio` de normalizar_folios_v4_excel.py, que es la
    que usa normalizar_folios_v6.py. Los pasos, en orden, porque cada uno cambia el
    resultado:

      1. Mayúsculas sin acentos; los separadores (- / _ . espacios , ; : #) parten
         tokens, y además se corta en la frontera letra/dígito.
      2. Tokens alfabéticos → claves de oficina (se reportan, no son llave).
      3. Tokens de 4 dígitos dentro de ANIO_MIN..ANIO_MAX → año (no es llave).
      4. En runs de >= 7 dígitos se PELA el año (y el mes) pegado al final.
      5. Un token de mes (01-12) ADYACENTE a un año se descarta; si al quitarlo el
         folio se queda sin candidatos ("12/2024"), se restaura: no era mes.
      6. `consecutivo_alt` sólo para runs >= 11 dígitos con el año EN MEDIO.
      7. Los códigos de oficina se descartan sólo si queda algún candidato.
      8. Consecutivo = el token numérico MÁS LARGO; empate → el ÚLTIMO.
      9. Un consecutivo de PUROS CEROS no es folio: devuelve llave vacía. Sin esta
         regla todos los folios '0' casan entre sí y generan falsos masivos.
     10. Se quitan los ceros a la izquierda ('00001' → '1').
    """
    resultado = {
        "consecutivo": "", "consecutivo_crudo": "", "consecutivo_alt": "",
        "anio": "", "mes": "", "claves_detectadas": "", "otros_numericos": "",
        "codigos_oficina": "", "confianza": "baja", "motivo_confianza": "",
    }
    if folio is None or (isinstance(folio, float) and pd.isna(folio)):
        resultado["motivo_confianza"] = "folio vacio"
        return resultado

    crudo = _quitar_acentos(str(folio)).upper().strip()
    if not crudo:
        resultado["motivo_confianza"] = "folio vacio"
        return resultado

    plano = re.sub(r"[-/_\.\s,;:#]+", " ", crudo)
    tokens = re.findall(r"[A-Z]+|\d+", plano)

    claves, numericos = [], []
    for tk in tokens:
        (claves if tk.isalpha() else numericos).append(tk)

    # pelar año/mes pegados SÓLO en runs largos (>= 7 dígitos: 3 de folio + 4 de año)
    numericos_peludos = []
    for run in numericos:
        if len(run) >= 7:
            cons, anio, mes = _pelar_anio_pegado(run)
            numericos_peludos.append(cons)
            if anio and not resultado["anio"]:
                resultado["anio"], resultado["mes"] = anio, mes
        else:
            numericos_peludos.append(run)

    # separar años y meses que vienen como token propio
    meses_validos = {f"{m:02d}" for m in range(1, 13)}
    candidatos, anios, meses_omitidos = [], [], []
    for i, tk in enumerate(numericos_peludos):
        if _es_anio(tk):
            anios.append(tk)
        elif tk in meses_validos and (
                (i + 1 < len(numericos_peludos) and _es_anio(numericos_peludos[i + 1]))
                or (i > 0 and _es_anio(numericos_peludos[i - 1]))):
            meses_omitidos.append(tk)
        else:
            candidatos.append(tk)

    # si quitar el "mes" deja SIN candidatos (folio tipo "12/2024"), ese número no
    # era mes sino el consecutivo mismo: se restaura.
    if not candidatos and meses_omitidos:
        candidatos = meses_omitidos

    if anios and not resultado["anio"]:
        resultado["anio"] = anios[-1]

    resultado["claves_detectadas"] = "|".join(claves)

    if not candidatos:
        resultado["motivo_confianza"] = "sin token numerico de consecutivo (solo claves/anio)"
        return resultado

    # LLAVE ALTERNATIVA: runs largos con el año EN MEDIO ("1009202509339" =
    # region|año|consecutivo). La principal conserva el run completo; la alterna
    # guarda el tramo posterior al año, por si la otra base sólo registra eso.
    for run in candidatos:
        if len(run) >= 11 and not resultado["consecutivo_alt"]:
            m = re.match(r"^(\d{2,6})((?:19|20)\d{2})(\d{3,})$", run)
            if m and ANIO_MIN <= int(m.group(2)) <= ANIO_MAX:
                resultado["consecutivo_alt"] = m.group(3).lstrip("0") or "0"
                if not resultado["anio"]:
                    resultado["anio"] = m.group(2)

    # códigos de oficina: se excluyen salvo que hacerlo deje al folio sin candidatos
    if tokens_ignorar:
        sin_codigos = [c for c in candidatos if c not in tokens_ignorar]
        if sin_codigos and len(sin_codigos) < len(candidatos):
            resultado["codigos_oficina"] = "|".join(c for c in candidatos if c in tokens_ignorar)
            candidatos = sin_codigos

    # consecutivo = token más largo; empate → el ÚLTIMO (el folio suele terminar
    # en consecutivo antes del año)
    max_len = max(len(c) for c in candidatos)
    consecutivo_crudo = [c for c in candidatos if len(c) == max_len][-1]
    otros = [c for c in candidatos if c != consecutivo_crudo]

    # PUROS CEROS = registro sin folio real. Dejarle llave "0" haría que todos
    # casaran entre sí (falsos positivos masivos).
    if set(consecutivo_crudo) == {"0"}:
        resultado["motivo_confianza"] = "folio de puros ceros = sin folio real (no matcheable)"
        return resultado

    resultado["consecutivo_crudo"] = consecutivo_crudo
    resultado["consecutivo"] = consecutivo_crudo.lstrip("0") or "0"
    resultado["otros_numericos"] = "|".join(otros)

    if len(resultado["consecutivo"]) < MIN_DIGITOS_CONSECUTIVO_CONFIABLE:
        resultado["confianza"] = "baja"
        resultado["motivo_confianza"] = (
            f"consecutivo de {len(resultado['consecutivo'])} digito(s): colisiona facil")
    elif otros and max(len(o) for o in otros) == max_len:
        resultado["confianza"] = "media"
        resultado["motivo_confianza"] = "dos tokens numericos del mismo largo; se tomo el ultimo"
    elif otros:
        resultado["confianza"] = "media"
        resultado["motivo_confianza"] = "hay otros tokens numericos; se tomo el mas largo"
    else:
        resultado["confianza"] = "alta"
        resultado["motivo_confianza"] = "consecutivo unico e inequivoco"

    return resultado


def _tokens_ignorar_de_serie(serie: Union[pd.Series, pd.DataFrame]) -> FrozenSet[str]:
    """
    Detecta códigos de oficina frecuentes en una serie de folios.
    Un token numérico que aparece en >= UMBRAL_TOKEN_CODIGO_OFICINA registros
    (o >= 0.05 % del total) se considera código de oficina y se ignora al
    extraer el consecutivo.
    """
    if isinstance(serie, pd.DataFrame):
        serie = serie.iloc[:, 0]
    conteo: Dict[str, int] = {}
    for f in serie.dropna().astype(str).unique():
        crudo = re.sub(r"[-/_\.\s,;:#]+", " ", _quitar_acentos(f).upper())
        for tk in set(re.findall(r"\d+", crudo)):
            if not _es_anio(tk):
                conteo[tk] = conteo.get(tk, 0) + 1
    umbral = max(UMBRAL_TOKEN_CODIGO_OFICINA, int(len(serie) * 0.0005))
    return frozenset(t for t, n in conteo.items() if n >= umbral)


# ══════════════════════════════════════════════════════════════════════════════
# SIMILITUD DE NOMBRES
# ══════════════════════════════════════════════════════════════════════════════

# Umbral de cobertura de un token por otro. Está aquí y no incrustado en el
# cuerpo porque la poda por cota superior (más abajo) depende de él.
UMBRAL_TOKEN_CUBIERTO = 0.85


@lru_cache(maxsize=300_000)
def _toks_nombre(x: str) -> Tuple[str, ...]:
    """Tokens comparables de un nombre. Memoizado: el mismo nombre de BANCI se
    compara contra miles de candidatos y antes se re-tokenizaba en cada par."""
    x = re.sub(r"[^A-Z\s]", " ", _quitar_acentos(str(x)).upper())
    return tuple(_ABREV_NOMBRE.get(w, w) for w in x.split()
                 if len(w) >= 2 and w not in _PARTICULAS_NOMBRE)


@lru_cache(maxsize=2_000_000)
def _ratio_token(w: str, x: str) -> float:
    """Ratio de difflib entre dos tokens, memoizado y con poda EXACTA.

    `SequenceMatcher.ratio()` es 2*M/T con M = caracteres coincidentes y
    T = len(w)+len(x). Como M nunca puede superar min(len(w), len(x)), el ratio
    está acotado por 2*min/(la+lb). Si esa cota ya queda por debajo del umbral,
    el par NO puede cubrir y se devuelve 0.0 sin llamar a difflib.

    Esto no cambia ningún resultado: el valor sólo se usa para elegir el mejor
    candidato CUANDO alguno alcanza el umbral, y un token que no llega a la cota
    tampoco llegaba al umbral. Lo que se ahorra son las comparaciones absurdas
    ("JOSE" contra "HERNANDEZ": cota 0.61), que son la mayoría.
    """
    if w == x:
        return 1.0
    la, lb = len(w), len(x)
    if 2.0 * min(la, lb) / (la + lb) < UMBRAL_TOKEN_CUBIERTO:
        return 0.0
    return SequenceMatcher(None, w, x).ratio()


@lru_cache(maxsize=500_000)
def _similitud_toks(ta: Tuple[str, ...], tb: Tuple[str, ...]) -> float:
    if not ta or not tb:
        return 0.0
    corto, largo = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    restantes, cubiertos = list(largo), 0
    for w in corto:
        mejor_i, mejor_r = -1, 0.0
        for i, x in enumerate(restantes):
            r = _ratio_token(w, x)
            if r > mejor_r:
                mejor_r, mejor_i = r, i
        if mejor_r >= UMBRAL_TOKEN_CUBIERTO:
            cubiertos += 1
            restantes.pop(mejor_i)
    return cubiertos / len(corto)


def similitud_nombres(nombre_a, nombre_b) -> float:
    """Similitud 0-1 entre dos nombres de PERSONA (transcrito de v4).

    Proporción de tokens del nombre MÁS CORTO cubiertos 1-a-1 por el otro, con
    coincidencia difusa (ratio SequenceMatcher >= 0.85: VASQUEZ/VAZQUEZ sí,
    CASTAN/CASTAÑO no). Tolera orden distinto y que una base traiga más tokens.
    Las abreviaturas se expanden antes de comparar.

    El resultado es idéntico al de la versión original; lo que cambia es que la
    tokenización, el ratio por token y el par completo están memoizados, y que
    los pares imposibles se descartan por cota antes de llamar a difflib. Era el
    cuello de botella del motor: se ejecuta una vez por PAR CANDIDATO, y el
    número de candidatos crece con el tamaño del RNPDNO.
    """
    return _similitud_toks(_toks_nombre(nombre_a), _toks_nombre(nombre_b))


# ══════════════════════════════════════════════════════════════════════════════
# NORMALIZACIÓN DE ENTIDAD Y SEXO
# ══════════════════════════════════════════════════════════════════════════════

# Alias de entidad → nombre canónico (transcrito de v4).
_ALIAS_ENTIDAD: Dict[str, str] = {
    "CDMX": "CIUDAD DE MEXICO", "DISTRITO FEDERAL": "CIUDAD DE MEXICO",
    "DF": "CIUDAD DE MEXICO", "EDOMEX": "MEXICO", "ESTADO DE MEXICO": "MEXICO",
    "MEXIQUE": "MEXICO", "BC": "BAJA CALIFORNIA", "BCS": "BAJA CALIFORNIA SUR",
    "NL": "NUEVO LEON", "QRO": "QUERETARO", "SLP": "SAN LUIS POTOSI",
    "MICHOACAN DE OCAMPO": "MICHOACAN", "VERACRUZ DE IGNACIO DE LA LLAVE": "VERACRUZ",
    "COAHUILA DE ZARAGOZA": "COAHUILA", "QUINTANAROO": "QUINTANA ROO",
}

# Sexo → H / M / "" (transcrito de v4). OJO con la convención: "M" es MUJER y
# "MASCULINO" es "H". No es la intuitiva, pero es la que usa el original y
# cambiarla desalinearía la comparación entre las dos bases.
_MAPA_SEXO: Dict[str, str] = {
    "H": "H", "HOMBRE": "H", "MASCULINO": "H", "M ASCULINO": "H", "VARON": "H",
    "MALE": "H",
    "M": "M", "MUJER": "M", "FEMENINO": "M", "FEMALE": "M", "F": "M",
}


def normalizar_entidad(entidad) -> str:
    """'Cd. de México ' / 'CDMX' → 'CIUDAD DE MEXICO' (transcrito de v4).

    Añadido sobre v4: si el valor es una CLAVE NUMÉRICA de entidad se traduce a
    nombre antes de normalizar. v4 borra los dígitos y devolvería '', así que este
    paso sólo cubre un caso que allá quedaba vacío; nunca altera un nombre.
    """
    if entidad is None or (isinstance(entidad, float) and pd.isna(entidad)):
        return ""
    e = _quitar_acentos(str(entidad)).upper().strip()
    if re.fullmatch(r"\d{1,2}", e):
        e = _ENTIDAD_NUM_MAP.get(e, e)
    e = re.sub(r"[^A-Z\s]", " ", e)
    e = re.sub(r"\s+", " ", e).strip()
    return _ALIAS_ENTIDAD.get(e, e)


def normalizar_sexo(sexo, usar_mf: bool = False) -> str:
    """Lleva el sexo a H / M / '' (transcrito de v4). Vacío nunca bloquea solo."""
    if sexo is None or (isinstance(sexo, float) and pd.isna(sexo)):
        return ""
    s = _quitar_acentos(str(sexo)).upper().strip()
    if usar_mf and s in {"M": "H", "F": "M"}:
        return {"M": "H", "F": "M"}[s]
    return _MAPA_SEXO.get(s, "")


# ══════════════════════════════════════════════════════════════════════════════
# CARGA DE REVISIONES SESNSP
# ══════════════════════════════════════════════════════════════════════════════

def _hash_norm(x) -> str:
    """Normaliza un identificador a mayúsculas. Devuelve '' si es nulo/vacío."""
    s = str(x).strip().upper()
    return "" if s in ("", "NAN", "NONE", "<NA>", "NA") else s


_DEFAULT_VERIF_CM = {
    "col_valido":     ["VALIDO", "Válido", "valido"],
    "col_reg_banci":  ["ID registro", "id_registro", "ID.registro",
                       "ID registro banci", "ID banci", "id_registro_banci"],
    "col_fub_rnpdno": ["FUB rnpdno", "fub_rnpdno", "FUB.rnpdno",
                       "ID rnpdno", "fub", "FUB"],
}
_DEFAULT_REVISION_CM = {
    "col_valido":     ["VALIDA", "Válida", "valida"],
    "col_reg_banci":  ["id_registro", "ID registro", "id_registro_banci", "ID.registro"],
    "col_fub_rnpdno": ["fub_rnpdno", "FUB rnpdno", "fub", "FUB"],
}

# Columnas del lado BANCI que traen los archivos de revisión. Se usan para volver a
# encontrar el registro cuando el `id_registro` del SESNSP no se puede cruzar (ver
# `resolver_revisiones_a_banci`). Los nombres se comparan normalizados, así que una
# sola entrada cubre las variantes con espacios ("Carpeta investigacion banci") y con
# guiones bajos ("carpeta_investigacion_banci").
_C_REV_CARPETA = ["carpeta_investigacion_banci", "carpeta_investigacion", "ntra_ci"]
_C_REV_CURP    = ["curp_limpia_banci", "curp_banci", "curp"]
_C_REV_NOMBRES = ["nombres_banci"]
_C_REV_APE1    = ["primer_apellido_banci"]
_C_REV_APE2    = ["segundo_apellido_banci"]
_C_REV_NOMCOMP = ["_nombre_completoBANCI", "nombre_completo_banci"]
_C_REV_FNAC    = ["fecha_nacimiento_banci"]
_C_REV_ENTIDAD = ["entidad_reporta_desaparicion", "entidad_banci", "entidad"]

# Llaves de contenido que se prueban, EN ESTE ORDEN, para volver a ligar una fila de
# revisión con su registro de BANCI. Se acepta una llave sólo si identifica a UN
# ÚNICO registro de BANCI: en una carpeta colectiva la carpeta sola no distingue
# entre víctimas, y pegar el match a la equivocada es peor que no pegarlo.
_LLAVES_RESOLUCION = [
    ("k_ent", "k_carp", "k_curp"),
    ("k_ent", "k_carp", "k_nom"),
    ("k_ent", "k_carp", "k_fnac"),
    ("k_ent", "k_carp"),
    ("k_ent", "k_curp"),
    ("k_ent", "k_nom", "k_fnac"),
]


def _k_col(x) -> str:
    """Normaliza un nombre de columna: ignora espacios, puntos, guiones y mayúsculas."""
    return re.sub(r"[\s._-]+", "", str(x)).upper()


def _buscar_col(df: pd.DataFrame, candidatas: List[str]) -> str:
    mapa = {_k_col(c): c for c in df.columns}
    return next((mapa[_k_col(c)] for c in candidatas if _k_col(c) in mapa), "")


def _norm_carpeta(s) -> str:
    """Carpeta reducida a alfanuméricos. Las dos bases escriben la misma carpeta con
    puntuación distinta ('C.I FG-AIFEPDNL/78/2025' vs 'C.IFG-AIFEPDNL/78/2025')."""
    return re.sub(r"[^A-Z0-9]", "", _quitar_acentos(str(s)).upper())


def _norm_nombre_llave(s) -> str:
    """Nombre a mayúsculas sin acentos, sin puntuación y con espacios colapsados."""
    return " ".join(re.sub(r"[^A-Z ]", " ", _quitar_acentos(str(s)).upper()).split())


def _norm_fecha_llave(s) -> str:
    """Fecha a 'YYYY-MM-DD' ('' si no es interpretable). Los archivos de revisión la
    traen a veces como '2008-05-01' y a veces como '2008-05-01 00:00:00'."""
    d = pd.to_datetime(str(s)[:10], errors="coerce", utc=True)
    return "" if pd.isna(d) else d.strftime("%Y-%m-%d")


def leer_revisiones_sesnsp(
    ruta_verif_fecha_hechos: Optional[Path] = None,
    ruta_revision_manual: Optional[Path] = None,
    hoja_verif: int = 0,
    hoja_revision: int = 1,
    skiprows_verif: int = 0,
    skiprows_revision: int = 0,
    col_mapping_verif: Optional[Dict[str, list]] = None,
    col_mapping_revision: Optional[Dict[str, list]] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Lee los dos archivos de revisión del SESNSP y los devuelve en un solo DataFrame
    normalizado, una fila por par revisado, con las columnas:

        fuente       'verif' | 'revision'
        veredicto    'SI' | 'NO' | ''   (vacío = no lo revisaron)
        quitar       True si ESE veredicto cierra el caso en ESE archivo
        bloquear     True si ESE veredicto sólo descarta el par, no a la persona
        id_registro  identificador del SESNSP (puede no cruzar con nuestro BANCI)
        fub          fub del RNPDNO emparejado
        k_ent/k_carp/k_curp/k_nom/k_fnac
                     llaves de contenido del lado BANCI, para volver a ligar la fila
                     con nuestro registro cuando `id_registro` no cruza

    La asimetría de `quitar` es la de normalizar_folios_v6.py:
      - matches_verif_fecha_hechos: las filas YA ERAN matches definitivos y sólo se
        preguntó si la diferencia de fechas los invalidaba. SI y NO cierran el caso.
      - revision_manual_score: las filas eran CANDIDATOS. El SI cierra el caso; el NO
        descarta ESE PAR, no a la persona, que sigue disponible para otro match.

    Lanza FileNotFoundError si una ruta no-None apunta a un archivo inexistente y
    ValueError si falta una columna requerida (revisa col_mapping_* y skiprows_* en
    config.py).
    """
    _REVISIONES = [
        dict(nombre="verif", ruta=ruta_verif_fecha_hechos, hoja=hoja_verif,
             skiprows=skiprows_verif,
             col_mapping=col_mapping_verif or _DEFAULT_VERIF_CM,
             quitar={"SI", "NO"}, bloquear={}),
        dict(nombre="revision", ruta=ruta_revision_manual, hoja=hoja_revision,
             skiprows=skiprows_revision,
             col_mapping=col_mapping_revision or _DEFAULT_REVISION_CM,
             quitar={"SI"}, bloquear={"NO"}),
    ]

    _COLS = ["fuente", "veredicto", "quitar", "bloquear", "id_registro", "fub",
             "k_ent", "k_carp", "k_curp", "k_nom", "k_fnac"]
    partes: List[pd.DataFrame] = []

    for cfg in _REVISIONES:
        ruta = cfg["ruta"]
        if ruta is None:
            continue
        if not Path(ruta).exists():
            raise FileNotFoundError(
                f"[Refinado] Archivo de revisión no encontrado: {ruta}\n"
                f"Verifica la ruta en config.REFINADO_RUTA_* "
                f"o asigna None si no se va a usar."
            )
        try:
            df = pd.read_excel(ruta, sheet_name=cfg["hoja"],
                               skiprows=cfg["skiprows"], dtype=str).fillna("")
        except Exception as e:
            raise RuntimeError(f"[Refinado] No se pudo leer {Path(ruta).name}: {e}") from e

        cm = cfg["col_mapping"]
        cv = _buscar_col(df, cm["col_valido"])
        cb = _buscar_col(df, cm["col_reg_banci"])
        cf = _buscar_col(df, cm["col_fub_rnpdno"])
        if not (cv and cf):
            faltantes = [k for k, v in [("col_valido", cv), ("col_fub_rnpdno", cf)] if not v]
            raise ValueError(
                f"[Refinado] {Path(ruta).name}: columnas no encontradas: {faltantes}.\n"
                f"Columnas disponibles (primeras 20): {list(df.columns)[:20]}\n"
                f"Candidatos configurados: {cm}\n"
                f"Verifica que skiprows sea correcto (actual: {cfg['skiprows']}) y ajusta "
                f"config.REFINADO_VERIF_COLUMN_MAPPING / config.REFINADO_REVISION_COLUMN_MAPPING."
            )

        c_carp = _buscar_col(df, _C_REV_CARPETA)
        c_curp = _buscar_col(df, _C_REV_CURP)
        c_nom  = _buscar_col(df, _C_REV_NOMBRES)
        c_ap1  = _buscar_col(df, _C_REV_APE1)
        c_ap2  = _buscar_col(df, _C_REV_APE2)
        c_ncmp = _buscar_col(df, _C_REV_NOMCOMP)
        c_fnac = _buscar_col(df, _C_REV_FNAC)
        c_ent  = _buscar_col(df, _C_REV_ENTIDAD)

        vacio = pd.Series("", index=df.index)
        if c_nom or c_ap1 or c_ap2:
            nombre = (df[c_nom] if c_nom else vacio) + " " + \
                     (df[c_ap1] if c_ap1 else vacio) + " " + \
                     (df[c_ap2] if c_ap2 else vacio)
        else:
            nombre = df[c_ncmp] if c_ncmp else vacio

        v = df[cv].map(lambda x: str(x).strip().upper())
        parte = pd.DataFrame({
            "fuente":      cfg["nombre"],
            "veredicto":   v,
            "quitar":      v.isin(cfg["quitar"]),
            "bloquear":    v.isin(cfg["bloquear"]),
            "id_registro": df[cb].map(_hash_norm) if cb else vacio,
            "fub":         df[cf].map(_hash_norm),
            "k_ent":       (df[c_ent] if c_ent else vacio).map(normalizar_entidad),
            "k_carp":      (df[c_carp] if c_carp else vacio).map(_norm_carpeta),
            "k_curp":      (df[c_curp] if c_curp else vacio).map(
                               lambda x: str(x).strip().upper()),
            "k_nom":       nombre.map(_norm_nombre_llave),
            "k_fnac":      (df[c_fnac] if c_fnac else vacio).map(_norm_fecha_llave),
        })[_COLS]
        partes.append(parte)

        if verbose:
            n_si = int((v == "SI").sum())
            n_no = int((v == "NO").sum())
            n_na = len(df) - n_si - n_no
            print(f"   [Refinado] {Path(ruta).name}: {len(df):,} filas — "
                  f"SI:{n_si:,}  NO:{n_no:,}  NA:{n_na:,}")

    if not partes:
        return pd.DataFrame(columns=_COLS)
    return pd.concat(partes, ignore_index=True)


def resolver_revisiones_a_banci(
    df_banci: pd.DataFrame, rev: pd.DataFrame, verbose: bool = True
) -> pd.Series:
    """
    Devuelve, para cada fila de `rev`, la etiqueta de índice de `df_banci` a la que
    corresponde (o NA si no se pudo resolver).

    Por qué no basta `id_registro`: en v6 el descuento se cruzaba por esa columna,
    pero es un sha1 que construye el SESNSP y que nuestro ETL no puede reproducir —
    no aparece en ninguna columna del BANCI de origen ni coincide con el de las bases
    puente. Cruzar por ahí devolvía CERO y el descuento quedaba silenciosamente
    inerte: los 517 FUB ya confirmados a mano nunca se aplicaban.

    Se resuelve entonces por CONTENIDO, probando `_LLAVES_RESOLUCION` en orden y
    aceptando una llave sólo cuando identifica a un único registro de BANCI.
    """
    if rev.empty or df_banci.empty:
        return pd.Series(pd.NA, index=rev.index, dtype="object")

    ba = pd.DataFrame(index=df_banci.index)
    col = lambda cands: _detectar_col(df_banci, cands)  # noqa: E731
    c_ent, c_carp = col(_C_ENTIDAD_BANCI), col(_C_FOLIO_BANCI)
    c_curp, c_nom = col(_C_CURP_BANCI), col(_C_NOMBRE_BANCI)
    c_fnac = col(_C_FNAC_BANCI)

    vacio = pd.Series("", index=df_banci.index)
    ba["k_ent"]  = (df_banci[c_ent]  if c_ent  else vacio).map(normalizar_entidad)
    ba["k_carp"] = (df_banci[c_carp] if c_carp else vacio).map(_norm_carpeta)
    ba["k_curp"] = (df_banci[c_curp] if c_curp else vacio).map(
        lambda x: "" if pd.isna(x) else str(x).strip().upper())
    ba["k_nom"]  = (df_banci[c_nom]  if c_nom  else vacio).map(_norm_nombre_llave)
    ba["k_fnac"] = (df_banci[c_fnac] if c_fnac else vacio).map(_norm_fecha_llave)

    resuelto = pd.Series(pd.NA, index=rev.index, dtype="object")
    detalle: Dict[str, int] = {}

    for llave in _LLAVES_RESOLUCION:
        pendientes = resuelto.isna()
        if not pendientes.any():
            break
        cols = list(llave)
        # Sólo sirven las filas donde TODAS las partes de la llave tienen valor.
        ba_ok = ba[(ba[cols] != "").all(axis=1)]
        if ba_ok.empty:
            continue
        # Una llave que apunta a más de un registro de BANCI no distingue víctima:
        # se descarta en vez de arriesgar pegar el match a la persona equivocada.
        grupos = ba_ok.groupby(cols, sort=False).size()
        unicos = grupos[grupos == 1]
        if unicos.empty:
            continue
        idx_por_llave = ba_ok.set_index(cols).index
        mapa = pd.Series(ba_ok.index, index=idx_por_llave)
        mapa = mapa[mapa.index.isin(unicos.index)]
        mapa = mapa[~mapa.index.duplicated()]

        rev_ok = pendientes & (rev[cols] != "").all(axis=1)
        if not rev_ok.any():
            continue
        buscado = pd.MultiIndex.from_frame(rev.loc[rev_ok, cols]) if len(cols) > 1 \
            else pd.Index(rev.loc[rev_ok, cols[0]])
        encontrado = pd.Series(mapa.reindex(buscado).to_numpy(), index=rev.index[rev_ok])
        nuevos = encontrado.notna()
        if nuevos.any():
            resuelto.loc[encontrado.index[nuevos]] = encontrado[nuevos]
            detalle["+".join(cols)] = int(nuevos.sum())

    if verbose:
        n = int(resuelto.notna().sum())
        print(f"   [Refinado] Revisiones ligadas a BANCI: {n:,} / {len(rev):,}")
        for llave, cuantos in detalle.items():
            print(f"      por {llave}: {cuantos:,}")
    return resuelto


def descuentos_sesnsp(
    df_banci: pd.DataFrame, rev: pd.DataFrame, verbose: bool = True
) -> Tuple[Set[Any], Set[str], Set[Tuple[Any, str]], Dict[Any, str]]:
    """
    Traduce las revisiones del SESNSP a las cuatro estructuras que consumen los
    motores, todas indexadas por la ETIQUETA DE ÍNDICE de `df_banci`:

        fuera_universo   : registros de BANCI cuyo caso ya está cerrado (salen del
                           universo del refinado; si no, se volverían a proponer y
                           saldrían doble en el conteo final).
        conf_fub         : fub del RNPDNO ya emparejados (mismo motivo).
        pares_rechazados : {(índice_banci, fub)} revisados y DESCARTADOS. Sólo se
                           bloquea EL PAR: la persona sigue disponible para otro match.
        confirmados      : {índice_banci: [fub, ...]} con veredicto SI, es decir los
                           matches que una persona ya validó. Es una LISTA porque la
                           relación es de muchos a muchos: una carpeta de BANCI puede
                           corresponder a varios registros del RNPDNO. Es lo que el
                           motor manual aplica.
    """
    if rev.empty:
        return set(), set(), set(), {}

    idx = resolver_revisiones_a_banci(df_banci, rev, verbose=verbose)
    rev = rev.assign(idx_banci=idx)

    conf_fub = set(rev.loc[rev["quitar"], "fub"]) - {""}
    con_idx = rev[rev["idx_banci"].notna()]

    fuera_universo = set(con_idx.loc[con_idx["quitar"], "idx_banci"])
    pares_rechazados = {
        (i, f) for i, f in zip(con_idx.loc[con_idx["bloquear"], "idx_banci"],
                               con_idx.loc[con_idx["bloquear"], "fub"]) if f
    }
    si = con_idx[(con_idx["veredicto"] == "SI") & (con_idx["fub"] != "")]
    # Un registro puede tener VARIOS FUB confirmados y todos son válidos: la relación
    # entre BANCI y RNPDNO es de muchos a muchos —una carpeta ampara a varias víctimas
    # y una persona puede estar registrada más de una vez en el RNPDNO—, así que un
    # revisor que marca tres pares como buenos está diciendo que los tres lo son.
    # Se conservan todos, ordenados por fuente: primero los de verif, cuyas filas YA
    # eran matches definitivos y sólo se preguntó por la fecha de hechos, y después los
    # de revision_manual_score, que eran candidatos. El primero de la lista es el que
    # la fila de BANCI lleva como `id_match_manual`; los demás se reclaman igual del
    # lado del RNPDNO, que es donde cada FUB cuenta como persona localizada en BANCI.
    orden = si.assign(_pri=(si["fuente"] != "verif").astype(int))
    orden = orden.sort_values("_pri", kind="stable")
    confirmados: Dict[Any, List[str]] = {}
    for i, f in zip(orden["idx_banci"], orden["fub"]):
        lista = confirmados.setdefault(i, [])
        if f not in lista:
            lista.append(f)

    if verbose:
        n_multi = sum(1 for v in confirmados.values() if len(v) > 1)
        n_pares = sum(len(v) for v in confirmados.values())
        print(f"   [Refinado] Descuento SESNSP → BANCI fuera del universo: "
              f"{len(fuera_universo):,}  |  FUB emparejados: {len(conf_fub):,}  |  "
              f"pares rechazados: {len(pares_rechazados):,}  |  "
              f"registros confirmados: {len(confirmados):,} ({n_pares:,} pares, "
              f"{n_multi:,} con más de un FUB)")
        n_sin_ligar = int(
            ((rev["veredicto"] == "SI") & (rev["fub"] != "") & rev["idx_banci"].isna()).sum()
        )
        if n_sin_ligar:
            print(f"      no aplicados: {n_sin_ligar:,} filas SI sin registro de BANCI "
                  f"identificable")
    return fuera_universo, conf_fub, pares_rechazados, confirmados


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE LÓGICA DE MATCHING (idénticas a normalizar_folios_v6.py)
# ══════════════════════════════════════════════════════════════════════════════

def _consecutivo_banci(folio: str, id_ci, tokens_ignorar: FrozenSet[str]) -> Tuple:
    """
    Consecutivo limpio de BANCI con la regla id_ci:
    si el consecutivo de la carpeta tiene <= 2 dígitos, se usa id_ci.
    Devuelve (cons, alt, anio, claves, fuente).
    """
    na = normalizar_folio(folio, tokens_ignorar=tokens_ignorar)
    cons, alt, anio = na["consecutivo"], na["consecutivo_alt"], na["anio"]
    claves = set(str(na["claves_detectadas"]).split("|")) - {""}
    fuente = "carpeta"
    if (len(cons) <= 2
            and id_ci is not None
            and str(id_ci).strip() not in ("", "nan", "None")):
        ni = normalizar_folio(id_ci)
        if len(ni["consecutivo"]) >= 3:
            cons, fuente = ni["consecutivo"], "id_ci"
            if not anio:
                anio = ni["anio"]
    return cons, alt, anio, claves, fuente


def _folio_limpio_status(
    cons_a, anio_a, claves_a,
    cons_b, alt_b, anio_b, claves_b,
) -> Tuple[str, str]:
    """
    Compara dos folios ya normalizados.
    Devuelve ('igual'|'parcial'|'anio_distinto'|'no', motivo).
    """
    if not cons_a or not (cons_b or alt_b):
        return "no", "sin consecutivo comparable"
    casa = cons_a == cons_b or (alt_b and cons_a == alt_b)
    if not casa:
        return "no", "consecutivo distinto"
    if anio_a and anio_b and anio_a != anio_b:
        return "anio_distinto", f"anio {anio_a} vs {anio_b} (otra carpeta)"
    if claves_a and claves_b:
        jac = len(claves_a & claves_b) / len(claves_a | claves_b)
        if jac < 1:
            return "parcial", "claves de oficina distintas (algun caracter distinto)"
    return "igual", "folio limpio identico (formato/ceros ignorados)"


def _fhechos_dias(a: dict, b: dict) -> Optional[int]:
    """Diferencia en días entre fechas de hechos. None si falta o es inválida."""
    da = pd.to_datetime(str(a.get("fhec", ""))[:10], errors="coerce", utc=True)
    db = pd.to_datetime(str(b.get("fhec", ""))[:10], errors="coerce", utc=True)
    if pd.isna(da) or pd.isna(db):
        return None
    return abs((da - db).days)


def _muni_igual(a: dict, b: dict) -> bool:
    """Municipio igual con fuzzy match (la notación difiere entre bases)."""
    ma, mb = a.get("muni", ""), b.get("muni", "")
    if not ma or not mb:
        return False
    return ma == mb or similitud_nombres(ma, mb) >= UMBRAL_MUNICIPIO


def _guarda_fnac(a: dict, b: dict, sim: float, colectiva: bool) -> Tuple[bool, str]:
    """
    Guardián anti-homónimo para definitivos. Exige fecha de nacimiento (o CURP-10)
    cuando el nombre no es idéntico O la fecha de hechos difiere > 360 días.
    Excepción: carpetas colectivas (fecha genérica, no confiable).
    """
    if colectiva:
        return True, ""
    motivos = []
    if sim < UMBRAL_NOMBRE_EXACTO:
        motivos.append("nombre no identico")
    dias = _fhechos_dias(a, b)
    if dias is not None and dias > DIAS_FHECHOS_EXIGE_FNAC:
        motivos.append(f"fecha de hechos difiere {dias} dias")
    if not motivos:
        return True, ""
    fnac_ig   = bool(a.get("fnac")) and a["fnac"] == b.get("fnac")
    curp10_ig = (len(a.get("curp", "")) >= 10 and len(b.get("curp", "")) >= 10
                 and a["curp"][:10] == b["curp"][:10])
    if fnac_ig or curp10_ig:
        return True, " + fecha nac" if fnac_ig else " + curp10"
    return False, "; ".join(motivos)


def _nombre_total_identico(a: dict, b: dict, sim: float) -> bool:
    """
    Nombre COMPLETO idéntico: exige que ambos lados tengan el mismo número de tokens
    (>= 3: nombre + 2 apellidos) y que la similitud sea prácticamente 1.0.
    """
    ta = [t for t in _quitar_acentos(str(a.get("nombre", ""))).upper().split() if len(t) >= 2]
    tb = [t for t in _quitar_acentos(str(b.get("nombre", ""))).upper().split() if len(t) >= 2]
    return (sim >= UMBRAL_NOMBRE_EXACTO and len(ta) == len(tb) and len(ta) >= 3)


def _guarda_otra_carpeta(
    a: dict, b: dict, sim: float, n_toks: int,
) -> Tuple[bool, str]:
    """
    Guardián para afirmar 'misma persona en otra carpeta' sin CURP-18 ni FUB.
    Exige una ancla de identidad fuerte (fecha de nacimiento o nombre completo + apoyo).
    """
    fnac_a, fnac_b = str(a.get("fnac", "")).strip(), str(b.get("fnac", "")).strip()
    fnac_ig   = bool(fnac_a) and fnac_a == fnac_b
    curp10_ig = (len(a.get("curp", "")) >= 10 and len(b.get("curp", "")) >= 10
                 and a["curp"][:10] == b["curp"][:10])
    contradice = bool(a.get("ent")) and bool(b.get("ent")) and a["ent"] != b["ent"]

    if contradice:
        if not (fnac_ig or curp10_ig):
            return False, "entidades distintas sin fecha nac que lo confirme"
        if not _nombre_total_identico(a, b, sim):
            return False, "entidades distintas y nombre no completo/identico"
        nota = (" + fecha nac igual" if fnac_ig else " + curp10 igual")
        return True, nota + " + nombre completo identico (entidades distintas)"

    if curp10_ig:
        return True, " + curp10 igual"
    if fnac_a and fnac_b:
        return (True, " + fecha nac igual") if fnac_ig else (False, "fecha nac distinta")

    if not (sim >= UMBRAL_NOMBRE_EXACTO and n_toks >= 3):
        return False, "sin fecha nac y nombre no completo"

    apoyos = []
    if _muni_igual(a, b):
        apoyos.append("municipio")
    if a.get("ent") and a["ent"] == b.get("ent"):
        apoyos.append("entidad")
    d = _fhechos_dias(a, b)
    if d is not None and d <= VENTANA_FECHA_HECHOS_DIAS:
        apoyos.append("fecha de hechos")
    if not apoyos:
        return False, "sin fecha nac y sin otra variable de apoyo"
    return True, " + " + " + ".join(apoyos) + " (sin fecha nac comparable)"


def _corroboradores(a: dict, b: dict) -> List[str]:
    """
    Variables (además del folio) en que coinciden dos registros.
    Se usan para respaldar una carpeta idéntica cuando el nombre NO coincide.
    """
    c = []
    if a["fnac"] and a["fnac"] == b["fnac"]:
        c.append("fecha nac")
    if len(a["curp"]) >= 10 and len(b["curp"]) >= 10 and a["curp"][:10] == b["curp"][:10]:
        c.append("curp10")
    if _muni_igual(a, b):
        c.append("municipio")
    if a["ent"] and a["ent"] == b["ent"]:
        c.append("entidad")
    if a["sexo"] and a["sexo"] == b["sexo"]:
        c.append("sexo")
    return c


def _tokens_nombre_coincidentes(a: dict, b: dict) -> int:
    """
    Cuántos tokens del nombre casan realmente (identicos o variante ortográfica >= 0.85).
    Distingue 'coincide solo en un apellido' (1 token) de coincidencia real (>= 2).
    """
    def _toks(x: str) -> List[str]:
        x = re.sub(r"[^A-Z\s]", " ", _quitar_acentos(str(x)).upper())
        return [w for w in x.split() if len(w) >= 2 and w not in _PARTICULAS_NOMBRE]

    ta, tb = _toks(a.get("nombre", "")), _toks(b.get("nombre", ""))
    if not ta or not tb:
        return 0
    restantes, n = list(tb), 0
    for w in ta:
        mejor_i, mejor_r = -1, 0.0
        for i, x in enumerate(restantes):
            r = 1.0 if w == x else SequenceMatcher(None, w, x).ratio()
            if r > mejor_r:
                mejor_r, mejor_i = r, i
        if mejor_r >= 0.85:
            n += 1
            restantes.pop(mejor_i)
    return n


@lru_cache(maxsize=300_000)
def _n_tokens_nombre(x: str) -> int:
    """Tokens de >=2 caracteres de un nombre. OJO: no es la tokenización de
    `_toks_nombre` (aquí no se expanden abreviaturas ni se quitan partículas);
    se memoiza aparte para no alterar el conteo."""
    return len([t for t in _quitar_acentos(str(x)).upper().split() if len(t) >= 2])


def _sim_nombre(a: dict, b: dict) -> Tuple[float, int]:
    """Devuelve (similitud, n_tokens_del_nombre_más_corto)."""
    sim = similitud_nombres(a["nombre"], b["nombre"])
    n_toks = min(_n_tokens_nombre(a["nombre"]), _n_tokens_nombre(b["nombre"]))
    return sim, n_toks


def _verificaciones_descriptivas(ia: int, ib: int, A: dict, B: dict) -> dict:
    """Verificaciones descriptivas por variable para el par (ia, ib)."""
    a, b = A.get(ia, {}), B.get(ib, {})

    def _cat(va, vb, igual: bool) -> str:
        ha, hb = bool(str(va).strip()), bool(str(vb).strip())
        if not ha and not hb: return "SIN DATO AMBOS"
        if not ha: return "SIN DATO BANCI"
        if not hb: return "SIN DATO RNPDNO"
        return "COINCIDE" if igual else "NO COINCIDE"

    v: dict = {}

    # Nombre
    na_, nb_ = str(a.get("nombre", "")).strip(), str(b.get("nombre", "")).strip()
    if not na_ and not nb_:
        v["verif_nombre"] = "SIN DATO AMBOS"
    elif not na_:
        v["verif_nombre"] = "SIN DATO BANCI"
    elif not nb_:
        v["verif_nombre"] = "SIN DATO RNPDNO"
    else:
        sim = similitud_nombres(na_, nb_)
        v["verif_nombre"] = ("COINCIDE" if sim >= UMBRAL_NOMBRE_100 else
                             f"PARCIAL (similitud {sim:.2f})" if sim >= 0.5 else
                             "NO COINCIDE")

    # CURP
    ca_, cb_ = a.get("curp", ""), b.get("curp", "")
    if len(ca_) < 10 and len(cb_) < 10:
        v["verif_curp"] = "SIN DATO AMBOS"
    elif len(ca_) < 10:
        v["verif_curp"] = "SIN DATO BANCI"
    elif len(cb_) < 10:
        v["verif_curp"] = "SIN DATO RNPDNO"
    elif ca_ == cb_ and len(ca_) == 18:
        v["verif_curp"] = "COINCIDE"
    elif ca_[:10] == cb_[:10]:
        v["verif_curp"] = "PARCIAL (CURP-10 igual)"
    else:
        v["verif_curp"] = "NO COINCIDE"

    # Carpeta
    st, mot = _folio_limpio_status(
        a.get("cons", ""), a.get("anio", ""), a.get("claves", set()),
        b.get("cons", ""), b.get("alt",  ""), b.get("anio", ""), b.get("claves", set()),
    )
    v["verif_carpeta"] = ("IDENTICA (limpia)"     if st == "igual" else
                          f"PARCIAL ({mot})"       if st == "parcial" else
                          "PARCIAL (anio distinto)" if st == "anio_distinto" else
                          ("SIN DATO" if "sin consecutivo" in mot else "NO COINCIDE"))

    v["verif_entidad"]   = _cat(a.get("ent",  ""), b.get("ent",  ""), a.get("ent")  == b.get("ent"))
    v["verif_sexo"]      = _cat(a.get("sexo", ""), b.get("sexo", ""), a.get("sexo") == b.get("sexo"))
    v["verif_fecha_nac"] = _cat(a.get("fnac", ""), b.get("fnac", ""), a.get("fnac") == b.get("fnac"))

    return v


# ══════════════════════════════════════════════════════════════════════════════
# MOTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

_PRIORIDAD_EVAL = {
    "definitivo":                    3,
    "parcial (algun caracter distinto)": 2,
    "revision manual":               1,
    "sin_match":                     0,
}
_COLS_SALIDA = [
    "id_match_refinado", "tipo_match_refinado", "score_refinado",
    "variables_match_refinado", "evaluacion_match_refinado",
    "fecha_hechos_status_refinado",
    "verif_nombre_refinado", "verif_curp_refinado", "verif_carpeta_refinado",
    "verif_entidad_refinado", "verif_sexo_refinado", "verif_fecha_nac_refinado",
]


def motor_match_refinado(
    df_banci:  pd.DataFrame,
    df_rnpdno: pd.DataFrame,
    conf_banci:        Optional[Set[str]]             = None,
    conf_fub:          Optional[Set[str]]             = None,
    pares_rechazados:  Optional[Set[Tuple[str, str]]] = None,
    ruta_verif_fecha_hechos: Optional[Path]           = None,
    ruta_revision_manual:    Optional[Path]           = None,
    hoja_verif:    int = 0,
    hoja_revision: int = 1,
    skiprows_verif:    int = 0,
    skiprows_revision: int = 0,
    col_mapping_verif:    Optional[Dict[str, list]] = None,
    col_mapping_revision: Optional[Dict[str, list]] = None,
    mostrar_progreso: bool = False,
    **kwargs,
) -> pd.DataFrame:
    """
    Motor de matching refinado. Implementa la lógica de normalizar_folios_v6.py
    como función pura sin estado (stateless), compatible con MultiMatchOrchestrator.

    Ver docstring del módulo para detalles de parámetros y prerrequisitos.
    """
    print("  🔸 [Motor Refinado] Ejecutando cruce por folios + nombre + CURP + FUB...")

    # ── 1. Cargar revisiones SESNSP si se proporcionaron rutas ────────────────
    # `conf_banci` y `pares_rechazados` se manejan por ETIQUETA DE ÍNDICE de
    # df_banci, no por el `id_registro` del SESNSP: ese identificador es un sha1 que
    # construye el Secretariado y que nuestro ETL no reproduce, así que cruzar por él
    # devolvía cero y el descuento quedaba inerte. `descuentos_sesnsp` vuelve a ligar
    # cada revisión con su registro por contenido (entidad + carpeta + curp/nombre/
    # fecha de nacimiento).
    if ruta_verif_fecha_hechos or ruta_revision_manual:
        _rev = leer_revisiones_sesnsp(
            ruta_verif_fecha_hechos, ruta_revision_manual,
            hoja_verif, hoja_revision,
            skiprows_verif, skiprows_revision,
            col_mapping_verif, col_mapping_revision,
        )
        _c_b, _c_f, _rechaz, _ = descuentos_sesnsp(df_banci, _rev)
        conf_banci       = (conf_banci       or set()) | _c_b
        conf_fub         = (conf_fub         or set()) | _c_f
        pares_rechazados = (pares_rechazados or set()) | _rechaz

    conf_banci       = conf_banci       or set()
    conf_fub         = conf_fub         or set()
    pares_rechazados = pares_rechazados or set()

    # ── 2. Copias locales con índice 0-based (no modificamos los originales) ──
    banci = df_banci.reset_index(drop=True).copy()
    comp  = df_rnpdno.reset_index(drop=True).copy()
    banci = banci.loc[:, ~banci.columns.duplicated()].copy()
    comp  = comp.loc[:, ~comp.columns.duplicated()].copy()

    # ── 3. Detectar columnas ──────────────────────────────────────────────────
    fol_a   = _detectar_col(banci, _C_FOLIO_BANCI)
    idci_a  = _detectar_col(banci, _C_ID_CI)
    fub_a   = _detectar_col(banci, _C_FUB_BANCI)
    nom_a   = _detectar_col(banci, _C_NOMBRE_BANCI)
    ape_a   = _detectar_col(banci, _C_APEPAT_BANCI)
    curp_a  = _detectar_col(banci, _C_CURP_BANCI)
    fnac_a  = _detectar_col(banci, _C_FNAC_BANCI)
    fhec_a  = _detectar_col(banci, _C_FHEC_BANCI)
    ent_a   = _detectar_col(banci, _C_ENTIDAD_BANCI)
    muni_a  = _detectar_col(banci, _C_MUNICIPIO_BANCI)
    sex_a   = _detectar_col(banci, _C_SEXO_BANCI)
    idreg_a = _detectar_col(banci, _C_IDREG_BANCI)

    # Identificadores de persona y carpeta para cálculo exacto de multiplicidad (como v6)
    idpers_sha_a = _detectar_col(banci, ["id_persona_banci", "id_persona_sha1_banci",
                                         "id_persona_sha1", "id_persona", "id_registro_banci",
                                         "id_registro"])
    idcarp_sha_a = _detectar_col(banci, ["id_carpeta_derivada_banci", "id_carpeta_sha1_banci",
                                         "id_carpeta_sha1", "id_carpeta_investigacion_banci",
                                         "id_carpeta"])

    if idci_a and ("sha" in idci_a.lower() or "hash" in idci_a.lower()):
        idci_a = ""   # Un hash no es un consecutivo: ignorar la regla id_ci

    fol_b   = _detectar_col(comp, _C_FOLIO_RNPDNO)
    fub_b   = _detectar_col(comp, _C_FUB_RNPDNO)
    nom_b   = _detectar_col(comp, _C_NOMBRE_RNPDNO)
    ape_b   = _detectar_col(comp, _C_APEPAT_RNPDNO)
    curp_b  = _detectar_col(comp, _C_CURP_RNPDNO)
    fnac_b  = _detectar_col(comp, _C_FNAC_RNPDNO)
    fhec_b  = _detectar_col(comp, _C_FHEC_RNPDNO)
    ent_b   = _detectar_col(comp, _C_ENTIDAD_RNPDNO)
    muni_b  = _detectar_col(comp, _C_MUNICIPIO_RNPDNO)
    sex_b   = _detectar_col(comp, _C_SEXO_RNPDNO)

    idpers_b = _detectar_col(comp, ["id_persona_rnpdno", "id_persona", "fub_rnpdno", "id_registro_rnpdno"])
    idcarp_b = _detectar_col(comp, ["id_carpeta", "id_carpeta_rnpdno"])

    if not fol_a:
        print("  ⚠️ [Refinado] No se detectó columna de folio en BANCI. "
              "El cruce por carpeta se omitirá. Agregar nombre a _C_FOLIO_BANCI.")
    if not fol_b:
        print("  ⚠️ [Refinado] No se detectó columna de folio en RNPDNO. "
              "El cruce por carpeta se omitirá. Agregar nombre a _C_FOLIO_RNPDNO.")
    if not fub_b:
        print("  ⚠️ [Refinado] No se detectó columna FUB en RNPDNO. "
              "id_match_refinado quedará vacío. Agregar nombre a _C_FUB_RNPDNO.")

    print(f"  BANCI: folio='{fol_a}' fub='{fub_a}' nombre='{nom_a}' "
          f"curp='{curp_a}' id_reg='{idreg_a}'")
    print(f"  RNPDNO: folio='{fol_b}' fub='{fub_b}' nombre='{nom_b}' "
          f"curp='{curp_b}'")

    # ── 4. Determinar qué filas saltan por descuento ───────────────────────────
    # Se trabaja sobre el conjunto COMPLETO (no se filtra en lugar) para
    # preservar el mapeo de índices al DataFrame original de df_banci.
    # `conf_banci` y `pares_rechazados` vienen indexados por la etiqueta de índice de
    # df_banci; aquí se traducen a la posición 0-based con la que trabaja el motor.
    # Se acepta además el `id_registro` del SESNSP por si el BANCI llegara a traerlo.
    REG_BANCI: Dict[int, str] = {}
    if idreg_a:
        REG_BANCI = {i: _hash_norm(banci.at[i, idreg_a]) for i in range(len(banci))}

    skip_banci: Set[int] = set()
    if conf_banci:
        for i in range(len(banci)):
            if df_banci.index[i] in conf_banci or REG_BANCI.get(i, "") in conf_banci:
                skip_banci.add(i)
        print(f"  Descuento BANCI: {len(skip_banci):,} registros ya confirmados se omiten")

    skip_rnpdno: Set[int] = set()
    if fub_b and conf_fub:
        for i in range(len(comp)):
            v = _hash_norm(comp.at[i, fub_b])
            if v in conf_fub:
                skip_rnpdno.add(i)
        print(f"  Descuento RNPDNO: {len(skip_rnpdno):,} fub ya emparejados se omiten")

    # Llaves con las que se bloquean los pares ya rechazados a mano.
    LLAVE_BANCI = {i: df_banci.index[i] for i in range(len(banci))}
    FUB_RNPDNO = ({i: _hash_norm(v) for i, v in enumerate(comp[fub_b].tolist())}
                  if fub_b else {})

    # ── 5. Tokens ignorar (códigos de oficina frecuentes) ─────────────────────
    tig_a = _tokens_ignorar_de_serie(banci[fol_a]) if fol_a else frozenset()
    tig_b = _tokens_ignorar_de_serie(comp[fol_b])  if fol_b else frozenset()

    # ── 6. Auxiliar para leer un campo ────────────────────────────────────────
    # Las columnas se materializan a lista UNA vez y después se indexan por
    # posición. Antes se leía celda por celda con `df.at[i, col]`, y como las
    # columnas del RNPDNO vienen respaldadas por Arrow, cada acceso escalar
    # cuesta ~40 µs en vez de ~50 ns: con 408 mil registros por ~10 columnas eran
    # millones de accesos y el 60% del tiempo del motor. El valor leído es el
    # mismo; sólo cambia cuántas veces se paga el viaje a pandas.
    _cols_mem: Dict[Tuple[int, str], list] = {}

    def _columna(df: pd.DataFrame, col: str) -> list:
        k = (id(df), col)
        c = _cols_mem.get(k)
        if c is None:
            c = df[col].tolist()
            _cols_mem[k] = c
        return c

    def _g(df: pd.DataFrame, col: str, i: int, n: int = 10) -> str:
        if not col:
            return ""
        v = _columna(df, col)[i]
        if v is None or v is pd.NaT:
            return ""
        if not isinstance(v, str) and pd.isna(v):
            return ""
        return str(v)[:n] if n else str(v)

    def _g_full(df: pd.DataFrame, col: str, i: int) -> str:
        return _g(df, col, i, n=0)

    # ── 7. Construir diccionarios de llaves limpias ───────────────────────────
    A: Dict[int, dict] = {}
    for i in range(len(banci)):
        if i in skip_banci:
            continue
        cons, alt, anio, claves, fuente = _consecutivo_banci(
            _g_full(banci, fol_a, i),
            _g_full(banci, idci_a, i) if idci_a else None,
            tig_a,
        )
        A[i] = dict(
            cons=cons, alt=alt, anio=anio, claves=claves, fuente=fuente,
            ent=normalizar_entidad(_g_full(banci, ent_a, i)),
            sexo=normalizar_sexo(_g_full(banci, sex_a, i)),
            curp=_limpia_curp(_g_full(banci, curp_a, i)),
            nombre=_g_full(banci, nom_a, i),
            fnac=_g(banci, fnac_a, i),
            fhec=_g(banci, fhec_a, i),
            muni=_quitar_acentos(_g_full(banci, muni_a, i)).upper().strip(),
            fub=_g_full(banci, fub_a, i).strip().upper(),
        )

    B: Dict[int, dict] = {}
    idx_cons_b:   Dict[str, List[int]] = defaultdict(list)
    idx_curp_b:   Dict[str, List[int]] = defaultdict(list)
    idx_curp10_b: Dict[str, List[int]] = defaultdict(list)
    idx_fub_b:    Dict[str, List[int]] = defaultdict(list)
    idx_ape_b:    Dict[str, List[int]] = defaultdict(list)
    idx_fnac_b:   Dict[str, List[int]] = defaultdict(list)

    for i in range(len(comp)):
        if i in skip_rnpdno:
            continue
        nb   = normalizar_folio(_g_full(comp, fol_b, i), tokens_ignorar=tig_b)
        curp = _limpia_curp(_g_full(comp, curp_b, i))
        fub_val = _g_full(comp, fub_b, i).strip().upper()
        B[i] = dict(
            cons=nb["consecutivo"], alt=nb["consecutivo_alt"],
            anio=nb["anio"],
            claves=set(str(nb["claves_detectadas"]).split("|")) - {""},
            ent=normalizar_entidad(_g_full(comp, ent_b, i)),
            sexo=normalizar_sexo(_g_full(comp, sex_b, i)),
            curp=curp,
            nombre=_g_full(comp, nom_b, i),
            fnac=_g(comp, fnac_b, i),
            fhec=_g(comp, fhec_b, i),
            muni=_quitar_acentos(_g_full(comp, muni_b, i)).upper().strip(),
            fub=fub_val,
        )
        if B[i]["cons"]:   idx_cons_b[B[i]["cons"]].append(i)
        if B[i]["alt"]:    idx_cons_b[B[i]["alt"]].append(i)
        if len(curp) == 18: idx_curp_b[curp].append(i)
        if len(curp) >= 10: idx_curp10_b[curp[:10]].append(i)
        if fub_val:         idx_fub_b[fub_val].append(i)
        ape = _quitar_acentos(_g_full(comp, ape_b, i)).upper().strip() if ape_b else ""
        if ape:             idx_ape_b[ape].append(i)
        if B[i]["fnac"]:    idx_fnac_b[B[i]["fnac"]].append(i)

    print(f"  Índices B construidos: {len(B):,} registros RNPDNO")

    # ── 7b. Conteos de multiplicidad (con la lógica exacta de v6) ─────────────
    def _conteos(idx_dict, df, col_carpeta, col_pers_id=None, col_carp_id=None):
        # Mismo motivo que en `_g`: `df[col].iat[i]` dentro del bucle era el 39%
        # del tiempo total del motor. Aquí la columna se materializa una vez.
        _pers = _columna(df, col_pers_id) if (col_pers_id and col_pers_id in df.columns) else None
        _carpid = _columna(df, col_carp_id) if (col_carp_id and col_carp_id in df.columns) else None
        _carp = _columna(df, col_carpeta) if (col_carpeta and col_carpeta in df.columns) else None

        pers_key, carp_key = {}, {}
        for i, d in idx_dict.items():
            # llave de PERSONA: id sha1 si existe -> CURP -> nombre -> registro
            pid = str(_pers[i]).strip() if _pers is not None else ""
            if pid and pid.upper() not in ("NAN", "NONE"):
                pk = "PID:" + pid
            elif len(d["curp"]) == 18:
                pk = "CURP:" + d["curp"]
            else:
                nm = " ".join(_quitar_acentos(d["nombre"]).upper().split())
                pk = ("NOMBRE:" + nm) if nm else ("REG:" + str(i))
            # llave de CARPETA: id sha1 si existe -> folio crudo (o REG si no hay folio)
            cid = str(_carpid[i]).strip() if _carpid is not None else ""
            if cid and cid.upper() not in ("NAN", "NONE"):
                ck = "CID:" + cid
            elif _carp is not None:
                ck = str(_carp[i]).strip().upper()
            else:
                ck = ""   # sin folio: no se puede calcular colectiva
            pers_key[i], carp_key[i] = pk, ck
        por_pers = defaultdict(list); por_carp = defaultdict(list)
        for i in idx_dict:
            por_pers[pers_key[i]].append(i); por_carp[carp_key[i]].append(i)
        # Los dos conjuntos dependen sólo del GRUPO, no del registro: se calculan
        # una vez por llave. Y la resta se reduce a una prueba de pertenencia
        # (|S - {x}| = |S| - 1 si x está en S), que es O(1) en vez de O(|S|).
        #
        # Antes, ambas cosas se recalculaban por registro y el costo era la suma
        # de |grupo|². Con un grupo de 44,747 registros —todos los del RNPDNO sin
        # expediente, que caen juntos bajo la llave "NAN"— eran 2,000 millones de
        # operaciones sólo en esta fase, el 53% del motor. El resultado es
        # idéntico; lo que cambia es que ya no se repite el mismo cálculo.
        cache_pers: dict = {}
        cache_carp: dict = {}
        out = {}
        for i in idx_dict:
            pk, ck = pers_key[i], carp_key[i]
            carpetas_de_pers = cache_pers.get(pk)
            if carpetas_de_pers is None:
                carpetas_de_pers = cache_pers[pk] = {carp_key[j] for j in por_pers[pk]}
            if ck:
                personas_de_carp = cache_carp.get(ck)
                if personas_de_carp is None:
                    personas_de_carp = cache_carp[ck] = {pers_key[j] for j in por_carp[ck]}
            else:
                personas_de_carp = None
            out[i] = dict(
                count_persona=len(por_pers[pk]),
                count_persona_dist=len(carpetas_de_pers) - (1 if ck in carpetas_de_pers else 0),
                count_carpeta=(len(por_carp[ck]) if ck else 0),
                count_carpeta_dist=((len(personas_de_carp) - (1 if pk in personas_de_carp else 0))
                                    if ck else 0),
            )
        return out

    CNT_A = _conteos(A, banci, fol_a if fol_a else None, idpers_sha_a, idcarp_sha_a)
    # v6: _conteos(B, comp, fol_b, idpers_b or fub_b, idcarp_b)
    # Si no hay columna de id_persona en RNPDNO, usar fub_b (el FUB es id único de persona)
    CNT_B = _conteos(B, comp, fol_b if fol_b else None, idpers_b or fub_b, idcarp_b)

    # ── 8. Función de candidatos ──────────────────────────────────────────────
    def _candidatos_de(ia: int, a: dict) -> Set[int]:
        cands: Set[int] = set()
        if a["fub"] in idx_fub_b:
            cands |= set(idx_fub_b[a["fub"]])
        if len(a["curp"]) == 18:
            cands |= set(idx_curp_b.get(a["curp"], []))
        if len(a["curp"]) >= 10:
            cands |= set(idx_curp10_b.get(a["curp"][:10], []))
        for k in (a["cons"], a["alt"]):
            if k:
                cands |= set(idx_cons_b.get(k, []))
        if ape_a:
            ape = _quitar_acentos(_g_full(banci, ape_a, ia)).upper().strip()
            if ape and len(idx_ape_b.get(ape, [])) <= MAX_BLOQUE_NOMBRE:
                cands |= set(idx_ape_b.get(ape, []))
        if a["fnac"]:
            cands |= set(idx_fnac_b.get(a["fnac"], []))
        # Bloquear pares ya rechazados. Sólo se descarta EL PAR: el registro de BANCI
        # sigue disponible para matchear con otro del RNPDNO.
        if pares_rechazados:
            llaves = {LLAVE_BANCI[ia], REG_BANCI.get(ia, "")} - {""}
            cands = {ib for ib in cands
                     if not any((k, FUB_RNPDNO.get(ib, "")) in pares_rechazados
                                for k in llaves)}
        return cands

    # ── 9. Clasificación (definitivo / parcial / revision manual) ─────────────
    tiene_def:   Dict[int, List[Tuple]] = {}
    eval_por_rec: Dict[int, List[Tuple]] = {}

    _pb = _ProgressBar(len(A), desc="[Refinado] Clasificando") if mostrar_progreso else None

    for ia, a in A.items():
        lst:  List[Tuple] = []
        defs: List[Tuple] = []
        colectiva_a = CNT_A[ia]["count_carpeta_dist"] > 0

        for ib in _candidatos_de(ia, a):
            b = B[ib]
            st, mot = _folio_limpio_status(
                a["cons"], a["anio"], a["claves"],
                b["cons"], b["alt"],  b["anio"], b["claves"],
            )
            sim, n_toks = _sim_nombre(a, b)
            lst.append((ib, sim, st, mot))

            nombre_def = sim >= UMBRAL_NOMBRE_SOLO and n_toks >= 2
            curp18     = len(a["curp"]) == 18 and a["curp"] == b["curp"]
            fub_ig     = bool(a["fub"]) and a["fub"] == b["fub"]

            if st == "igual":
                colectiva = colectiva_a or CNT_B[ib]["count_carpeta_dist"] > 0
                if nombre_def:
                    _ok, _nota = _guarda_fnac(a, b, sim, colectiva)
                    if _ok:
                        det = (f"{'carpeta colectiva; ' if colectiva else ''}"
                               f"nombre {sim:.2f}{_nota} + folio limpio identico "
                               f"(formato/ceros ignorados); fuente: {a['fuente']}")
                        defs.append((ib, "definitivo", det))
                elif not colectiva:
                    corr    = _corroboradores(a, b)
                    fuertes = [x for x in corr if x in ("fecha nac", "curp10")]
                    if len(corr) >= CORROBORADORES_MIN_CARPETA and fuertes:
                        defs.append((ib, "definitivo",
                                     "folio limpio identico + "
                                     f"{' + '.join(corr)}; fuente: {a['fuente']}"))

            elif st in ("parcial", "anio_distinto") and nombre_def:
                # Chequear AMBOS lados (BANCI y RNPDNO) para decidir si omitir la guarda de fecha_nac (igual que v6)
                _colect_p = colectiva_a or CNT_B[ib]["count_carpeta_dist"] > 0
                _ok, _nota = _guarda_fnac(a, b, sim, _colect_p)
                if _ok:
                    defs.append((ib, "parcial (algun caracter distinto)",
                                 f"nombre {sim:.2f}{_nota} + carpeta parcial ({mot})"))

            else:  # carpeta distinta
                carp = ("mismo consecutivo, otro anio (otra carpeta)"
                        if st == "anio_distinto" else "carpeta distinta")
                if curp18 or fub_ig:
                    base = "CURP-18 identica" if curp18 else "FUB identico"
                    defs.append((ib, "definitivo",
                                 f"misma persona en otra carpeta ({base}); {carp}"))
                elif nombre_def:
                    _ok, _nota = _guarda_otra_carpeta(a, b, sim, n_toks)
                    if _ok:
                        _ok2, _nota2 = _guarda_fnac(a, b, sim, False)
                        if _ok2:
                            defs.append((ib, "definitivo",
                                         f"misma persona en otra carpeta "
                                         f"(nombre {sim:.2f}{_nota}); {carp}"))

        eval_por_rec[ia] = lst
        if defs:
            tiene_def[ia] = defs
        if _pb is not None:
            _pb.update()

    print(f"  Registros con match definitivo/parcial: {len(tiene_def):,}")

    # Puente de carpetas compartidas (para enriquecer la cola de revisión)
    def _obtener_serie_carpeta(df: pd.DataFrame, col: str) -> List[str]:
        if not col or col not in df.columns:
            return [""] * len(df)
        s = df[col]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        res = []
        for val in s:
            if val is None or pd.isna(val):
                res.append("")
            else:
                st = str(val).strip()
                res.append("" if st.lower() in ("nan", "none", "<na>") else st)
        return res

    carpeta_a_s = _obtener_serie_carpeta(banci, fol_a)
    carpeta_b_s = _obtener_serie_carpeta(comp, fol_b)
    puente: Dict[str, Set[str]] = defaultdict(set)
    for ia, defs in tiene_def.items():
        ca = carpeta_a_s[ia]
        for ib, _, _ in defs:
            cb = carpeta_b_s[ib]
            if ca and cb:
                puente[ca].add(cb)
    ib_por_carpeta: Dict[str, List[int]] = defaultdict(list)
    for ib in B:
        c = carpeta_b_s[ib]
        if c:
            ib_por_carpeta[c].append(ib)

    # ── 10. Un resultado por fila BANCI ───────────────────────────────────────
    # Prioridad: definitivo > parcial > revision > sin_match
    # Dentro de definitivos: COINCIDE fecha_hechos > SIN DATO > DIFIERE
    resultados: Dict[int, dict] = {}

    def _fh_prioridad(fh_st: str) -> int:
        if "COINCIDE" in fh_st:   return 2
        if "SIN DATO" in fh_st:   return 1
        return 0

    for ia, a in A.items():
        # ─ Definitivos ─
        if ia in tiene_def:
            mejor: Optional[dict] = None
            for ib, eva, mot in tiene_def[ia]:
                dias = _fhechos_dias(a, B[ib])
                if dias is None:
                    fh_st = "SIN DATO"
                elif dias <= VENTANA_FECHA_HECHOS_DIAS:
                    fh_st = f"COINCIDE ({dias} dias)"
                    mot = mot + f"; +fecha de hechos (+-{VENTANA_FECHA_HECHOS_DIAS} dias)"
                else:
                    fh_st = f"DIFIERE ({dias} dias)"

                cand = {
                    "id_match_refinado":          B[ib]["fub"],
                    "tipo_match_refinado":         eva,
                    "score_refinado":              100,
                    "variables_match_refinado":    mot,
                    "evaluacion_match_refinado":   eva,
                    "fecha_hechos_status_refinado": fh_st,
                    **{f"{k}_refinado": v
                       for k, v in _verificaciones_descriptivas(ia, ib, A, B).items()},
                }
                if mejor is None:
                    mejor = cand
                else:
                    p_new = (_PRIORIDAD_EVAL.get(eva, 0), _fh_prioridad(fh_st))
                    p_old = (_PRIORIDAD_EVAL.get(mejor["tipo_match_refinado"], 0),
                             _fh_prioridad(mejor["fecha_hechos_status_refinado"]))
                    if p_new > p_old:
                        mejor = cand
            resultados[ia] = mejor  # type: ignore[assignment]
            continue

        # ─ Revisión manual ─
        cand_ibs = {ib for ib, _, _, _ in eval_por_rec.get(ia, [])}
        ca = carpeta_a_s[ia]
        via_puente: Set[int] = set()
        for cb in puente.get(ca, ()):
            for ib in ib_por_carpeta.get(cb, []):
                cand_ibs.add(ib)
                via_puente.add(ib)

        opciones: List[Tuple] = []
        for ib in cand_ibs:
            b = B[ib]
            st, mot = _folio_limpio_status(
                a["cons"], a["anio"], a["claves"],
                b["cons"], b["alt"],  b["anio"], b["claves"],
            )
            folio_rel     = st in ("igual", "parcial", "anio_distinto")
            curp10_ig     = (len(a["curp"]) >= 10 and len(b["curp"]) >= 10
                             and a["curp"][:10] == b["curp"][:10])
            fnac_ig       = bool(a["fnac"]) and a["fnac"] == b["fnac"]
            ent_ig        = bool(a["ent"]) and a["ent"] == b["ent"]
            sexo_ig       = bool(a["sexo"]) and a["sexo"] == b["sexo"]
            muni_ig       = _muni_igual(a, b)
            sim           = similitud_nombres(a["nombre"], b["nombre"])
            tok_ok        = _tokens_nombre_coincidentes(a, b)
            nombre_evid   = sim >= UMBRAL_NOMBRE_MIN  and tok_ok >= MIN_TOKENS_NOMBRE
            nombre_fuerte = sim >= UMBRAL_NOMBRE_SOLO and tok_ok >= MIN_TOKENS_NOMBRE

            otras          = (["folio"]     if folio_rel  else []) + \
                             (["curp10"]    if curp10_ig  else []) + \
                             (["fnac"]      if fnac_ig    else []) + \
                             (["municipio"] if muni_ig    else []) + \
                             (["entidad"]   if ent_ig     else []) + \
                             (["sexo"]      if sexo_ig    else [])
            otras_no_gen  = [x for x in otras if x not in ("entidad", "sexo")]
            otras_fuertes = [x for x in otras if x in ("folio", "curp10", "fnac")]
            folio_espec   = (st in ("igual", "parcial")
                             and len(a["cons"]) >= LONGITUD_CONSEC_ESPECIFICO)

            if not (folio_espec or nombre_fuerte
                    or (nombre_evid and otras_no_gen)
                    or (len(otras) >= 2 and otras_fuertes)):
                continue

            sc, razones = 0.0, []
            if   st == "igual":         sc += W_FOLIO_LIMPIO;  razones.append("folio limpio igual")
            elif st == "parcial":       sc += W_FOLIO_PARCIAL; razones.append(f"folio parcial ({mot})")
            elif st == "anio_distinto": sc += 8;               razones.append("mismo consecutivo, anio distinto")
            if curp10_ig: sc += W_CURP10;    razones.append("curp10 igual")
            if fnac_ig:   sc += W_FNAC;      razones.append("fecha nac igual")
            if nombre_evid:
                sc += sim * W_NOMBRE; razones.append(f"nombre {sim:.2f} ({tok_ok} tokens)")
            elif tok_ok == 1:
                sc -= 5;              razones.append("solo 1 apellido coincide (no cuenta)")
            elif sim > 0:
                razones.append(f"nombre {sim:.2f} (bajo, no cuenta)")
            if muni_ig:  sc += W_MUNICIPIO; razones.append("municipio igual")
            if ent_ig:   sc += W_ENTIDAD;   razones.append("entidad (desempate)")
            if sexo_ig:  sc += W_SEXO;      razones.append("sexo (desempate)")
            if ib in via_puente:
                sc += W_PUENTE; razones.append("carpeta compartida")
            dias = _fhechos_dias(a, b)
            if dias is not None and dias <= VENTANA_FECHA_HECHOS_DIAS:
                razones.append(f"+fecha de hechos (+-{VENTANA_FECHA_HECHOS_DIAS} dias)")

            sc = min(99, int(round(sc)))
            if sc > 0:
                opciones.append((sc, ib, "; ".join(razones)))

        opciones.sort(key=lambda x: -x[0])

        if opciones:
            sc_top, ib_top, razones_top = opciones[0]
            resultados[ia] = {
                "id_match_refinado":           B[ib_top]["fub"],
                "tipo_match_refinado":         "revision manual",
                "score_refinado":              sc_top,
                "variables_match_refinado":    razones_top,
                "evaluacion_match_refinado":   "revision manual",
                "fecha_hechos_status_refinado": None,
                **{f"{k}_refinado": v
                   for k, v in _verificaciones_descriptivas(ia, ib_top, A, B).items()},
            }
        # else: sin match → queda fuera de resultados

    # ── 11. Construir DataFrame de salida usando índice original de df_banci ──
    out = pd.DataFrame(
        index=df_banci.index,
        columns=_COLS_SALIDA,
        dtype=object,
    )
    out["tipo_match_refinado"]  = "sin_match"
    out["score_refinado"]       = 0

    for ia, res in resultados.items():
        # ia es la posición 0-based en banci = df_banci.reset_index(drop=True)
        orig_idx = df_banci.index[ia]
        for col in _COLS_SALIDA:
            out.at[orig_idx, col] = res.get(col)

    n_matched = (out["tipo_match_refinado"] != "sin_match").sum()
    n_def     = (out["tipo_match_refinado"].isin(
                    ["definitivo", "parcial (algun caracter distinto)"]
                 )).sum()
    n_rev     = (out["tipo_match_refinado"] == "revision manual").sum()
    n_sin     = (out["tipo_match_refinado"] == "sin_match").sum()

    print(f"  ✅ [Motor Refinado] {n_matched:,} / {len(df_banci):,} matcheados  "
          f"(definitivos/parciales: {n_def:,}  revisión: {n_rev:,}  sin match: {n_sin:,})")

    return out
