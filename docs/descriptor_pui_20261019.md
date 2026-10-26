# Descriptor comparativo PUI · corte 19/10/2026

Este documento describe y compara los archivos:

1. **CSV de coincidencias:** `input/pui/reporte_coincidencias_validas_2026-10-19.csv`.
2. **Salida integrada:** `output/Resultado_3_Procesamiento_ETL_PUI.parquet`.

El CSV contiene coincidencias administrativas de varias instituciones: cada fila representa un evento/coincidencia. El Parquet no es una copia reducida fila a fila: agrupa información por FUB, la cruza con confrontas manuales y el RNPDNO, añade registros elegibles de defunción y conserva las personas desaparecidas o pendientes que cumplen las reglas del ETL.

Los conteos, tipos y faltantes se calcularon en las copias locales el **22/10/2026**. La fecha declarada por el nombre del CSV es **19/10/2026**.

## 1. Resumen de los archivos

| Propiedad | CSV de coincidencias | Parquet integrado |
|---|---:|---:|
| Filas | 178,132 eventos | 38,374 registros/personas | 
| Columnas | 16 | 10 |
| FUB distintos | 53,973 valores de origen, con identificadores de coincidencia al final | 38,374 FUB normalizados y únicos |
| Granularidad | Evento administrativo detectado | Una fila por FUB en esta salida, más los registros de defunción incorporados que cumplen filtro |
| Estado de la persona | No es el resultado final del RNPDNO | `Desaparecidos` 32,143; `Pendientes` 6,231 |

La ejecución registrada en el notebook autónomo muestra estos pasos de volumen: **178,132** filas leídas, **130,237** coincidencias después de limpiar FUB/CURP y aplicar exclusiones, agregación de esas coincidencias a **18,103 FUB**, y finalmente **38,374 filas × 10 columnas** en el Parquet. También se registraron 2,531 filas de defunción que cumplen la condición de elegibilidad. El total final incorpora varias ramas y no debe interpretarse como una simple reducción del CSV.

> En esta copia del Parquet el campo FUB no tiene duplicados: hay 38,374 filas y 38,374 FUB únicos. El ETL conserva dos clases de registros conceptualmente diferentes (actividad administrativa y defunciones) dentro del mismo contrato; las defunciones se etiquetan en la institución como `defuncion de ...`.

## 2. Diccionario del CSV de entrada

Las faltas son celdas vacías reconocidas durante la lectura. Los valores se leen como texto para preservar ceros iniciales e identificadores; `is_valid` se normaliza posteriormente a booleano.

| Variable | Tipo leído | Vacíos | Distintos | Descripción |
|---|---|---:|---:|---|
| `institucion_id` | texto | 0 | 14 | Código de la institución que generó la coincidencia. |
| `institucion` | texto | 0 | 14 | Nombre de la institución de origen. |
| `fase_busqueda` | texto | 0 | 2 | Fase de búsqueda; el notebook acepta fases 2 y 3. |
| `fub` | texto | 0 | 53,973 | FUB asociado a la coincidencia. En este insumo lleva un identificador UUID al final que se separa durante la limpieza. |
| `curp` | texto | 0 | 50,104 | CURP asociada a la coincidencia. Los valores en el archivo se leen como cadena; algunas cadenas vacías pueden estar representadas literalmente y no como NA. |
| `tipo_evento` | texto | 0 | 52,315 | Trámite o evento administrativo observado. |
| `fecha_evento` | texto | 0 | 3,500 | Fecha asociada al evento; se convierte a fecha al exportar el resultado integrado. |
| `fecha_desaparicion` | texto | 123 | 6,941 | Fecha de desaparición informada en la coincidencia. |
| `entidad_federativa` | texto | 148,937 | 33 | Entidad reportada en el registro de coincidencia. |
| `reporte_created_at` | texto | 0 | 26,486 | Fecha/hora de creación del reporte/coincidencia. |
| `coincidencia_id` | texto | 0 | 178,132 | Identificador de cada evento. Es único en esta copia. |
| `calle` | texto | 153,595 | 5,618 | Calle asociada al domicilio del evento; dato sensible de ubicación. |
| `codigo_postal` | texto | 170,169 | 1,691 | Código postal asociado; dato de ubicación. |
| `colonia` | texto | 150,161 | 1,499 | Colonia asociada; dato de ubicación. |
| `direccion` | texto | 148,937 | 8,984 | Dirección asociada; dato sensible de ubicación. |
| `is_valid` | texto → booleano | 0 | 2 | Bandera de vigencia/validez de la coincidencia. En el CSV: `True` 158,211 y `False` 19,921. |

