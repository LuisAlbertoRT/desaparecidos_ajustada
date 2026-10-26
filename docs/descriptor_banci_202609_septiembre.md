# Descriptor comparativo BANCI · septiembre de 2026

Este documento describe y compara:

1. **Origen:** `input/banci/SUBIR_R_202609_septiembre.xlsx`, hoja `Victimas` (en la solicitud se mencionó “UBIR_R”; el nombre real en la carpeta es `SUBIR_R_202609_septiembre.xlsx`).
2. **Salida ETL:** `output/Resultado_2_Procesamiento_ETL_BANCI_autonomo.parquet`.

El esquema, faltantes, tipos y conteos se verificaron en los archivos locales el 22/10/2026. La comparación confirma que la salida conserva el orden de filas y las 39,127 observaciones del Excel; `LLAVE` coincide fila por fila con `llave_banci`.

## 1. Resumen

| Propiedad | Excel BANCI, `Victimas` | Parquet ETL autónomo |
|---|---:|---:|
| Filas | 39,127 | 39,127 |
| Columnas | 74 | 32 |
| Hoja | `Victimas` | — |
| `LLAVE` / `llave_banci` únicos | 35,776 | 35,776 |
| `Entidad` distintas | 33 | 33 en campo de origen; 32 en entidad derivada |
| Registro perdido/agregado en esta corrida | — | 0; salida alineada fila a fila por `LLAVE` |

En `localizado_o_no_localizado` el origen tiene `Localizada` 25,730, `No localizada` 13,090 y `No Localizada` 307. El ETL estandariza los valores a mayúsculas: `LOCALIZADA` 25,730 y `NO LOCALIZADA` 13,397.

## 2. Diccionario del Excel de origen

Las faltas se refieren a celdas vacías reconocidas al leer el Excel; no implican que la variable sea inválida. La columna `tipo` indica el tipo inferido por pandas en esta lectura local (no necesariamente el formato físico de Excel).

