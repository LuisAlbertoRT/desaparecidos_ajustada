#!/usr/bin/env python3
"""Regenera README.md y DOCUMENTACION_COMPLETA.md a partir de sus fuentes.

Las dos son concatenaciones, no documentos que se editen a mano:

    README.md                = README_base.md + MANUAL_DE_USUARIO_CONCEPTUAL.md
    DOCUMENTACION_COMPLETA.md = README_base.md + MANUAL + docs/1..9

Editar el trozo que toque y volver a correr:

    python generar_documentacion.py
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASE = RAIZ / "README_base.md"
MANUAL = RAIZ / "MANUAL_DE_USUARIO_CONCEPTUAL.md"
DOCS = [RAIZ / "docs" / n for n in (
    "1_fuentes_de_informacion.md",
    "2_flujo_y_pipeline.md",
    "3_metodologia_de_matching.md",
    "4_generacion_de_reportes.md",
    "5_diccionario_de_variables.md",
    "6_arquitectura.md",
    "7_llaves_de_cruce.md",
    "8_indicios_de_vida.md",
    "9_credenciales_google_drive.md",
)]

SEP = "\n\n---\n\n"


def _leer(p: Path) -> str:
    if not p.exists():
        raise FileNotFoundError(f"Falta la fuente: {p}")
    return p.read_text(encoding="utf-8").strip()


# Nombres de los docs, para reescribir los enlaces entre ellos.
_NOMBRES_DOCS = {d.name for d in DOCS}


def _reapuntar(texto: str) -> str:
    """Corrige los enlaces relativos de un doc de `docs/` al pegarlo en la raíz.

    Dentro de `docs/`, `../catalogo_abreviaturas.md` y `6_arquitectura.md` son
    correctos. Concatenados en DOCUMENTACION_COMPLETA.md —que vive en la raíz—
    apuntarian a archivos inexistentes, asi que se reescriben.
    """
    def _sub(m):
        etiqueta, url, ancla = m.group(1), m.group(2), m.group(3) or ""
        if url.startswith("../"):
            url = url[3:]
        elif url in _NOMBRES_DOCS:
            url = f"docs/{url}"
        return f"[{etiqueta}]({url}{ancla})"

    return re.sub(r"\[([^\]]+)\]\(([^)#]+?)(#[^)]*)?\)", _sub, texto)


def main() -> None:
    base, manual = _leer(BASE), _leer(MANUAL)

    (RAIZ / "README.md").write_text(
        SEP.join([base, manual]) + "\n", encoding="utf-8")
    (RAIZ / "DOCUMENTACION_COMPLETA.md").write_text(
        SEP.join([base, manual] + [_reapuntar(_leer(d)) for d in DOCS]) + "\n",
        encoding="utf-8")

    for nombre in ("README.md", "DOCUMENTACION_COMPLETA.md"):
        p = RAIZ / nombre
        print(f"  ✅ {nombre}: {len(p.read_text(encoding='utf-8').splitlines()):,} líneas")


if __name__ == "__main__":
    main()
