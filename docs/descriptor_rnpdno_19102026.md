# Descriptor comparativo RNPDNO · corte 19/10/2026

Este documento describe y compara los archivos:

1. `input/rnpdno/reporte_personas_completo_19102026.parquet`: extracción de origen del RNPDNO.
2. `output/Resultado_1_Procesamiento_ETL_RNPDNO_autonomo.parquet`: salida del ETL autónomo documentado en `notebooks luis/1_Procesamiento_ETL_RNPDNO_autonomo_explicado.ipynb`.

Las cantidades de filas, columnas, faltantes y categorías siguientes se verificaron sobre las copias locales disponibles el **22/10/2026**. El origen reporta `fecha_consulta` 19/10/2026.

## 1. Resumen comparativo

| Propiedad | Archivo de origen | ETL autónomo |
|---|---:|---:|
| Filas | 412,526 | 412,526 |
| Columnas | 62 | 33 |
| FUB no nulos | 412,526 | 412,526 |
| FUB únicos | 412,526 | 412,526 |
| FUB duplicados | 0 | 0 |
| Fecha de consulta | 19/10/2026 | 19/10/2026 |

Se verificó el cruce completo por FUB: todas las 412,526 filas del origen tienen una fila correspondiente en la salida y viceversa. El ETL no agregó ni eliminó registros en esta corrida; seleccionó y transformó variables.

## 2. Archivo de origen: variables disponibles

El origen trae 62 columnas, todas leídas como texto. La salida autónoma conserva 19 campos relevantes para el maestro y la clasificación; los demás campos de la extracción no se exportan en este Parquet.

### Campos conservados y renombrados

| Campo en la salida | Campo de origen | Contenido |
|---|---|---|
| `fub_rnpdno` | `fub` | Folio Único de Búsqueda; llave de persona. |
| `estatus_rnpdno` | `estatus` | Estatus reportado en la extracción. |
| `nombre_vic_rnpdno` | `nombre_vic` | Nombre de la persona desaparecida o localizada. |
| `primerapellido_vic_rnpdno` | `primerapellido_vic` | Primer apellido. |
| `segundoapellido_vic_rnpdno` | `segundoapellido_vic` | Segundo apellido. |
| `sexo_rnpdno` | `sexo` | Sexo reportado. |
| `fechanacimiento_rnpdno` | `fechanacimiento` | Fecha de nacimiento original, conservada como texto. |
| `idestadonacimiento_vic_rnpdno` | `idestadonacimiento_vic` | Clave de entidad de nacimiento. |
| `idestado_rnpdno` | `idestado` | Clave de entidad asociada al registro. |
| `idmunicipio_rnpdno` | `idmunicipio` | Clave de municipio. |
| `fechahechos_rnpdno` | `FechaHechos` normalizada al alias `fechahechos` | Fecha de hechos recibida, conservada como texto. |
| `fechapercato_rnpdno` | `fechapercato` | Fecha de percance u otro campo de respaldo recibido. |
| `fechalocaliza_rnpdno` | `fechalocaliza` | Fecha de localización recibida. |
| `delitolocalizacion_rnpdno` | `delitolocalizacion` | Texto de delito/localización. |
| `fechacaptura_rnpdno` | `fechacaptura` | Fecha de captura. |
| `dependencia_origen_rnpdno` | `dependencia_origen` | Dependencia reportante. |
| `fecha_consulta_rnpdno` | `fecha_consulta` | Fecha del corte de consulta del RNPDNO. |
| `curp_vic_rnpdno` | `curp_vic` | CURP reportada originalmente. |
| `expedientes_rnpdno` | `Expediente` | Expediente; se estandariza el nombre al plural. |

El archivo de origen contiene, además, estas 43 columnas que no forman parte de la salida de 33 columnas: `idestatusvic`, `clasificacion_v`, `clasificacion_r`, `idnacionalidad`, `nacionalidad`, `Telefono_desaparecido`, `tienedelito`, `iddelitolocalizacion`, `idclasificiaciondelito`, `clasificiaciondelito`, `iddelitoDesaparicion`, `DelitoDesaparicion`, `idcattipousuario`, `idinicio`, `inicio`, `conidentidad`, `curp_reportante`, `rfc_reportante`, `nombre_reportante`, `paterno_reportante`, `materno_reportante`, `sexo_reportante`, `nacionalidad_reportante`, `id_edonac_reportante`, `fecha_nac_reportante`, `relacion`, `parentesco`, `ren_curp`, `ren_nombres`, `ren_apellido1`, `ren_apellido2`, `ren_sexo`, `ren_fechnac`, `ren_nacionalidad`, `ren_cveentidadnac`, `ren_statuscurp`, `ren_fecha`, `tel_movil_reportante`, `tel_fijo_casa_reportante`, `tel_fijo_oficina_reportante`, `correo_electronico_reportante`, `fechacaptura_estatus` y `publicarficha`.

Que un campo se omita de este Parquet no significa que se haya eliminado del origen; simplemente no está incluido en el esquema final del ETL autónomo.

## 3. Diccionario de las 33 columnas de salida