| Variable del Excel | Tipo leído | Vacíos | Distintos | Descripción funcional inferida por nombre |
|---|---|---:|---:|---|
| `Entidad` | texto | 0 | 33 | Entidad que reporta el registro. |
| `LLAVE` | texto | 0 | 35,776 | Llave compuesta de BANCI, principal referencia interna. |
| `ID_CI` | objeto | 0 | 35,222 | Identificador de carpeta/investigación. |
| `NTRA_CI` | objeto | 0 | 34,005 | Número de carpeta/investigación. |
| `FHA_DE_INI` | fecha/hora | 0 | 735 | Fecha de inicio del registro/carpeta. Rango: 2024-02-01 a 2026-09-30. |
| `HRA_DE_INI` | objeto | 3,115 | 9,254 | Hora de inicio. |
| `RMEN_DE_HCHOS` | texto | 9 | 19,370 | Resumen de hechos. |
| `DTO` | objeto | 0 | 94 | Campo de delito/registro, según nomenclatura de origen. |
| `MODA_DTO` | objeto | 0 | 70 | Modalidad del delito. |
| `FORMA_ACC` | objeto | 0 | 23 | Forma de acción/captura. |
| `FHA_DE_HCHOS` | fecha/hora | 658 | 1,806 | Fecha de hechos. Rango: 1905-07-17 a 2026-09-30. |
| `HRA_DE_HCHOS` | objeto | 7,914 | 3,366 | Hora de hechos. |
| `EMTO_COM_DTO` | objeto | 9 | 40 | Campo de comisión/entidad relacionado con el delito; verificar definición institucional. |
| `GRDO_CONS` | objeto | 1 | 10 | Grado de consumación. |
| `CLASF_DE_DTO` | objeto | 0 | 11 | Clasificación del delito. |
| `NOM_ENT_HCHOS` | objeto | 0 | 34 | Nombre de entidad de los hechos. |
| `ID_ENT_HCHOS` | entero | 0 | 33 | Clave de entidad de los hechos. |
| `NOM_MUN_HCHOS` | objeto | 202 | 1,414 | Nombre del municipio de los hechos. |
| `ID_MUN_HCHOS` | objeto | 0 | 460 | Clave de municipio de los hechos, conservada como identificador. |
| `NOM_LOC_HCHOS` | objeto | 138 | 3,758 | Nombre de localidad de los hechos. |
| `ID_LOC_HCHOS` | objeto | 694 | 724 | Clave de localidad. |
| `NOM_COL_HCHOS` | objeto | 73 | 12,915 | Nombre de colonia. |
| `ID_COL_HCHOS` | objeto | 700 | 6,502 | Clave de colonia. |
| `CP` | objeto | 782 | 5,865 | Código postal. |
| `COORD_X` | objeto | 162 | 16,384 | Coordenada X. Dato potencialmente sensible de ubicación. |
| `COORD_Y` | objeto | 162 | 16,457 | Coordenada Y. Dato potencialmente sensible de ubicación. |
| `DOM_HCHOS` | objeto | 74 | 23,821 | Domicilio de los hechos; información sensible. |
| `DELITO_HOM` | texto | 0 | 2 | Tipo homologado: desaparición forzada o cometida por particulares. |
| `ID_DELITO` | objeto | 4,968 | 7,873 | Identificador de delito. |
| `ID_VICF` | objeto | 10,560 | 25,272 | Identificador de víctima/fuente, según el sistema de origen. |
| `ID_TV` | objeto | 11,753 | 9 | Código de tipo de víctima. |
| `ID_TPM` | objeto | 27,763 | 9 | Código de tipo/modalidad, verificar catálogo institucional. |
| `SEXO` | texto | 0 | 3 | Sexo reportado. |
| `GENERO` | objeto | 7,449 | 17 | Género reportado. |
| `POB` | objeto | 9,241 | 14 | Campo poblacional; requiere catálogo para interpretación exacta. |
| `DISC` | objeto | 9,758 | 21 | Campo de discapacidad u otra clasificación; requiere diccionario BANCI. |
| `FHA_NAC` | fecha/hora | 7,191 | 15,294 | Fecha de nacimiento. Hay 5 fechas posteriores al 30/09/2026, posibles valores anómalos. |
| `EDAD` | decimal | 7,188 | 101 | Edad reportada. |
| `NACIONAL` | texto | 0 | 36 | Nacionalidad reportada. |
| `NO_BANCI` | objeto | 36,708 | 5 | Campo de estatus/observación BANCI, requiere catálogo. |
| `folio_fotovolante` | objeto | 21,203 | 16,046 | Folio de fotovolante. |
| `folio_RNPDNO` | texto | 22,183 | 16,612 | FUB/folio RNPDNO para cruce. |
| `Primer apellido` | texto | 1,121 | 4,166 | Primer apellido reportado. Dato personal. |
| `Segundo apellido` | texto | 1,420 | 4,009 | Segundo apellido reportado. Dato personal. |
| `Nombres` | texto | 1,119 | 17,506 | Nombres reportados. Dato personal. |
| `entidad_nacimiento` | texto | 7,755 | 34 | Entidad de nacimiento. |
| `estado_migratorio2` | objeto | 18,115 | 65 | Estado migratorio reportado. |
| `curp` | texto | 13,703 | 24,827 | CURP; dato personal sensible. |
| `rfc` | objeto | 26,220 | 7,772 | RFC; dato personal sensible. |
| `fecha_ultimo_contacto` | objeto | 9,132 | 2,609 | Fecha de último contacto. |
| `hora_ultimo_contacto` | objeto | 12,042 | 1,854 | Hora de último contacto. |
| `Entidad_visto` | texto | 8,102 | 118 | Entidad donde se vio por última vez. |
| `Municipio_visto` | texto | 8,133 | 1,832 | Municipio donde se vio por última vez. |
| `lugar_ultimo_contacto` | objeto | 9,753 | 21,268 | Lugar de último contacto; puede revelar ubicación. |
| `senas_tatujes_datos_identificacion` | objeto | 12,251 | 20,109 | Señas/tatuajes/datos de identificación; información sensible. |
| `localizado_o_no_localizado` | texto | 0 | 3 | Estatus de localización: incluye variantes de mayúsculas/minúsculas. |
| `con_o_sin_vida` | texto | 11,552 | 8 | Condición con/sin vida u otras etiquetas del origen. |
| `fecha_localizacion` | fecha/hora | 14,027 | 781 | Fecha de localización. |
| `voluntaria` | objeto | 13,140 | 26 | Campo de localización voluntaria; categorías requieren revisión. |
| `fue_delito` | objeto | 11,726 | 10 | Indicador/categoría de delito. |
| `delito` | texto | 18,100 | 296 | Delito reportado. |
| `observaciones` | objeto | 23,821 | 5,547 | Observaciones operativas; puede incluir datos personales. |
| `delito_localiza` | decimal | 39,127 | 0 | Columna completamente vacía en esta entrega. |
| `localizado_o_no_localizado_ORI` | objeto | 609 | 28 | Valor original antes de corrección/actualización. |
| `con_o_sin_vida_ORI` | objeto | 11,409 | 25 | Condición original con/sin vida. |
| `fecha_localizacion_ORI` | objeto | 12,119 | 1,277 | Fecha original de localización, sin tipo de fecha uniforme. |
| `voluntaria_ORI` | objeto | 12,950 | 27 | Valor original de localización voluntaria. |
| `fue_delito_ORI` | objeto | 11,615 | 22 | Valor original de fue delito. |
| `delito_ORI` | texto | 18,100 | 296 | Delito original. |
| `observaciones_ORI` | texto | 39,054 | 68 | Observaciones originales; 39,054 vacíos. |
| `FUB_OK` | decimal | 39,127 | 0 | Columna completamente vacía en esta entrega. |
| `CURP_OK` | decimal | 39,127 | 0 | Columna completamente vacía en esta entrega. |
| `NOMBRE_OK` | decimal | 39,127 | 0 | Columna completamente vacía en esta entrega. |
| `delito_localiza_vf` | decimal | 39,127 | 0 | Columna completamente vacía en esta entrega. |

