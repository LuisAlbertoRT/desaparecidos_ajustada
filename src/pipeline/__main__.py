"""CLI para construir el universo fuera de Jupyter.

    python -m src.pipeline build --perfil reporte_diario
    python -m src.pipeline build --perfil estatal --forzar-matching
    python -m src.pipeline info   --perfil reporte_diario
    python -m src.pipeline limpiar --perfil base --nivel universo

Sirve para precalentar el caché (por ejemplo de madrugada o en CI) para que los
notebooks de PPT abran siempre con un acierto de caché.
"""

from __future__ import annotations

import argparse
import sys

from src.settings import Settings, perfiles_disponibles


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for nombre, ayuda in [("build", "construye el universo"),
                          ("info", "muestra la configuración y el estado del caché"),
                          ("limpiar", "borra el caché")]:
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--perfil", default="base", help=f"uno de {perfiles_disponibles()}")
        if nombre == "build":
            p.add_argument("--forzar", action="store_true", help="recalcula todo")
            p.add_argument("--forzar-matching", action="store_true",
                           help="recalcula los motores aunque haya caché")
            p.add_argument("--silencioso", action="store_true")
        if nombre == "limpiar":
            p.add_argument("--nivel", choices=["universo", "matching", "todo"], default="todo")

    args = ap.parse_args(argv)
    cfg = Settings.desde_perfil(args.perfil)

    if args.cmd == "info":
        from src.pipeline.universo import ARCHIVOS_MATCHING, ARCHIVOS_UNIVERSO, _vigente
        print(cfg.resumen())
        for nivel, clave, archivos in (("matching", cfg.clave_matching, ARCHIVOS_MATCHING),
                                       ("universo", cfg.clave_universo, ARCHIVOS_UNIVERSO)):
            d = cfg.cache_dir / nivel / clave
            estado = "✅ vigente" if _vigente(d, archivos, nivel, True) else "— ausente o descartado"
            print(f"  caché {nivel:<9}: {estado}  ({d})")
        return 0

    if args.cmd == "limpiar":
        from src.pipeline.universo import limpiar_cache
        limpiar_cache(cfg, args.nivel)
        return 0

    from src.pipeline.universo import Universo
    u = Universo.construir(cfg, forzar=args.forzar,
                           forzar_matching=args.forzar_matching,
                           verbose=not args.silencioso)
    print(f"\n✅ Universo listo — RNPDNO {len(u.rn):,} | BANCI {len(u.ba):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