El sufijo `_rnpdno` identifica el valor recibido del origen, después de normalizar la columna/alias y los valores vacíos reconocidos. El sufijo `_derivada_rnpdno` indica una conversión o cálculo realizado por el ETL.

| Variable | Tipo de salida | Faltantes | Descripción / transformación |
|---|---|---:|---|
| `fub_rnpdno` | texto | 0 | Identificador de persona tomado de `fub`. Único en esta copia. |
| `estatus_rnpdno` | texto | 0 | Estatus original de RNPDNO. Se usa junto con la validez de CURP para reconstruir la clasificación final. |
| `nombre_vic_rnpdno` | texto | 15 | Nombre reportado. |
| `primerapellido_vic_rnpdno` | texto | 158 | Primer apellido reportado. |
| `segundoapellido_vic_rnpdno` | texto | 5,218 | Segundo apellido reportado. |
| `sexo_rnpdno` | texto | 0 | Sexo reportado. |
| `fechanacimiento_rnpdno` | texto | 92,336 | Fecha de nacimiento original, antes de convertirla a fecha. |
| `idestadonacimiento_vic_rnpdno` | texto | 217,550 | Clave de entidad de nacimiento original. |
| `idestado_rnpdno` | texto | 0 | Clave de entidad original. |
| `idmunicipio_rnpdno` | texto | 14,760 | Clave municipal original. |
| `fechahechos_rnpdno` | texto | 32,680 | Fecha original de hechos; viene del campo `FechaHechos` del Parquet de origen. |
| `fechapercato_rnpdno` | texto | 39,533 | Fecha original de percance/respaldo. |
| `fechalocaliza_rnpdno` | texto | 218,668 | Fecha original de localización. |
| `delitolocalizacion_rnpdno` | texto | 398,743 | Clasificación o descripción de delito/localización reportada. |
| `fechacaptura_rnpdno` | texto | 0 | Fecha original de captura. |
| `dependencia_origen_rnpdno` | texto | 0 | Dependencia reportante. |
| `fecha_consulta_rnpdno` | texto | 0 | Fecha original de consulta; en esta copia corresponde al 19/10/2026. |
| `curp_vic_rnpdno` | texto | 244,214 | CURP original reportada; no incluye las CURP auxiliares RENAPO. |
| `expedientes_rnpdno` | texto | 174,549 | Expediente original; nombre estandarizado desde `Expediente`. |
| `fechanacimiento_derivada_rnpdno` | fecha/hora | 92,336 | Conversión de `fechanacimiento_rnpdno` a fecha; los valores vacíos o inválidos quedan nulos. Rango observado: 1882-08-13 a 2204-09-01; hay fechas atípicas que requieren validación. |
| `idestado_derivada_rnpdno` | entero nullable | 0 | `idestado` convertido a entero. Tiene 33 valores distintos en esta copia. |
| `idmunicipio_derivada_rnpdno` | numérico nullable | 14,760 | `idmunicipio` convertido a número; aparece como decimal nullable por la representación de nulos. Interpretar junto con la entidad. |
| `fechahechos_derivada_rnpdno` | fecha/hora | 32,680 | Conversión de la fecha de hechos original; rango observado: 1952-12-31 a 2026-10-15. |
| `fechapercato_derivada_rnpdno` | fecha/hora | 39,533 | Conversión de la fecha de percance/respaldo; rango observado: 1952-12-31 a 2026-10-15. |
| `fechalocaliza_derivada_rnpdno` | fecha/hora | 218,668 | Conversión de la fecha de localización. Rango observado: 1900-01-01 a 2205-03-01; existen fechas atípicas que no deben usarse sin validación. |
| `fechacaptura_derivada_rnpdno` | fecha/hora | 0 | Conversión de la fecha de captura; rango observado: 2006-11-29 a 2026-10-16. |
| `fecha_consulta_derivada_rnpdno` | fecha/hora | 0 | Conversión de la fecha de consulta; valor único observado: 2026-10-19. |
| `curp_vic_derivada_rnpdno` | texto | 241,285 | CURP normalizada y, cuando corresponde, imputada con los archivos auxiliares RENAPO configurados en el notebook. No reemplaza el campo original. |
| `curp_vic_valida_derivada_rnpdno` | lógico | 0 | Indicador de estructura válida según las reglas locales del notebook y las claves de entidad admitidas. No equivale a una validación oficial ante RENAPO. TRUE: 169,955; FALSE: 242,571. |
| `nombre_completo_derivada_rnpdno` | texto | 0 | Concatenación de nombre, primer apellido y segundo apellido; convierte a mayúsculas, quita acentos seleccionados y normaliza espacios. Un nombre vacío puede dar una cadena vacía, no un nulo. |
| `fecha_hechos_modificada_derivada_rnpdno` | fecha/hora | 0 | Fecha de hechos de trabajo: primera fecha disponible entre `fechahechos_derivada_rnpdno`, `fechapercato_derivada_rnpdno` y `fechacaptura_derivada_rnpdno`, en ese orden. Es la fecha usada después para construir períodos. |
| `estado_derivada_rnpdno` | texto | 0 | Nombre de entidad obtenido de `idestado_derivada_rnpdno` mediante el catálogo de 33 claves. |
| `clasificacion_des_derivada_rnpdno` | texto | 0 | Clasificación final: `Localizados` para los dos estatus de localización; entre los demás registros, `Desaparecidos` si pasó el criterio de CURP válida y `Pendientes` si no pasó. Valores observados: Localizados 282,056; Desaparecidos 84,013; Pendientes 46,457. |