> Las descripciones señaladas como inferidas por nombre no reemplazan un catálogo oficial de campos BANCI. El Excel no incluye en esta carpeta un diccionario de datos para aclarar todos los códigos abreviados.

## 3. Diccionario de las 32 columnas del Parquet

Las columnas con sufijo `_banci` conservan los campos fuente seleccionados (estandarizados a alias BANCI); las columnas `_derivada_banci` son campos normalizados o calculados por el notebook autónomo.

| Variable | Tipo | Faltantes | Descripción y cálculo |
|---|---|---:|---|
| `entidad_banci` | texto | 0 | Copia de `Entidad`. |
| `llave_banci` | texto | 0 | Llave de registro BANCI. 35,776 valores distintos en 39,127 filas. |
| `id_ci_banci` | texto | 0 | ID_CI original. |
| `ntra_ci_banci` | texto | 0 | NTRA_CI original. |
| `fha_de_ini_banci` | fecha/hora | 0 | Fecha de inicio original; rango 2024-02-01 a 2026-09-30. |
| `fha_de_hchos_banci` | fecha/hora | 658 | Fecha de hechos original; rango 1905-07-17 a 2026-09-30. |
| `nom_mun_hchos_banci` | texto | 202 | Municipio de hechos original. |
| `id_mun_hchos_banci` | texto | 0 | Clave municipal de hechos, tratada como identificador textual. |
| `delito_hom_banci` | texto | 0 | Clasificación homologada del delito; 39,068 cometida por particulares y 59 desaparición forzada. |
| `sexo_banci` | texto | 0 | Sexo original; HOMBRE 23,572, MUJER 14,911, NO ESPECIFICADO 644. |
| `fha_nac_banci` | fecha/hora | 7,191 | Fecha de nacimiento original; rango observado 1905-06-21 a 2027-09-30. Revisar fechas futuras. |
| `folio_rnpdno_banci` | texto | 22,183 | Folio RNPDNO original. |
| `primer_apellido_banci` | texto | 1,121 | Primer apellido original. |
| `segundo_apellido_banci` | texto | 1,420 | Segundo apellido original. |
| `nombres_banci` | texto | 1,119 | Nombres originales. |
| `curp_banci` | texto | 13,703 | CURP original, sin modificar. |
| `localizado_o_no_localizado_banci` | texto | 0 | Estatus original con grafía fuente. Valores: tres variantes/categorías. |
| `fue_delito_banci` | texto | 11,726 | Campo original fue_delito. |
| `fub_ok_banci` | decimal | 39,127 | Copia del campo `FUB_OK`; está vacío en toda esta entrega y no contiene FUB aprovechable. |
| `entidad_derivada_banci` | texto | 0 | Entidad normalizada a mayúsculas, sin diacríticos ni espacios exteriores; 32 valores distintos (de 33 grafías fuente). |
| `id_ci_derivada_banci` | texto | 0 | ID_CI estandarizado a texto. |
| `ntra_ci_derivada_banci` | texto | 0 | Número de carpeta estandarizado a texto. |
| `fha_de_hchos_derivada_banci` | fecha/hora | 658 | Fecha de hechos convertida; en esta corrida no difiere de la fecha origen parseable. |
| `nom_mun_hchos_derivada_banci` | texto | 202 | Municipio normalizado; sin acentos, en mayúsculas. |
| `localizado_o_no_localizado_derivada_banci` | texto | 0 | Estatus normalizado a mayúsculas: LOCALIZADA 25,730; NO LOCALIZADA 13,397. |
| `fha_nac_derivada_banci` | fecha/hora | 7,191 | Fecha de nacimiento convertida. En esta corrida no difiere de la fecha de origen parseable. |
| `nombres_derivada_banci` | texto | 1,119 | Nombres reparados cuando se detectó apellido faltante y fue posible redistribuir partes del nombre. |
| `primer_apellido_derivada_banci` | texto | 1,264 | Primer apellido reparado en algunas filas. |
| `segundo_apellido_derivada_banci` | texto | 1,412 | Segundo apellido reparado en algunas filas. |
| `nombre_completo_derivada_banci` | texto | 0 | Concatenación de nombres y apellidos disponibles; 37,000 cadenas distintas. |
| `curp_valida_derivada_banci` | lógico | 0 | TRUE si cumple reglas estructurales locales de longitud, patrón y entidad; TRUE 25,233, FALSE 13,894. No es verificación oficial RENAPO. |
| `id_carpeta_derivada_banci` | texto | 0 | Llave compuesta entidad/número de carpeta, usando ID_CI como respaldo cuando NTRA_CI está vacío o en ceros. 39,127 no nulos y 34,654 valores distintos. |

