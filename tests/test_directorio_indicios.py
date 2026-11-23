import unittest
from unittest.mock import patch

import pandas as pd

import config
from src.directorio_indicios import indicios_formalizados


class IndiciosFormalizadosTests(unittest.TestCase):
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
