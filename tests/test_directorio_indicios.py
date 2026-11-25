import ast
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import config
from src.directorio_indicios import indicios_formalizados


class IndiciosFormalizadosTests(unittest.TestCase):
    def test_marcadores_de_32_entidades_usan_el_universo_de_cada_grafica(self):
        directorio = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "estado_de_desaparicion": [
                "Jalisco", "Tamaulipas", None, None, "Se desconoce", "Jalisco",
            ],
        })
        comprimido = pd.DataFrame({
            "fub_rnpdno": directorio["fub"],
            "clasificacion_des_derivada_rnpdno": [
                "Localizados", "Localizados", "Localizados",
                "Localizados", "Localizados", "Desaparecidos",
            ],
            "nombre_entidad_derivada_rnpdno": [None, None, "Jalisco", None, None, None],
            "estado_final_nuevo": [None] * 6,
        })
        with patch("src.directorio_indicios.leer_excel", return_value=directorio), \
             patch("src.directorio_indicios.IMPUTACION_CURP_FILE") as ruta:
            ruta.exists.return_value = False
            _, tabla, fmz = indicios_formalizados(comprimido, verbose=False)
            _, tabla_imp, fmz_imp = indicios_formalizados(
                comprimido, verbose=False, imputar=True
            )

        notebook = Path(__file__).resolve().parents[1] / "notebooks" / "6_PPT_Reporte_Diario.ipynb"
        celdas = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
        arboles = [
            ast.parse("".join(celda["source"]))
            for celda in celdas if celda["cell_type"] == "code"
            and ("MARCADOR_FMZ =" in "".join(celda["source"])
                 or "MARCADOR_FMZ_NAC:" in "".join(celda["source"]))
        ]
        nombres = {
            "MARCADOR_FMZ",
            "MARCADOR_FMZ_NAC",
            "MARCADOR_FMZ_32_IMP",
            "MARCADOR_FMZ_UNIVERSO",
            "MARCADOR_FMZ_BUSQUEDA",
            "MARCADOR_FMZ_BUSQUEDA_PCT",
            "MARCADOR_FMZ_OTRAS",
            "MARCADOR_FMZ_OTRAS_PCT",
        }
        asignaciones = [
            nodo for arbol in arboles for nodo in arbol.body
            if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1
            and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id in nombres
        ]
        entorno = {"config": config, "fmz": fmz, "fmz_imp": fmz_imp}
        exec(compile(ast.Module(body=asignaciones, type_ignores=[]), str(notebook), "exec"), entorno)
        entorno.update({
            "universo_fmz": fmz["universo_nacional"],
            "universo_busqueda": fmz["universo"],
            "universo_otras": fmz["universo_nacional"] - fmz["universo"],
            "pct_universo_busqueda": (
                f"{100 * fmz['universo'] / fmz['universo_nacional']:.1f}%"
                if fmz["universo_nacional"] else "n/d"
            ),
            "pct_universo_otras": (
                f"{100 * (fmz['universo_nacional'] - fmz['universo']) / fmz['universo_nacional']:.1f}%"
                if fmz["universo_nacional"] else "n/d"
            ),
        })
        extras = next(
            argumento.value for arbol in arboles for nodo in arbol.body
            if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call)
            for argumento in nodo.value.keywords if argumento.arg == "extra"
        )
        valores = {
            entorno[clave.id]: eval(compile(ast.Expression(valor), str(notebook), "eval"), entorno)
            for clave, valor in zip(extras.keys, extras.values)
            if isinstance(clave, ast.Name) and clave.id in nombres
        }
        marcador = f"reg_rn_{config.DIRECTORIO_INDICIOS_CORTE}-max_loc_fmz"
        self.assertEqual(fmz["nacional"], 5)
        self.assertEqual(fmz["universo_nacional"], len(directorio))
        self.assertEqual(int(tabla["localizados"].sum()), 2)
        self.assertEqual(int(tabla_imp["localizados"].sum()), 3)
        self.assertEqual(valores[f"{marcador}_v2"], int(tabla["localizados"].sum()))
        self.assertEqual(valores[f"{marcador}_v2_v3"], int(tabla_imp["localizados"].sum()))
        self.assertEqual(valores[f"reg_rn_{config.DIRECTORIO_INDICIOS_CORTE}-max_p1"], 6)
        self.assertEqual(valores["r_p8"], fmz["universo"])
        self.assertEqual(valores["r_p8_1"], f"{100 * fmz['universo'] / 6:.1f}%")
        self.assertEqual(valores["r_p9"], 6 - fmz["universo"])
        self.assertEqual(valores["r_p9_1"], f"{100 * (6 - fmz['universo']) / 6:.1f}%")

    def test_imputar_con_columnas_de_entidad_totalmente_vacias(self):
        directorio = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4"],
            "estado_de_desaparicion": [None, None, None, None],
        })
        curps = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4"],
            "curp_vic": ["AAAA800101HDFAAA01", None, None, None],
        })
        casos = [
            ([None] * 4, ["Jalisco", None, None, None], "Jalisco"),
            ([None] * 4, [None] * 4, "Ciudad de México"),
            (["Se desconoce"] * 4, [None] * 4, "Ciudad de México"),
        ]
        for paso1, paso2, entidad in casos:
            with self.subTest(paso1=paso1, paso2=paso2):
                comprimido = pd.DataFrame({
                    "fub_rnpdno": ["FUB1", "FUB2", "FUB3", "FUB4"],
                    "clasificacion_des_derivada_rnpdno": [
                        "Localizados", "Localizados", "Localizados", "Desaparecidos",
                    ],
                    "nombre_entidad_derivada_rnpdno": pd.array(paso1, dtype="string[pyarrow]"),
                    "estado_final_nuevo": pd.array(paso2, dtype="string[pyarrow]"),
                })
                with patch("src.directorio_indicios.leer_excel", return_value=directorio), \
                     patch("src.directorio_indicios.IMPUTACION_CURP_FILE") as ruta, \
                     patch("src.directorio_indicios.pd.read_parquet", return_value=curps):
                    ruta.exists.return_value = True
                    _, tabulado_32, conteos = indicios_formalizados(
                        comprimido, verbose=False, imputar=True
                    )

                localizados = tabulado_32.set_index("estado_de_desaparicion")["localizados"]
                self.assertEqual(localizados.get(entidad, 0), 1)
                self.assertEqual(conteos["sin_estado"], 2)
                self.assertEqual(int(tabulado_32["todavia_desaparecidos"].sum()), 0)

    def test_cuenta_registros_sin_entidad_y_no_los_incluye_en_las_graficas(self):
        directorio = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "estado_de_desaparicion": [
                None,
                33,
                "33",
                "Nacido en el extranjero",
                "nAcIdO   En El ExTrAnJeRo",
                "Tamaulipas",
            ],
        })
        comprimido = pd.DataFrame({
            "fub_rnpdno": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "clasificacion_des_derivada_rnpdno": [
                "Localizados",
                "Desaparecidos",
                "Desaparecidos",
                "Localizados",
                "Desaparecidos",
                "Localizados",
            ],
        })

        with patch("src.directorio_indicios.leer_excel", return_value=directorio):
            tabulado, tabulado_32, conteos = indicios_formalizados(
                comprimido, verbose=False
            )

        self.assertEqual(conteos["sin_estado"], 2)
        self.assertNotIn(
            config.DIRECTORIO_INDICIOS_SIN_ESTADO,
            tabulado["estado_de_desaparicion"].tolist(),
        )
        self.assertNotIn(
            config.DIRECTORIO_INDICIOS_SIN_ESTADO,
            tabulado_32["estado_de_desaparicion"].tolist(),
        )

    def test_imputar_resuelve_la_entidad_en_cascada(self):
        directorio = pd.DataFrame({
            "fub": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "estado_de_desaparicion": [
                None,                         # paso 1: nombre_entidad_derivada_rnpdno
                "Nacido en el extranjero",    # paso 2: estado_final_nuevo
                "33",                         # paso 3: entidad de la CURP
                None,                         # sin resolver: queda "Sin información"
                "Tamaulipas",                 # con entidad: no se toca
                None,                         # desaparecido: NO se imputa
            ],
        })
        comprimido = pd.DataFrame({
            "fub_rnpdno": ["FUB1", "FUB2", "FUB3", "FUB4", "FUB5", "FUB6"],
            "clasificacion_des_derivada_rnpdno": [
                "Localizados", "Localizados", "Localizados",
                "Localizados", "Localizados", "Desaparecidos",
            ],
            "nombre_entidad_derivada_rnpdno": [
                "Jalisco", "Se desconoce", None, None, "Tamaulipas", "Jalisco",
            ],
            "estado_final_nuevo": [None, "México", "Se desconoce", None, None, None],
        })
        curps = pd.DataFrame({
            "fub": ["FUB3", "FUB4"],
            # El código de estado son las posiciones 12-13: "DF" → Ciudad de México.
            "curp_vic": ["AAAA800101HDFAAA01", None],
        })

        with patch("src.directorio_indicios.leer_excel", return_value=directorio), \
             patch("src.directorio_indicios.IMPUTACION_CURP_FILE") as ruta, \
             patch("src.directorio_indicios.pd.read_parquet", return_value=curps):
            ruta.exists.return_value = True
            ruta.name = "reporte_personas_completo.parquet"
            _, tabulado_32, conteos = indicios_formalizados(
                comprimido, verbose=False, imputar=True
            )

        self.assertEqual(conteos["sin_estado"], 1)
        localizados = tabulado_32.set_index("estado_de_desaparicion")["localizados"]
        self.assertEqual(localizados.get("Jalisco", 0), 1)
        self.assertEqual(localizados.get("Estado de México", 0), 1)
        self.assertEqual(localizados.get("Ciudad de México", 0), 1)
        self.assertEqual(localizados.get("Tamaulipas", 0), 1)
        # El desaparecido sin entidad NO se imputa: las barras de
        # "todavía desaparecidos" no se mueven respecto de la lámina original.
        des = tabulado_32.set_index("estado_de_desaparicion")["todavia_desaparecidos"]
        self.assertEqual(des.get("Jalisco", 0), 0)
        self.assertNotIn(
            config.DIRECTORIO_INDICIOS_SIN_ESTADO,
            tabulado_32["estado_de_desaparicion"].tolist(),
        )


if __name__ == "__main__":
    unittest.main()