## 4. Modificaciones que realiza el ETL autónomo

1. **Selecciona un esquema de trabajo.** De las 74 columnas del Excel, conserva 19 campos fuente, y agrega 13 campos derivados para producir las 32 columnas finales. Omite 55 campos de origen, entre ellos domicilio/coordenadas, descripción y horas de hechos, variables auxiliares, datos de localización, observaciones y columnas de control vacías.
2. **Estandariza nombres y alias.** Por ejemplo, `Entidad` pasa al campo de trabajo `entidad`; `Primer apellido`, `Segundo apellido` y `Nombres` se asignan a sus nombres normalizados. En salida, las variables fuente quedan con sufijo `_banci`.
3. **Conserva los valores de fuente seleccionados.** Se crean copias con sufijo `_banci`; en la verificación de esta entrega, los 18 campos mapeados conservados coinciden fila por fila con el Excel (al comparar nulos y cadenas recortadas).
4. **Repara nombres, sin cambiar la copia fuente.** Cuando falta uno de los apellidos y el campo nombres contiene varias palabras, intenta reubicar las últimas partes en apellidos. En esta ejecución cambió 156 valores de nombres, 302 de primer apellido y 8 de segundo apellido; estas cifras se refieren a celdas comparadas, no a personas necesariamente distintas. Los campos originales `_banci` se preservan.
5. **Normaliza texto.** La entidad derivada y municipio derivado se pasan a mayúsculas, se eliminan diacríticos y se normalizan espacios. El estado derivado tuvo 32 categorías distintas y el municipio derivado reduce las variantes ortográficas a 1,409 valores no nulos distintos.
6. **Normaliza estatus.** `localizado_o_no_localizado_derivada_banci` se convierte a mayúsculas; las dos formas fuente `No localizada` y `No Localizada` quedan en `NO LOCALIZADA`.
7. **Convierte fechas.** Inicio, hechos y nacimiento se exportan como fecha/hora; las cadenas o valores no interpretables pasarían a nulos. La fecha de inicio no tiene vacíos; fecha de hechos tiene 658 y nacimiento 7,191. La rutina contempla corrección restando años a fechas posteriores a la fecha de ejecución; en este corte no se observó corrección en fechas de hechos o nacimiento frente a sus valores parseables de origen, aunque hay 5 fechas de nacimiento futuras respecto al cierre del corte que requieren cautela.
8. **Valida CURP estructuralmente.** `curp_valida_derivada_banci` evalúa longitud, patrón y clave estatal según catálogo local. El resultado no certifica que la CURP esté oficialmente validada.
9. **Construye nombre completo.** Une nombres y apellidos derivados para disponer de una cadena de comparación; queda no nula en todas las 39,127 filas, aunque eso no implica que todos los nombres sean completos o válidos.
10. **Construye identificador de carpeta.** Crea `id_carpeta_derivada_banci` como entidad y número de carpeta; usa `ID_CI` si `NTRA_CI` está vacío o contiene ceros. En la ejecución, 900 registros usaron ID_CI por respaldo.
11. **Valida por separado campos de identidad para matching.** El notebook calcula internamente nombre válido y bandera de omisión de matching; esas banderas de diagnóstico no están entre las 32 columnas exportadas. El `fub_ok_banci` sí aparece en el esquema, pero la fuente `FUB_OK` está completamente vacía.
12. **No deduplica ni filtra por entidad en esta corrida.** El resultado tiene las 39,127 filas en el mismo orden del Excel y conserva las 33 categorías de entidad original.

