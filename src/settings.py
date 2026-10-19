"""
Configuración como *datos*, no como estado global.

`config.py` conserva únicamente lo invariante del proyecto (rutas base, mapeos de
columnas, catálogos de regex, ENTIDADES). Todo lo que varía entre una PPT y otra
vive en un perfil TOML dentro de `perfiles/` y se materializa en un objeto
`Settings` inmutable que se pasa explícitamente a cada etapa del pipeline.

Esto permite que un mismo kernel de Jupyter tenga varias configuraciones vivas al
mismo tiempo (algo imposible con `importlib.reload(config)`) y, sobre todo, que
el sistema de caché sepa exactamente qué campos afectan a qué etapa.

Uso:
    from src.settings import Settings
    cfg = Settings.desde_perfil("reporte_diario")
    cfg_estatal = Settings.desde_perfil("estatal")      # coexisten sin conflicto
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Optional

import config

PERFILES_DIR = config.BASE_DIR / "perfiles"


_SENTINELA = object()


def _cfg(nombre: str, default=_SENTINELA):
    """Lee un valor de config.py con un error legible si no está.

    Un AttributeError crudo desde aquí casi siempre significa que el kernel de
    Jupyter tiene una copia vieja de `config` en `sys.modules` —típicamente tras
    editar config.py con el kernel vivo, o tras un `importlib.reload` a medias—.
    El archivo en disco suele estar bien; lo que hay que reiniciar es el kernel.
    """
    if hasattr(config, nombre):
        return getattr(config, nombre)
    if default is not _SENTINELA:
        return default
    raise AttributeError(
        f"config.py no define {nombre!r}.\n"
        f"  módulo cargado: {getattr(config, '__file__', '?')}\n"
        "  Si el archivo SÍ lo define, el kernel tiene una copia vieja en memoria:\n"
        "  reinicia el kernel (Kernel → Restart) y vuelve a ejecutar.\n"
        f"  Para confirmarlo:  import config; print(config.__file__, hasattr(config, {nombre!r}))"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades de resolución de rutas
# ─────────────────────────────────────────────────────────────────────────────
def _resolver_ruta(valor: Any) -> Optional[Path]:
    """Convierte un valor de perfil en Path absoluto (relativo a BASE_DIR)."""
    if valor is None or valor == "":
        return None
    p = Path(valor)
    return p if p.is_absolute() else (config.BASE_DIR / p)


def _firma_archivo(p: Optional[Path]) -> str:
    """Firma barata y estable de un archivo de entrada: nombre + tamaño + mtime.

    Se usa como parte de la llave de caché: si el archivo fuente cambia, la
    llave cambia y la etapa se recalcula. No se hace hash del contenido porque
    los insumos son Excel/Parquet de cientos de MB.
    """
    if p is None:
        return "none"
    if not p.exists():
        return f"{p.name}:missing"
    st = p.stat()
    return f"{p.name}:{st.st_size}:{int(st.st_mtime)}"


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────
# Campos que NO entran en `clave_matching`: los de la capa B (van en
# `clave_universo`), los de rebanado y salida, y el nombre del perfil —dos perfiles
# con la misma capa A comparten caché—. Todo campo nuevo entra por defecto: olvidar
# anotarlo aquí cuesta un recálculo de más, nunca un caché viejo.
_CAMPOS_CAPA_B = ("modalidad_clasificacion_carpeta", "modalidad_manual_clasificacion_carpeta",
                  "propagar_delito_banci")
_CAMPOS_FUERA_DE_CAPA_A = {"perfil", "estado", "periodos", "cache_dir", "resultados_dir",
                           *_CAMPOS_CAPA_B}


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de una corrida del pipeline.

    Los campos están agrupados por la CAPA que afectan. Esa agrupación no es
    decorativa: determina las llaves de caché (`clave_matching`, `clave_universo`)
    y por lo tanto qué se recalcula cuando cambias algo.
    """

    perfil: str = "base"

    # ── CAPA A · MATCHING (cara: minutos) ────────────────────────────────────
    rnpdno_etl_parquet: Optional[Path] = None
    banci_etl_parquet: Optional[Path] = None
    confrontas_file: Optional[Path] = None

    # Prioridad de la cascada, no orden de ejecución. `manual` primero: una revisión
    # humana del SESNSP pesa más que un match algorítmico cuando señalan a personas
    # distintas (ver el comentario en perfiles/base.toml).
    orden_prioridad_cascada: tuple[str, ...] = ("manual", "estandar", "refinado")
    # ¿Los motores corren EN CADENA, pasando al siguiente sólo lo que el anterior no
    # resolvió? false (default) = los tres ven el universo completo y la cascada elige
    # después. true = cada motor recibe el remanente del anterior, en el orden de
    # `orden_prioridad_cascada`: mucho más rápido, pero se pierde la corroboración
    # cruzada (`motores_match_consolidado` sólo puede nombrar a un motor).
    cascada_en_ejecucion: bool = False
    periodo_match: str = "01oct24-max"
    fecha_sexenio: str = "2024-10-01"
    reglas_post: tuple[str, ...] = ("excluir_revision_manual", "regla_r_desfase_dias")
    tolerancia_desfase_dias: int = 10
    # Excluye del cruce a los LOCALIZADOS de BANCI. Gobierna los dos sitios donde
    # se aplicaba por separado: el filtro interno del motor estándar
    # (`preparar_banci_r`) y el universo del refinado.
    filtrar_banci_no_localizados: bool = True
    # Excluye del cruce a los LOCALIZADOS del RNPDNO en los motores manual y
    # refinado (CLASIF_UNIVERSO en src/pipeline/motores.py). En false, el universo
    # es el RNPDNO completo: todo contra todo.
    filtrar_rnpdno_clasificacion: bool = True
    # El motor manual acepta el FUB que BANCI ya trae en `folio_RNPDNO` como match,
    # sin comparar nombre, CURP, fecha ni carpeta. Apagado: un identificador
    # pre-asignado no es evidencia, y esos registros quedan libres para que el motor
    # refinado los resuelva con evidencia real (el FUB igual sigue siendo una de sus
    # señales, pero ahí tiene que sostenerse contra la identidad).
    manual_usar_fub_preasignado: bool = False

    # Revisiones SESNSP (motores manual y refinado)
    refinado_ruta_verif: Optional[Path] = None
    refinado_ruta_revision: Optional[Path] = None
    refinado_hoja_verif: int = 0
    refinado_hoja_revision: int = 1
    refinado_skiprows_verif: int = 1
    refinado_skiprows_revision: int = 0

    # ── CAPA B · DERIVADAS (barata: segundos) ────────────────────────────────
    # Por defecto se toma de config.MODALIDAD_CLASIFICACION_CARPETA.
    modalidad_clasificacion_carpeta: Optional[int] = None
    # Suma a la modalidad todos los FUBs de los Excel de revisión manual
    # (config.CARPETAS_MANUALES_DIR). Por defecto se toma de
    # config.MODALIDAD_MANUAL_CLASIFICACION_CARPETA.
    modalidad_manual_clasificacion_carpeta: Optional[bool] = None
    # `delitolocalizacion` del RNPDNO sólo existe para Localizados, así que el tipo
    # de desaparición de los matcheados se toma de BANCI. Ponlo en false para usar
    # únicamente el RNPDNO (is_dfor / is_cpar quedarán en 0 para desaparecidos).
    propagar_delito_banci: bool = True

    # ── CAPA C · REBANADAS (gratis: microsegundos) ───────────────────────────
    # `estado` YA NO filtra antes del matching. Es una dimensión de rebanada:
    # el universo se construye siempre nacional y cada PPT corta la entidad que
    # necesita. Una corrida de matching sirve para las 32 entidades.
    estado: Optional[int] = None
    periodos: dict[str, tuple] = field(default_factory=dict)

    # ── SALIDA ───────────────────────────────────────────────────────────────
    cache_dir: Optional[Path] = None
    resultados_dir: Optional[Path] = None

    # ── Construcción ─────────────────────────────────────────────────────────
    @classmethod
    def desde_perfil(cls, nombre: str = "base", **overrides) -> "Settings":
        """Carga `perfiles/<nombre>.toml`, resolviendo la cadena de `extends`."""
        datos = _cargar_perfil_encadenado(nombre)
        datos["perfil"] = nombre
        datos.update(overrides)
        return cls.desde_dict(datos)

    @classmethod
    def desde_dict(cls, datos: dict) -> "Settings":
        d = dict(datos)

        # Rutas: default a lo que ya define config.py (backward-compatible)
        d["rnpdno_etl_parquet"] = _resolver_ruta(
            d.get("rnpdno_etl_parquet")
        ) or (_cfg("OUTPUT_DIR") / "Resultado_1_Procesamiento_ETL_RNPDNO.parquet")
        d["banci_etl_parquet"] = _resolver_ruta(
            d.get("banci_etl_parquet")
        ) or (_cfg("OUTPUT_DIR") / "Resultado_2_Procesamiento_ETL_BANCI.parquet")
        d["confrontas_file"] = _resolver_ruta(d.get("confrontas_file")) or _cfg("CONFRONTAS_FILE")
        d["refinado_ruta_verif"] = _resolver_ruta(
            d.get("refinado_ruta_verif")
        ) or _cfg("REFINADO_RUTA_VERIF_FECHA_HECHOS", None)
        d["refinado_ruta_revision"] = _resolver_ruta(
            d.get("refinado_ruta_revision")
        ) or _cfg("REFINADO_RUTA_REVISION_MANUAL", None)

        # La modalidad de carpeta la manda config.py salvo que el perfil la sobrescriba.
        if d.get("modalidad_clasificacion_carpeta") is None:
            d["modalidad_clasificacion_carpeta"] = _cfg("MODALIDAD_CLASIFICACION_CARPETA", 1)
        if d.get("modalidad_manual_clasificacion_carpeta") is None:
            d["modalidad_manual_clasificacion_carpeta"] = bool(
                _cfg("MODALIDAD_MANUAL_CLASIFICACION_CARPETA", False))

        d["cache_dir"] = _resolver_ruta(d.get("cache_dir")) or (_cfg("OUTPUT_DIR") / "cache")
        d["resultados_dir"] = _resolver_ruta(d.get("resultados_dir")) or _cfg("RESULTADOS_INDICADORES_DIR")

        # Tuplas para que el objeto sea realmente inmutable
        for k in ("orden_prioridad_cascada", "reglas_post"):
            if k in d and d[k] is not None:
                d[k] = tuple(d[k])

        # Los períodos del perfil se superponen sobre el catálogo de config.py
        periodos = {k: tuple(v) for k, v in _cfg("PERIODOS_TIEMPO").items()}
        for k, v in (d.get("periodos") or {}).items():
            periodos[k] = tuple(x if x else None for x in v)
        d["periodos"] = periodos

        # Normalizar `estado`: acepta clave numérica, nombre de entidad, o los
        # marcadores "nacional" / "" / 0 para el universo completo (TOML no tiene null).
        est = d.get("estado")
        if isinstance(est, str):
            if est.strip().lower() in ("", "nacional", "none", "null"):
                d["estado"] = None
            else:
                from src.utils import get_id_estado
                cve = get_id_estado(est, _cfg("ENTIDADES"))
                if cve is None:
                    raise ValueError(f"Entidad desconocida en el perfil: {est!r}")
                d["estado"] = cve
        elif est == 0:
            d["estado"] = None

        validos = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in validos})

    def con(self, **cambios) -> "Settings":
        """Devuelve una copia con campos modificados (no muta el original)."""
        return replace(self, **cambios)

    # ── Parámetros derivados ─────────────────────────────────────────────────
    @property
    def params_motores(self) -> dict:
        """Parámetros de los motores manual y refinado, tal como los espera
        `motor_match_manual` / `motor_match_refinado`."""
        comunes = {
            "ruta_verif_fecha_hechos": self.refinado_ruta_verif,
            "ruta_revision_manual": self.refinado_ruta_revision,
            "hoja_verif": self.refinado_hoja_verif,
            "hoja_revision": self.refinado_hoja_revision,
            "skiprows_verif": self.refinado_skiprows_verif,
            "skiprows_revision": self.refinado_skiprows_revision,
            "col_mapping_verif": _cfg("REFINADO_VERIF_COLUMN_MAPPING", {}),
            "col_mapping_revision": _cfg("REFINADO_REVISION_COLUMN_MAPPING", {}),
        }
        manual = dict(comunes)
        manual["usar_fub_preasignado"] = self.manual_usar_fub_preasignado
        return {"manual": manual, "refinado": dict(comunes)}

    @property
    def regex_carpeta(self) -> str:
        """Regex de carpeta de investigación según la modalidad configurada."""
        return _cfg("RNPDNO_REGEX_CARPETA")

    def rango_periodo(self, nombre: str) -> tuple:
        if nombre not in self.periodos:
            raise KeyError(
                f"Período '{nombre}' no definido. Disponibles: {sorted(self.periodos)}"
            )
        return self.periodos[nombre]

    # ── Llaves de caché ──────────────────────────────────────────────────────
    def _hash(self, payload: dict) -> str:
        s = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    @property
    def clave_matching(self) -> str:
        """Llave del caché de la CAPA A. Cambia si cambia cualquier cosa que pueda
        mover un cruce:

            · cualquier campo del perfil que no sea de las capas B o C
            · el RANGO de `periodo_match`, no sólo su nombre
            · config.py tal como lo ve esta corrida (`huella.huella_config`)
            · el código de los motores y todo lo que importan (`huella.huella_codigo`)
            · la firma de los insumos declarados en el perfil

        NO cambia al cambiar período de rebanado, estatus, subfiltro o entidad.
        Los demás archivos que lee la capa (catálogos, revisiones…) no entran aquí
        sino junto al caché: `Universo.construir` revisa sus firmas al leerlo.
        """
        from src.pipeline import huella
        from src.pipeline.motores import VERSION_MATCHING
        return self._hash({
            "version_matching": VERSION_MATCHING,
            "campos": {f.name: getattr(self, f.name) for f in fields(self)
                       if f.name not in _CAMPOS_FUERA_DE_CAPA_A},
            "rango_periodo_match": self.periodos.get(self.periodo_match),
            "config": huella.huella_config(),
            "codigo": huella.huella_codigo("matching"),
            "fuentes": [
                _firma_archivo(self.rnpdno_etl_parquet),
                _firma_archivo(self.banci_etl_parquet),
                _firma_archivo(self.confrontas_file),
                _firma_archivo(self.refinado_ruta_verif),
                _firma_archivo(self.refinado_ruta_revision),
            ],
        })

    @property
    def clave_universo(self) -> str:
        """Llave del caché de la CAPA B: la de matching más los campos de la capa B,
        el código de las derivadas y, con la validación manual de carpeta activa, la
        firma de cada Excel de revisión: un Excel nuevo en la carpeta no lo vería el
        registro de lecturas del caché viejo."""
        from src.pipeline import huella
        from src.pipeline.derivadas import VERSION_DERIVADAS
        return self._hash({
            "matching": self.clave_matching,
            "version_derivadas": VERSION_DERIVADAS,
            "campos": {c: getattr(self, c) for c in _CAMPOS_CAPA_B},
            "codigo": huella.huella_codigo("universo"),
            "carpetas_manuales": ([_firma_archivo(p) for p in config.archivos_carpetas_manuales()]
                                  if self.modalidad_manual_clasificacion_carpeta else []),
        })

    def resumen(self) -> str:
        return (
            f"Settings(perfil={self.perfil!r})\n"
            f"  BANCI ETL   : {self.banci_etl_parquet.name}\n"
            f"  RNPDNO ETL  : {self.rnpdno_etl_parquet.name}\n"
            f"  Confrontas  : {self.confrontas_file.name}\n"
            f"  Cascada     : {' → '.join(self.orden_prioridad_cascada)}\n"
            f"  Carpeta     : modalidad {self.modalidad_clasificacion_carpeta}"
            f"{' + revisión manual' if self.modalidad_manual_clasificacion_carpeta else ''}\n"
            f"  Reglas post : {', '.join(self.reglas_post) or '(ninguna)'}\n"
            f"  Entidad     : {config.ENTIDADES.get(self.estado, 'Nacional') if self.estado else 'Nacional'}"
            f"  (dimensión de rebanada, no filtro pre-matching)\n"
            f"  clave_matching={self.clave_matching}  clave_universo={self.clave_universo}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Carga de perfiles TOML con herencia
# ─────────────────────────────────────────────────────────────────────────────
def _cargar_perfil_encadenado(nombre: str, _vistos: Optional[set] = None) -> dict:
    _vistos = _vistos or set()
    if nombre in _vistos:
        raise ValueError(f"Ciclo de herencia en perfiles: {nombre}")
    _vistos.add(nombre)

    ruta = PERFILES_DIR / f"{nombre}.toml"
    if not ruta.exists():
        disponibles = sorted(p.stem for p in PERFILES_DIR.glob("*.toml"))
        raise FileNotFoundError(
            f"No existe el perfil '{nombre}' ({ruta}). Disponibles: {disponibles}"
        )

    with open(ruta, "rb") as fh:
        datos = tomllib.load(fh)

    padre = datos.pop("extends", None)
    if padre:
        base = _cargar_perfil_encadenado(padre, _vistos)
        base.update(datos)   # el hijo gana
        return base
    return datos


def perfiles_disponibles() -> list[str]:
    return sorted(p.stem for p in PERFILES_DIR.glob("*.toml"))
