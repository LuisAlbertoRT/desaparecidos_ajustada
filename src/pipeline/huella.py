"""Huellas que deciden si un caché del pipeline sigue valiendo.

Un caché sólo puede reutilizarse si TODO lo que pudo influir en él es igual que
cuando se escribió. Ese "todo" se mide aquí en cuatro partes:

    huella_config()          config.py como lo ve esta corrida: sus valores y sus funciones
    huella_codigo(capa)      el código de la capa y todo lo que importa del proyecto
    registrar_lecturas()     los archivos que la capa leyó, con su firma al leerlos
    editados_en_sesion(capa) código cambiado después de arrancar este proceso

Las dos primeras entran en la llave del caché (`Settings.clave_matching`,
`Settings.clave_universo`): si cambian, la llave es otra y el caché viejo ya no
se encuentra. La tercera se guarda junto al caché y se revisa al leerlo, porque
qué archivos se leen sólo se sabe después de correr la capa. La cuarta impide
ESCRIBIR un caché desde un kernel que quizá corre una versión anterior del
código: la llave se calcula con el código en disco, y el resultado se calcularía
con el que está en memoria.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
import types
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import config

_RAIZ = Path(config.BASE_DIR).resolve()

# Los módulos de entrada de cada capa. La huella sigue sus imports, también los
# que se hacen dentro de una función.
RAICES = {
    "matching": ("src/pipeline/carga.py", "src/pipeline/motores.py"),
    "universo": ("src/pipeline/derivadas.py", "src/pipeline/universo.py"),
}

try:
    import psutil
    _INICIO = psutil.Process().create_time()
except Exception:                       # sin psutil: desde que se importó este módulo
    _INICIO = time.time()


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# config.py
# ─────────────────────────────────────────────────────────────────────────────
def _codigo(co: types.CodeType) -> list:
    """Lo que ejecuta un objeto de código, sin números de línea ni ruta: comentar
    o mover una función no cambia su huella."""
    return [co.co_code.hex(), [_constante(c) for c in co.co_consts], list(co.co_names),
            list(co.co_varnames), co.co_argcount, co.co_kwonlyargcount, co.co_flags]


def _constante(c):
    if isinstance(c, types.CodeType):
        return _codigo(c)
    if isinstance(c, (set, frozenset)):
        return sorted(map(repr, c))
    if isinstance(c, tuple):
        return [_constante(x) for x in c]
    return repr(c)


def _dato(v):
    """Forma estable de un valor de config: igual en dos procesos si el valor es igual."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, re.Pattern):
        return [v.pattern, v.flags]
    if isinstance(v, types.FunctionType):
        return [_codigo(v.__code__), _dato(v.__defaults__), _dato(v.__kwdefaults__)]
    if isinstance(v, dict):
        return [[_dato(k), _dato(x)] for k, x in v.items()]     # el orden importa
    if isinstance(v, (list, tuple)):
        return [_dato(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted((_dato(x) for x in v), key=repr)
    return f"<{type(v).__name__}>"


def huella_config() -> str:
    """config.py tal como lo ve ESTA corrida, no como está en disco.

    Se toman los valores que dejó al importarse —no su texto— porque varios
    dependen del entorno (`PIPELINE_MODO_INSUMOS`…) o del archivo que encontró un
    `glob`: el mismo texto puede dar otra configuración. Y se toman de memoria
    porque es lo que usan los motores: un config.py editado pero no recargado
    sigue calculando con lo anterior, y la llave tiene que decir eso mismo.

    Quedan fuera las rutas dentro de OUTPUT_DIR: son salidas y no cambian ningún
    cálculo, y alguna lleva la fecha de hoy (`PPT_DIARIO_FILE`), que invalidaría
    el caché cada día. Las que sí se leen (los Parquet del ETL) entran por el
    perfil y por `registrar_lecturas`.
    """
    salida = Path(config.OUTPUT_DIR).resolve()
    valores = {}
    for nombre, v in vars(config).items():
        if nombre.startswith("__") or isinstance(v, (types.ModuleType, type)):
            continue
        if callable(v) and getattr(v, "__module__", None) != config.__name__:
            continue                    # lo importado (Path, date…) no es configuración
        if isinstance(v, Path) and v.resolve().is_relative_to(salida):
            continue
        valores[nombre] = _dato(v)
    return _hash(json.dumps(valores, sort_keys=True, default=repr))


# ─────────────────────────────────────────────────────────────────────────────
# Código
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=None)
def _leer_modulo(ruta: Path, _firma: tuple) -> tuple[str, tuple[str, ...]]:
    """(volcado del AST, módulos que importa). El volcado no lleva comentarios ni
    números de línea. `_firma` sólo sirve para que un archivo editado se relea."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    importados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados += [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
            importados += [nodo.module] + [f"{nodo.module}.{a.name}" for a in nodo.names]
    return ast.dump(arbol), tuple(importados)


def _archivo_de_modulo(nombre: str) -> Optional[Path]:
    # config.py no se sigue: entra por `huella_config`, con lo que hay en memoria.
    if nombre == "config":
        return None
    base = _RAIZ.joinpath(*nombre.split("."))
    for candidato in (base.with_suffix(".py"), base / "__init__.py"):
        if candidato.is_file():
            return candidato
    return None


def _cierre(capa: str) -> dict[Path, str]:
    """Los archivos del proyecto que puede ejecutar la capa, con su volcado.

    Se sigue el módulo importado y no el `__init__` de los paquetes que lo
    contienen: `from src.pipeline.reglas import x` depende de reglas.py, no de
    todo `src/pipeline/`.
    """
    pendientes = [_RAIZ / r for r in RAICES[capa]]
    vistos: dict[Path, str] = {}
    while pendientes:
        ruta = pendientes.pop()
        if ruta in vistos:
            continue
        st = ruta.stat()
        volcado, importados = _leer_modulo(ruta, (st.st_mtime_ns, st.st_size))
        vistos[ruta] = volcado
        pendientes += [a for a in map(_archivo_de_modulo, importados) if a is not None]
    return vistos


def huella_codigo(capa: str) -> str:
    cierre = _cierre(capa)
    return _hash(json.dumps({str(r.relative_to(_RAIZ)): cierre[r] for r in sorted(cierre)}))


def editados_en_sesion(capa: str) -> list[str]:
    """Archivos del código de la capa modificados después de arrancar este proceso.

    Python no vuelve a leer un módulo ya importado: un kernel abierto antes de la
    edición calcula con el código viejo. Ese resultado no debe guardarse bajo la
    llave del código nuevo.
    """
    return [str(r.relative_to(_RAIZ)) for r in sorted(_cierre(capa))
            if r.stat().st_mtime > _INICIO]


# ─────────────────────────────────────────────────────────────────────────────
# Archivos leídos
# ─────────────────────────────────────────────────────────────────────────────
def firma(ruta) -> Optional[list]:
    """Tamaño y fecha de modificación (ns). `None` si el archivo ya no existe."""
    try:
        st = os.stat(ruta)
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def archivos_cambiados(dependencias: dict[str, list]) -> list[str]:
    """Los archivos registrados cuya firma ya no es la que tenían al leerse."""
    return [r for r, f in dependencias.items() if firma(r) != f]


# Registros activos: (archivos leídos, carpetas excluidas). Una pila porque los
# registros pueden anidarse.
_ACTIVOS: list[tuple[dict, tuple[Path, ...]]] = []
_SISTEMA = tuple({Path(p).resolve() for p in (sys.prefix, sys.base_prefix, sys.exec_prefix,
                                              "/usr", "/proc", "/sys", "/dev", "/etc")})
_EXT_CODIGO = {".py", ".pyc", ".so", ".pyd", ".pth"}
_auditoria_instalada = False


def _anotar(ruta) -> None:
    if not _ACTIVOS or not isinstance(ruta, (str, os.PathLike)):
        return
    try:
        p = Path(ruta).resolve()
        if p.suffix in _EXT_CODIGO or not p.is_file() or any(p.is_relative_to(d) for d in _SISTEMA):
            return
    except (OSError, ValueError, RuntimeError):
        return
    f = firma(p)
    for leidos, excluidas in _ACTIVOS:
        if not any(p.is_relative_to(d) for d in excluidas):
            leidos.setdefault(str(p), f)


def _auditar(evento, args):
    # Un gancho de auditoría no debe fallar nunca: su excepción rompería el `open`.
    if evento != "open" or not _ACTIVOS:
        return
    try:
        ruta, modo, banderas = args
        if modo is None:                # os.open: se decide por las banderas
            if banderas & (os.O_WRONLY | os.O_RDWR):
                return
        elif any(c in modo for c in "wax+"):
            return
        _anotar(ruta)
    except Exception:
        pass


@contextmanager
def registrar_lecturas(excluir=()):
    """Anota cada archivo que se lee dentro del bloque, con su firma al leerlo.

    Casi toda lectura pasa por `open` y la ve el gancho de auditoría (CSV, Excel,
    JSON…). Parquet no: pyarrow abre el archivo por su cuenta, así que sus
    funciones de lectura se envuelven mientras dura el bloque.
    """
    global _auditoria_instalada
    if not _auditoria_instalada:
        sys.addaudithook(_auditar)      # no se puede quitar; fuera de un bloque no hace nada
        _auditoria_instalada = True

    leidos: dict[str, list] = {}
    entrada = (leidos, tuple(Path(e).resolve() for e in excluir))
    _ACTIVOS.append(entrada)
    parches = _envolver_parquet() if len(_ACTIVOS) == 1 else []
    try:
        yield leidos
    finally:
        _ACTIVOS.remove(entrada)
        for modulo, nombre, original in parches:
            setattr(modulo, nombre, original)


def _envolver_parquet() -> list:
    import pandas as pd
    import pyarrow.parquet as pq

    parches = []
    for modulo, nombre in ((pq, "read_table"), (pq, "read_schema"),
                           (pq, "read_metadata"), (pd, "read_parquet")):
        original = getattr(modulo, nombre)

        def envoltura(*a, _original=original, **k):
            _anotar(a[0] if a else next(iter(k.values()), None))
            return _original(*a, **k)

        setattr(modulo, nombre, envoltura)
        parches.append((modulo, nombre, original))
    return parches