## 5. Campos fuente no exportados

El Parquet conserva **19 campos de origen** (18 campos mapeados más `FUB_OK`) y agrega 13 variables derivadas. Por tanto, **55 de las 74 columnas fuente** no se exportan:

`HRA_DE_INI`, `RMEN_DE_HCHOS`, `DTO`, `MODA_DTO`, `FORMA_ACC`, `HRA_DE_HCHOS`, `EMTO_COM_DTO`, `GRDO_CONS`, `CLASF_DE_DTO`, `NOM_ENT_HCHOS`, `ID_ENT_HCHOS`, `NOM_LOC_HCHOS`, `ID_LOC_HCHOS`, `NOM_COL_HCHOS`, `ID_COL_HCHOS`, `CP`, `COORD_X`, `COORD_Y`, `DOM_HCHOS`, `ID_DELITO`, `ID_VICF`, `ID_TV`, `ID_TPM`, `GENERO`, `POB`, `DISC`, `EDAD`, `NACIONAL`, `NO_BANCI`, `folio_fotovolante`, `entidad_nacimiento`, `estado_migratorio2`, `rfc`, `fecha_ultimo_contacto`, `hora_ultimo_contacto`, `Entidad_visto`, `Municipio_visto`, `lugar_ultimo_contacto`, `senas_tatujes_datos_identificacion`, `con_o_sin_vida`, `fecha_localizacion`, `voluntaria`, `delito`, `observaciones`, `delito_localiza`, `localizado_o_no_localizado_ORI`, `con_o_sin_vida_ORI`, `fecha_localizacion_ORI`, `voluntaria_ORI`, `fue_delito_ORI`, `delito_ORI`, `observaciones_ORI`, `CURP_OK`, `NOMBRE_OK` y `delito_localiza_vf`.

`FUB_OK` **sí** se exporta como `fub_ok_banci`; ambas columnas están vacías en esta entrega. En la configuración, `FUB_OK` también figura como alias de respaldo para `folio_rnpdno`, pero aquí se encuentra primero `folio_RNPDNO`, que alimenta `folio_rnpdno_banci`.

## 6. Privacidad y cautelas

- El Excel incluye nombres, CURP, RFC, domicilio, coordenadas, folios, detalles de identificación y observaciones: restringir acceso y no publicar filas de ejemplo.
- La salida reduce exposición al omitir domicilio, coordenadas y diversos datos, pero aún conserva nombres, CURP, FUB/folio y llaves de carpeta, por lo que sigue siendo sensible.
- Las definiciones de algunos códigos abreviados (por ejemplo `DTO`, `TPM`, `POB`, `DISC`, `NO_BANCI`) son aproximadas por nombre; consultar el diccionario oficial BANCI para su interpretación institucional exacta.
- Los conteos describen estas copias locales y pueden cambiar con otra entrega o con modificaciones del ETL.

## 7. Verificación básica en R

```r
library(readxl)
library(arrow)

archivo_excel <- "input/banci/SUBIR_R_202609_septiembre.xlsx"
archivo_parquet <- "output/Resultado_2_Procesamiento_ETL_BANCI_autonomo.parquet"

origen <- read_excel(archivo_excel, sheet = "Victimas")
etl <- read_parquet(archivo_parquet)

c(n_filas_excel = nrow(origen), n_columnas_excel = ncol(origen))
c(n_filas_etl = nrow(etl), n_columnas_etl = ncol(etl))

# La llave y el orden de los registros se conservaron en esta corrida.
stopifnot(nrow(origen) == nrow(etl))
stopifnot(all(trimws(as.character(origen$LLAVE)) == trimws(as.character(etl$llave_banci))))

# Conteos del estatus normalizado y de la validación estructural de CURP.
table(etl$localizado_o_no_localizado_derivada_banci, useNA = "ifany")
table(etl$curp_valida_derivada_banci, useNA = "ifany")
```