Los campos de ubicación y datos identificadores no se copian al Parquet final. Los recuentos de eventos por institución observados incluyen: SEBIEN 91,484; RENAPO 55,387; SEP 10,763; PEMEX 9,941; IMSS 3,530; SAT 2,784; CONSAR 2,427, además de otras instituciones.

## 3. Diccionario de la salida Parquet

Los nombres de exportación se asignan al final del notebook. Los sufijos expresan procedencia o derivación; varias columnas son combinaciones de PUI, confrontas manuales y RNPDNO.

| Variable exportada | Tipo | Faltantes | Distintos | Descripción / procedencia |
|---|---|---:|---:|---|
| `fub_derivada_pui` | texto | 0 | 38,374 | FUB limpio y enlazado a la persona; único en la salida observada. |
| `curp_victima_derivada_rnpdno_pui` | texto | 7,113 | 31,230 | CURP de trabajo asociada a la persona; puede venir de la rama PUI o del maestro RNPDNO, de acuerdo con el cruce. |
| `indicadora_indicio_de_vida_derivada_pui` | texto | 0 | 2 | Indicador del origen de actividad: `con registro administrativo` (33,809) o `con registro administrativo en PUI` (4,565). La primera etiqueta puede incluir defunciones; no significa que la persona esté viva. |
| `institucion_indicadora_de_vida_derivada_pui` | texto | 0 | 2,580 | Instituciones que aportan el registro, acumuladas entre PUI, confronta manual y defunciones. Para defunciones aparece como `defuncion de INE` (1,925), `defuncion de RENAPO` (574) o `defuncion de SSA` (32). |
| `numero_instituciones_derivada_pui` | entero nullable | 0 | 16 | Número de instituciones. Se combina entre ramas PUI/manual; las filas de defunción se asignan a 0. Rango observado: 0–15. |
| `indicadora_coincidencia_manual_derivada_pui` | texto | 25,620 | 2 | Señala `coincidencia en PUI y registro manual` (8,189) o `solo coincidencia en PUI` (4,565). Nulo en la rama manual sin PUI y en defunciones. |
| `tipo_tramites_derivada_pui` | texto | 25,620 | 9,237 | Eventos PUI agrupados y concatenados, con normalización/abreviaturas institucionales. Nulo en registros que no provienen de la rama de coincidencias. |
| `tramites_repetidos_derivada_pui` | texto | 25,620 | 715 | Conteos de repetición de cada evento, paralelos al orden de `tipo_tramites`; texto porque puede contener una secuencia de conteos. |
| `fecha_evento_derivada_pui` | fecha/hora | 25,620 | 1,545 | Primera fecha de evento del grupo PUI; nula en ramas sin evento PUI. Rango observado: 2014-02-25 a 2026-10-09. |
| `clasificacion_des_derivada_rnpdno` | texto | 0 | 2 | Clasificación vigente del maestro RNPDNO: `Desaparecidos` (32,143) o `Pendientes` (6,231). Se filtran fuera los localizados. |

Los faltantes de varias columnas de trámite tienen el mismo valor, 25,620, porque esas filas proceden de confrontas manuales sin evento PUI o de la rama de defunciones, en las que no se informan tipo/fecha de trámite ni indicador de match manual.

## 4. Transformaciones del CSV al Parquet