## 4. ¿Qué modificaciones se realizaron en el ETL autónomo?

1. **Estandarización de nombres de columna.** Los encabezados se normalizan (minúsculas, sin acentos ni signos y con guion bajo) y se aplican alias. Por ejemplo, `FechaHechos` pasa a alimentar `fechahechos`; `Expediente` se exporta como `expedientes_rnpdno`.
2. **Selección de esquema.** De las 62 columnas del origen, conserva 19 campos de datos/persona y de estatus necesarios para el maestro. No exporta las otras 43 columnas enumeradas arriba, muchas relacionadas con reportantes, RENAPO, teléfonos y campos auxiliares.
3. **Normalización de faltantes.** En la lectura se convierten marcadores vacíos comunes —por ejemplo, cadena vacía, `N/A`, `NaN`, `None` y variantes configuradas— a nulos. Por eso las columnas originales con sufijo pueden diferir en nulos respecto del origen aunque el valor informado no se haya recalculado.
4. **Copia de campos de origen.** Los campos originales seleccionados se guardan con sufijo `_rnpdno`; se retienen como texto para distinguirlos de los campos derivados. Se conserva la CURP original por separado de la CURP de trabajo.
5. **Conversión de tipos.** Las fechas se convierten a fecha/hora; las claves de estado/municipio se convierten a tipos numéricos en sus columnas derivadas. Los valores que no se convierten quedan nulos.
6. **CURP de trabajo.** Se quitan espacios, se convierte a mayúsculas y se validan longitud, patrón y clave estatal conforme a las reglas del notebook. Puede incorporarse una CURP válida procedente de los archivos auxiliares RENAPO si la original no es válida; se crea además la bandera booleana. La CURP auxiliar no se expone como columna separada en el Parquet final.
7. **Fecha de hechos de trabajo.** Se crea una fecha con respaldo jerárquico: fecha de hechos, luego percance y, si ambas faltan, fecha de captura. En el corte inspeccionado esta columna no tiene nulos.
8. **Nombre completo y entidad.** Se agrega un nombre completo normalizado y se traduce la clave estatal a un nombre mediante el catálogo local.
9. **Clasificación de salida.** Los 282,056 registros con estatus `LOCALIZADA CON VIDA` o `LOCALIZADA SIN VIDA` se clasifican como `Localizados`. Los 130,470 no localizados se dividen, según CURP válida, en 84,013 `Desaparecidos` y 46,457 `Pendientes`.
10. **Deduplicación/consolidación.** El notebook comprueba consistencia de identidad dentro de FUB y conserva la primera fila por FUB en cada universo. En esta copia no hubo que quitar filas: el origen ya tiene un registro por cada FUB.
11. **Corte y exportación.** `fecha_consulta` se conserva como texto de origen y también se convierte a fecha. La copia derivada corresponde al corte del 19/10/2026. El resultado final tiene 33 columnas y 412,526 filas.

## 5. Límites de interpretación

- El Parquet derivado no es una copia exhaustiva del archivo original: excluye 43 columnas del origen.
- `_rnpdno` identifica procedencia, pero los campos pueden contener normalización de vacíos y estandarización de alias. Para auditoría byte a byte, conservar y consultar el archivo de entrada original.
- La validez de CURP del ETL es una regla estructural local, no certificación oficial ni comprobación de identidad.
- La imputación de CURP afecta los campos `curp_vic_derivada_rnpdno`, `curp_vic_valida_derivada_rnpdno` y, por consecuencia, la división entre `Desaparecidos` y `Pendientes`; no altera el FUB ni el total de filas.
- Las fechas extremas observadas en nacimiento y localización deben depurarse antes de calcular edades o tendencias.
- Estos conteos describen los dos archivos inspeccionados. Una nueva extracción del RNPDNO o una nueva ejecución del ETL puede cambiar conteos, nulos y categorías.

## 6. Esquema reproducible en R

```r
library(arrow)
library(dplyr)

origen <- read_parquet("input/rnpdno/reporte_personas_completo_19102026.parquet")
etl <- read_parquet("output/Resultado_1_Procesamiento_ETL_RNPDNO_autonomo.parquet")

# Tamaño y llave
tibble(
  archivo = c("origen", "ETL autónomo"),
  filas = c(nrow(origen), nrow(etl)),
  columnas = c(ncol(origen), ncol(etl))
)

# Conteos principales de la clasificación ETL
table(etl$clasificacion_des_derivada_rnpdno, useNA = "ifany")

# Comprobar que el FUB sea único y que ambos archivos tengan el mismo universo
stopifnot(
  n_distinct(origen$fub) == nrow(origen),
  n_distinct(etl$fub_rnpdno) == nrow(etl),
  setequal(origen$fub, etl$fub_rnpdno)
)
```