1. **Lectura local del CSV.** Se exige el esquema de 16 columnas. Se intenta UTF-8 y se usa Latin-1 si la codificación UTF-8 falla; se leen los datos como texto para conservar identificadores.
2. **Validación.** Se valida que la fase de búsqueda pertenezca a las fases 2 o 3 y que `is_valid` pueda interpretarse como booleano. En esta copia hay 158,211 `True` y 19,921 `False`; el flujo mostrado en el notebook no filtra esas filas únicamente por `is_valid`.
3. **Normalización del FUB.** El campo `fub` de cada coincidencia lleva el UUID de la coincidencia añadido al folio. Se conserva temporalmente como `fub_uuid` y se elimina el sufijo UUID para recuperar el FUB de persona.
4. **Exclusiones del origen.** Se eliminan CURP contenidas en `input/pui/curps_excluidas.txt` y, para RENAPO (`institucion_id == "0044"`), se excluyen actas de nacimiento y eventos que contienen `|1`. La lista local tiene 1 CURP, pero no coincide con ninguna fila de este CSV: no elimina registros. En esta copia se retiran 47,047 eventos RENAPO de acta de nacimiento y 848 eventos RENAPO que contienen `|1`; quedan 130,237 filas de coincidencia.
5. **Agregación persona/eventos.** Las 130,237 filas se agrupan por FUB en 18,103 personas. Se resume el número de apariciones, instituciones únicas, fases, eventos, fechas y otros datos. Los eventos se concatenan en el orden del grupo; las repeticiones de cada evento se cuentan de forma paralela.
6. **Cruce con confrontas manuales.** Se enlaza por FUB. Para coincidencias que no empatan por FUB, se usa CURP + fecha de desaparición; se etiquetan las ramas como `coincidencia en PUI y registro manual` o `solo coincidencia en PUI` según procedencia.
7. **Cruce con el RNPDNO.** Se usa el Parquet de RNPDNO para añadir la CURP de trabajo, clasificación y fecha modificada de hechos. Las coincidencias que existen solo en PUI se retienen únicamente si su FUB está presente en RNPDNO; en la corrida documentada, 6,131 estaban presentes y 1,572 se descartaron por no tener FUB en el RNPDNO.
8. **Filtro de universo vigente.** Se conservan los registros con desaparición activa o estado manual nulo, y luego sólo las clasificaciones RNPDNO `Desaparecidos` o `Pendientes`.
9. **Anexo de defunciones.** Se agregan actas del Excel `tabla_defunciones_por_institucion_05052026.xlsx` cuando corresponden a desaparecidos/pendientes y la fecha modificada de hechos es desde 2006-01-01. La corrida añadió 2,531 registros. La etiqueta administrativa no es prueba de vida; por eso este conjunto puede contener defunciones.
10. **Esquema y tipos finales.** Se quitan columnas auxiliares, se aplica el contrato fijo de 10 columnas, se convierte `fecha_evento` a fecha y el número de instituciones a entero nullable, y se renombra según el diccionario de la sección anterior.

## 5. Qué significa el conteo final

El Parquet representa **38,374 filas** en esta corrida, todas con FUB no nulo y sin FUB duplicado. Incluye:

- Coincidencias PUI agrupadas y relacionadas con confrontas manuales.
- Registros de confronta manual sin coincidencia directa de PUI, bajo las reglas de cruce establecidas.
- Registros de defunción institucional que cumplen las reglas de RNPDNO y fecha.

No es el número de eventos fuente (178,132), ni el número de FUB agrupados solo de la PUI (18,103), ni un conteo de personas localizadas. La etiqueta `con registro administrativo` identifica la existencia de actividad administrativa; no garantiza que la persona esté viva. De hecho, 2,531 filas del Parquet se identifican como registros de defunción.

## 6. Privacidad y límites

- El CSV contiene CURP, FUB con sufijo UUID, eventos y datos de ubicación/dirección. No publicar filas de muestra ni datos identificadores.
- El Parquet omite dirección, calle, colonia, código postal, UUID de coincidencia y varias columnas fuente sensibles, pero conserva FUB, CURP y cadenas de instituciones/trámites; sigue siendo información sensible.
- Los conteos corresponden a la versión exacta de los insumos locales y al notebook autónomo inspeccionado. Otros archivos de salida o cortes pueden cambiar los resultados.
- Este descriptor resume la lógica del notebook; no certifica que todos los eventos administrativos sean verdaderos indicios de vida.

## 7. Verificación en Python

```python
from pathlib import Path
import pandas as pd

raiz = Path.cwd()
csv = pd.read_csv(
    raiz / "input/pui/reporte_coincidencias_validas_2026-10-19.csv",
    dtype=str,
    low_memory=False,
)
pui = pd.read_parquet(
    raiz / "output/Resultado_3_Procesamiento_ETL_PUI.parquet"
)

print("CSV:", csv.shape)
print("Parquet:", pui.shape)
print("FUB únicos en salida:", pui["fub_derivada_pui"].nunique())
print(pui["clasificacion_des_derivada_rnpdno"].value_counts())
```
