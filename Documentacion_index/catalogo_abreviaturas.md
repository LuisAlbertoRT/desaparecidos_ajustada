# Catálogo de abreviaturas y nomenclatura

## 1. Bases y conceptos principales

| Abreviatura | Significado |
|---|---|
| `reg` | Registros |
| `rn` | Registros en RNPDNO |
| `ba` | Registros en BANCI |
| `mr` | Registros en MJ y RIPS (detenciones penitenciarias) |

## 2. Combinaciones de bases

| Abreviatura | Significado |
|---|---|
| `rn-no-ba` | Registros en RNPDNO que no están en BANCI |
| `rn-si-ba` | Registros en RNPDNO que sí están en BANCI |
| `ba-no-rn` | Registros en BANCI que no están en RNPDNO |
| `ba-si-rn` | Registros en BANCI que sí están en RNPDNO |

---

## 3. Estatus de localización

| Abreviatura | Significado |
|---|---|
| `des` | Desaparecidos |
| `loc` | Localizados |
| `cvid` | Con vida |
| `svid` | Sin vida |

---

## 4. Características del caso

| Abreviatura | Significado |
|---|---|
| `cdel` | Con delito |
| `sdel` | Sin delito |
| `cind` | Con indicios de vida — con registro administrativo en la PUI (ver la nota de abajo) |
| `sind` | Sin indicios de vida — sin ningún registro administrativo |
| `sisf` | Sin información suficiente (sin curp válida y sin registro admnistrativo) |
| `cisf` | Con información suficiente (el complemento de sisf)|
| `sdat` | Sin datos (NA's) |
| `dfor` | Desaparición forzada |
| `cpar` | Desaparición cometida por particulares |
| `cfval` | Con folio válido — el expediente cumple el formato de Carpeta de Investigación de su entidad (`CATALOGO_REGEX_CI_POR_ENTIDAD`) |
| `sfval` | Sin folio válido — el expediente no cumple el formato, ya sea porque el folio capturado no pasa o porque el campo viene vacío |
| `cfvac` | Con folio vacío (el campo de expediente es NAN o cadena vacía) |
| `sfvac` | Sin folio vacío (el campo de expediente trae texto, válido o no) |
| `fmz` | Formalizados — el indicio de vida ya derivó en una localización registrada en el RNPDNO |

> `cfval` y `sfval` son una **partición**: los dos suman el universo del que se
> derivan. `cfvac` y `sfvac` son otra partición transversal —dicen si el campo
> trae texto, no si ese texto es válido— y al cruzarse parten `sfval` en las dos
> ramas que consumen las plantillas:
> `sfval_sfvac` (hay folio, pero no pasa el criterio) + `sfval_cfvac` (el campo
> viene vacío) = `sfval`.
> No confundir `cfvac` (el campo de folio viene vacío) con `ccvac` (a la persona le
> faltan campos de identificación).

> `ccarp` / `scarp` (con / sin carpeta de investigación) ya no existen: ningún indicador los
> usaba y el criterio de carpeta sólo alimenta `cfval`. Ver
> [6. Arquitectura](docs/6_arquitectura.md#clasificación-de-carpeta-de-investigación).

> `cind` significa literalmente **"hay registro administrativo posterior a la
> desaparición"**, y eso incluye las actas de defunción, que el notebook 3 etiqueta igual
> que los indicios de vida. Tampoco distingue si el registro venía sólo de la PUI o si
> además lo confirmó una confronta manual: `indicadora_indicio_de_vida_derivada_pui` llega
> binaria al universo.
> El detalle está en [8. Indicios de vida](docs/8_indicios_de_vida.md).

> `dfor` y `cpar` particionan las bases **matcheadas** (`rn-si-ba`, `ba`): la
> clasificación la aporta `delito_hom_banci`, y `propagar_delito_desde_banci` la
> lleva a cada FUB emparejado, incluidos los extra de
> `fubs_confirmados_manual_derivada_rnpdno_banci`. En `rn` a secas NO particionan:
> `delitolocalizacion_rnpdno` está vacía en el 100 % de los
> desaparecidos, así que fuera del cruce casi nadie tiene ninguna de las dos.

| `ddes` | Cambio en el número de desaparecidos |
| `dloc` | Cambio en el número de localizados |

---

## 5. Datos faltantes

| Abreviatura | Significado |
|---|---|
| `smuni` | Sin municipio |
| `sfnac` | Sin fecha de nacimiento |
| `sfdes` | Sin fecha de desaparición — se cuenta sobre `fechahechos_derivada_rnpdno`, la fecha de hechos del RNPDNO sin rellenar, NO sobre `fecha_hechos_modificada_derivada_rnpdno`, que el ETL rellena con percato/captura y deja sin nulos |
| `snomb` | Sin nombre — le falta alguno de los tres campos crudos (`nombre_vic_rnpdno`, `primerapellido_vic_rnpdno`, `segundoapellido_vic_rnpdno`) o el nombre concatenado no pasa el criterio de nombre (sin dígitos, sin texto de relleno, ≥ 11 caracteres) |
| `ssexo` | Sin sexo |
| `scurp` | Sin CURP |
| `sfub` | Sin FUB |

> Los campos de esta sección se cuentan siempre sobre la columna **sin rellenar** del
> RNPDNO, no sobre su derivada del ETL: las derivadas rellenan (`fecha_hechos_modificada_derivada_rnpdno`)
> o concatenan con `fillna("")` (`nombre_completo_derivada_rnpdno`) y tapan justo
> el hueco que el recuadro "Datos faltantes" quiere medir.

---

## 6. Entidad federativa

| Abreviatura | Significado |
|---|---|
| `ent<NN>` | Clave INEGI de la entidad, a dos dígitos (`ent17` = Morelos, `ent09` = Ciudad de México) |
| *(sin token)* | Nacional — sin filtro de entidad |

La entidad es una **dimensión de rebanada**, no un filtro previo al matching: el universo
se construye siempre nacional y la clave de entidad viaja como columna, de modo que las 32 entidades
se obtienen de una sola corrida de motores.

---

## 7. Instición de procedencia

| Abreviatura | Significado |
|---|---|
| `fis` | Físcalias |
| `com` | Comisiones |
| `por` | Portal |
| `nnal` | Nacional |
| `lcal` | Local |

---


## 8. Fechas

| Abreviatura | Significado |
|---|---|
| `min` | Fecha mínima de la base |
| `max` | Fecha máxima de la base |
| `01ene06` | 1 de enero de 2006 |
| `01oct24` | 1 de octubre de 2024 |
| `01ago25` | 1 de agosto de 2025 |
| `25mar26` | 25 de marzo de 2026 — corte congelado de referencia, no un período del pipeline |
| `01jul26` | 1 de julio de 2026 — segundo corte congelado de referencia, tampoco un período del pipeline |
| `24jun26` | 24 de junio de 2026 — fecha del directorio de indicios de vida, tampoco un período del pipeline |

---


## 9. Períodos de tiempo

| Abreviatura | Significado |
|---|---|
| `min-max` | De la fecha mínima a la fecha máxima de la base |
| `min-01ene06` | De la fecha mínima de la base al 31 de diciembre de 2005 (antes del 1 de enero de 2006) |
| `01ene06-max` | Del primero de enero de 2006 a la fecha máxima de la base |
| `min-01oct24` | De la fecha mínima de la base al 30 de septiembre de 2024 (antes del 1 de octubre de 2024) |
| `01oct24-max` | Del primero de octubre de 2024 a la fecha máxima de la base |
| `01ago25-max` | Del 1 de agosto de 2025 a la fecha máxima de la base |
| `01jul26-max` | Del 1 de julio de 2026 a la fecha máxima de la base |
| `24jun26-max` | Del corte del directorio de indicios (24/06/2026) a hoy. **No es un período de `PERIODOS_TIEMPO`**: ver 9 quáter |



---


## 9 bis. Marcadores de diferencia (`<actual>-<corte>`)

Dos nombres canónicos unidos por un guion son una **resta**: cuánto creció el indicador
desde un corte de referencia congelado.

```
reg_rn_01ene06-max_des_sisf-reg_rn_25mar26_des_sisf
  =  reg_rn_01ene06-max_des_sisf  −  reg_rn_25mar26_des_sisf
```

El minuendo lo calcula el pipeline; el sustraendo es un corte que **no** pasa por él:
llega como Excel ya rebanado en `input/datos_marzo` (un archivo por marcador, el nombre
del archivo es el nombre del marcador) y se declara en `config.CORTE_25MAR26_FILES`.
El corte del 01/07/2026 funciona igual, desde `input/datos_julio` y
`config.CORTE_01JUL26_FILES`, con las mismas tres rebanadas:

```
reg_rn_01ene06-max_des_sisf-reg_rn_01jul26_des_sisf
  =  reg_rn_01ene06-max_des_sisf  −  reg_rn_01jul26_des_sisf
```

Los dos se registran en `config.CORTES_REFERENCIA`. Lo cuenta `src.utils.contar_corte`,
y `diferencias_vs_corte` arma las restas para inyectarlas en
`Universo.indicadores(..., extra=...)`.

`pct_` sobre una resta es el **crecimiento porcentual**: la diferencia dividida entre el
corte, no entre el padre de la rebanada.

Los registros de una resta se entregan como base con el mismo nombre del marcador
(`reg_rn_01ene06-max_des_sisf-reg_rn_25mar26_des_sisf.parquet`): las altas (`_ddes`) y las
bajas (`_dloc`) de la sección 9 ter juntas, una fila por registro, con la columna
`movimiento_derivada_rnpdno_25mar26` = `alta` / `baja`. Las altas menos las bajas dan el
marcador. Los escribe `src.cortes_referencia.movimientos_vs_corte` desde el notebook 6
(`DIFERENCIAS_A_EXPORTAR`).

---

## 9 ter. Sufijos de delta (`_ddes`, `_dloc`)

Sobre un indicador que se compara contra el corte congelado, estos sufijos separan
las dos corrientes que componen el saldo neto, cruzando los **`fub`** de ambas fotos:

| Sufijo | Significado |
|---|---|
| `_ddes` | **Altas** — está en el indicador de hoy y **no** en el corte de referencia |
| `_dloc` | **Bajas** — está en el corte de referencia y **no** en el indicador de hoy |
| `_dfub` | **Sin cruzar** — la fila no trae `fub`, así que no puede caer ni en altas ni en bajas |

```
reg_rn_01ene06-max_des_sisf_ddes  −  reg_rn_01ene06-max_des_sisf_dloc
  =  reg_rn_01ene06-max_des_sisf-reg_rn_25mar26_des_sisf
```

Las dos corrientes suelen ser mucho mayores que su diferencia, así que el neto por sí
solo esconde el movimiento real. Un registro causa baja porque la persona fue localizada
(de ahí `dloc`) **o** porque dejó de cumplir el subfiltro —p. ej. perdió el registro
administrativo activo en PUI—, de modo que `_dloc` es una **cota superior** de las
localizaciones, no su conteo exacto.

`_dfub` queda **fuera** de esa identidad: sin llave no hay cruce posible, y esas filas
tampoco entran en los totales del pipeline, que sólo cuenta registros de la base `rn`.
La clave sólo se emite cuando hay alguna; hoy el único caso es
`reg_rn_25mar26_des_cisf_sind`, cuyas 137 filas sin `fub` son todas
`origen_categoria_union == "Solo banci, sin intersección"`.

El nombre del marcador no dice contra qué corte se cruzó, así que los del corte de julio
llevan `_v2` al final:

```
reg_rn_01ene06-max_des_sisf_ddes_v2  −  reg_rn_01ene06-max_des_sisf_dloc_v2
  =  reg_rn_01ene06-max_des_sisf-reg_rn_01jul26_des_sisf
```

Lo calcula `src.utils.deltas_vs_corte` (con `sufijo="_v2"` para julio), que necesita el
`Slice` (para sacar los `fub` del universo) y no sólo el total.

Los registros de un `_dloc` se entregan como base con el mismo nombre del marcador
(`reg_rn_01ene06-max_des_sisf_dloc.parquet`): las filas del corte, con sus columnas
sufijadas `_25mar26`, más el estado que hoy tiene cada `fub` en el universo. Los escribe
`src.cortes_referencia.bajas_vs_corte` desde el notebook 6 (`BAJAS_A_EXPORTAR`). Los de
julio salen igual, con el `_v2` del marcador (`reg_rn_01ene06-max_des_sisf_dloc_v2.parquet`)
y las columnas del corte sufijadas `_01jul26` (`BAJAS_VS_JULIO_A_EXPORTAR`).

---

## 9 quáter. Indicios formalizados (`24jun26-max_loc_fmz`)

Un marcador que **no** es una rebanada del universo, aunque lo parezca:

```
reg_rn_24jun26-max_loc_fmz        total de indicios ya formalizados
pct_reg_rn_24jun26-max_loc_fmz    su porcentaje contra el total del país
reg_rn_24jun26-max_loc_fmz_v2     el mismo conteo, pero de todo el país
reg_rn_24jun26-max_loc_fmz_v3     el complemento del anterior: el resto del país
gr_ent_rn_24jun26-max_loc_fmz     su desglose por entidad
reg_rn_24jun26-max_loc_fmz_v4     el total, pero de las 32 entidades federativas
gr_32ent_rn_24jun26-max_loc_fmz   su desglose por entidad, de esas 32
```

> No confundir este `fmz` con la bandera `cind` de la sección 4: son dos "indicios de vida"
> distintos y de fuentes distintas. La comparación está en
> [8.0](docs/8_indicios_de_vida.md).

Su población no sale del RNPDNO ni de BANCI, sino de un **directorio congelado** de
personas con indicio de vida al 24/06/2026 (`config.DIRECTORIO_INDICIOS_FILE`), que llega
como Excel y no pasa por el pipeline. El `24jun26-max` tampoco es un rango de fechas de
hechos: es "desde aquel corte hasta hoy".

La pregunta que responde es: **de aquellos indicios de vida, ¿a cuántos les siguió una
localización registrada?** Se contesta cruzando el directorio contra el RNPDNO vigente por
`fub` y contando los que hoy están como `Localizados` — de ahí `loc_fmz`.

Dos criterios que conviene tener presentes:

- Un `fub` del directorio que **no aparece** en el RNPDNO cuenta como todavía desaparecido.
  No hay evidencia de localización, y descartarlo inflaría el porcentaje de formalizados.
- El conteo se acota a las 24 entidades de `config.DIRECTORIO_INDICIOS_ESTADOS`, las que
  participan en la Búsqueda Generalizada. Las demás quedan fuera **a propósito**.

### El sufijo `_v2`: el mismo conteo, sin acotar por entidad

`reg_rn_24jun26-max_loc_fmz_v2` es exactamente el mismo indicador que
`reg_rn_24jun26-max_loc_fmz` —los indicios del directorio que ya se formalizaron como
localización— con **una sola diferencia**: no se filtra a `DIRECTORIO_INDICIOS_ESTADOS`,
así que cuenta a todo el país. La lámina lo rotula "Total de país" y por eso el otro
marcador es siempre menor o igual:

```
reg_rn_24jun26-max_loc_fmz     3,927   sólo las 24 entidades de la Búsqueda Generalizada
reg_rn_24jun26-max_loc_fmz_v2  4,217   todas las entidades del directorio
reg_rn_24jun26-max_loc_fmz_v3    290   el resto del país  (= _v2 − el primero)
```

*(cifras de la corrida del 14/09/2026; cambian con cada corte del RNPDNO, porque el
directorio está congelado pero el estatus contra el que se cruza no.)*

El `_v2` **no** es una versión nueva que reemplace a la anterior: las dos conviven en la
misma lámina. Es el único marcador de la plantilla que lleva ese sufijo.

`pct_reg_rn_24jun26-max_loc_fmz` no sigue la regla del padre de la sección 10 —no hay
`Slice` del que colgarse—: su denominador es el **total del país**, o sea el propio
`_v2`. Mide qué parte de los formalizados de todo el directorio cae en las 24 entidades
de la Búsqueda Generalizada:

```
pct_reg_rn_24jun26-max_loc_fmz  =  3,927 / 4,217  =  93.1%
```

No se calcula contra las 33,430 personas del directorio en esas entidades (el total que
la lámina rotula "Entidades participantes en la Búsqueda Generalizada"); ese número sigue
disponible como `universo`, pero sólo alimenta la gráfica y el log.

### El sufijo `_v3`: el resto del país

`reg_rn_24jun26-max_loc_fmz_v3` es el complemento exacto del primero dentro del `_v2`:

```
reg_..._fmz  +  reg_..._fmz_v3  =  reg_..._fmz_v2
```

La resta la hace `indicios_formalizados` —devuelve `resto`— y no el cuaderno, para que las
tres cifras de la lámina salgan de la misma pasada y no puedan discrepar.

### El sufijo `_v4` y la gráfica `gr_32ent`: las 32 entidades

La plantilla trae una lámina gemela que no acota a la Búsqueda Generalizada.
`reg_rn_24jun26-max_loc_fmz_v4` cuenta los formalizados de las **32 entidades
federativas** y `gr_32ent_rn_24jun26-max_loc_fmz` los desglosa, una barra por entidad.

No es el `_v2`: éste cuenta todo el directorio, incluso a quien no tiene entidad
("Nacido en el extranjero"), y el `_v4` sólo a las 32. Por eso:

```
reg_..._fmz  ≤  reg_..._fmz_v4  ≤  reg_..._fmz_v2
   4,421            4,787              4,788        (corrida del 06/10/2026)
```

Las 32 no se teclean: salen del catálogo INEGI `config.ENTIDADES` (claves 1 a 32), con los
mismos renombres que el directorio (`México` → `Estado de México`).

Lo calcula `src.directorio_indicios.indicios_formalizados`, que devuelve los dos tabulados
por entidad —el de las 24 y el de las 32, lo que dibujan las dos gráficas— y un
diccionario con `total`, `nacional` (el denominador), `pct`, `resto`, `universo` y
`total_32`. Se inyecta con `extra=` en `Universo.indicadores`, igual que las diferencias
contra el corte de marzo.

---

## 9 quinquies. RNIP y MJ (`reg_mr_*`)

La otra base que **no** es una rebanada del universo. Su población sale del archivo
`config.MJ_RIPS_FILE` —las personas del RNPDNO halladas en un **Mandamiento Judicial**
(hoja `MJ UNICOS`) o en el **registro penitenciario** (hoja `RIPS UNICOS`)—, no del
RNPDNO ni de BANCI, así que no pasa por el matching ni por `Slice`. Lo calcula
`src.utils.cruzar_mj_rips` y sus conteos entran por `extra=` en `Universo.indicadores`,
igual que los indicios formalizados de la sección anterior.

```
reg_mr_min-max            todos los registros del archivo
reg_mr_min-max_des        los que hoy siguen desaparecidos
reg_mr_min-max_loc        los que hoy están localizados
reg_mr_min-max_loc_cvid   de esos localizados, con vida
reg_mr_min-max_loc_svid   de esos localizados, sin vida
fha_mr_dia_mes_anio       la fecha de corte del archivo
```

El `min-max` **no rebana nada**: el archivo es una foto fija y se toma completo. Va en el
nombre porque el período es obligatorio en la nomenclatura de la sección 11.

La pregunta que responde es: **de las personas con detención penitenciaria, ¿cuántas
siguen desaparecidas en el RNPDNO y cuántas ya están localizadas, con vida o sin ella?**
Se contesta cruzando el archivo contra `Universo.rn` por `fub_rnpdno` y leyendo de ahí
`estatus_loc_derivada_rnpdno`, `is_cvid_derivada_rnpdno` e `is_svid_derivada_rnpdno`.

Tres criterios que conviene tener presentes:

- Las dos hojas se concatenan **sin deduplicar**. Un `fub` que está en MJ y además en
  RIPS son dos registros, que es lo que cuenta la lámina ("Total registros de RNIP y
  MJ"). La columna `tipo` dice de cuál hoja vino cada uno.
- Un `fub` que **no aparece** en el RNPDNO cuenta como todavía desaparecido, por la misma
  razón que en el directorio de indicios: no hay evidencia de localización.
- Sus `pct_` sí siguen la regla del padre de la sección 10, escrita a mano en
  `src.utils.MJ_RIPS_DENOMINADOR` porque no hay `Slice` del que colgarse. Las dos parejas
  son particiones y suman 100%:

```
des  + loc   = reg_mr_min-max        →  pct_ contra el total del archivo
cvid + svid  = reg_mr_min-max_loc    →  pct_ contra los localizados
```

---

## 10. Porcentajes (`pct_`)

Un marcador `pct_X` es `X` dividido entre **la misma rebanada sin su último filtro**
(`Slice.padre`). Se quita, en este orden: entidad → último subfiltro → estatus → período.

```
pct_reg_rn_01oct24-max_loc_cdel  =  reg_rn_01oct24-max_loc_cdel / reg_rn_01oct24-max_loc
pct_reg_rn_01oct24-max_des       =  reg_rn_01oct24-max_des      / reg_rn_01oct24-max
```

Cuando esa regla no aplique, se pasa el denominador explícito:

```python
u.porcentaje(Slice("rn-si-ba", "01oct24-max", estatus="des"),
             Slice("rn", "01oct24-max", estatus="des"))
```

### Repartos que suman 100%: `pct_X_v1`, `_v2`, `_v3`

Cada porcentaje se redondea por su lado, así que los recuadros de una lámina que se
reparten un total pueden sumar 99.9% o 100.1%. Las láminas 5, 6 y 7 del reporte diario
usan en su lugar marcadores con sufijo, que salen de
`src.particiones.porcentajes_particion`: reparte las décimas por **resto mayor** para
que el grupo sume exactamente 100.0%, sin mover ninguna parte más de una décima.

La misma rebanada aparece en varias láminas contra denominadores distintos, y el sufijo
dice a qué reparto pertenece. Dentro de una lámina, los del mismo sufijo suman 100%:

```
_v1  láminas 5 y 7:  rn-si-ba_..._des + rn-no-ba_..._des              = rn_01oct24-max_des
     lámina 6:       ..._sfval_sfvac + ..._sfval_cfvac                = rn-no-ba_..._des_sfval
_v2  lámina 6:       rn-si-ba_..._des + ..._cfval + ..._sfval         = rn_01oct24-max_des
_v3  lámina 7:       ..._cfval + ..._sfval_sfvac + ..._sfval_cfvac    = rn-no-ba_01oct24-max_des
```

Se declaran en `PARTICIONES` del notebook 6 como `(sufijo, denominador, partes)`. Si las
partes no suman el denominador, el cálculo se detiene en vez de forzar el 100%.

---

## 11. Orden de los tokens

El nombre canónico lo genera `src.slices.Slice.nombre` y siempre sigue este orden:

```
reg_<base>_<periodo>[_<estatus>][_<subfiltro>][_ent<NN>]
```

Los tokens entre corchetes se omiten cuando valen `all` / nacional. La operación inversa
es `Slice.desde_nombre("reg_rn_01oct24-max_des_ent17")`.

---





## 13. Graficas

| Abreviatura | Significado |
|---|---|
| `gr` | Figura de gráfica (generalmente en png) |
| `ent` | entidad o por entidades |
| `32ent` | por entidades, con las 32 entidades federativas aunque la lámina hermana acote a una selección |


---

## 14. Fechas

| Abreviatura | Significado |
|---|---|
| `fha` | Fecha |
| `hoy` | Hoy |
| `dia` | Día |
| `mes` | Mes |
| `anio` | Año |
| `umes` | Último mes |
| `uanio` | Último mes |


Un marcador de fecha se nombra `fha_<qué fecha>_<partes>`, y **la cola de partes ES el
formato**: `src.utils.formatear_fecha_es` las une con " de " en el orden en que aparecen.

| Marcador | Valor |
|---|---|
| `fha_rn_dia_mes_anio` | Corte del RNPDNO — `17 de agosto de 2026` |
| `fha_rn_mes_anio` | `agosto de 2026` |
| `fha_rn_anio` | `2026` |
| `fha_ba_dia_mes_anio` | Corte del BANCI — `31 de julio de 2026` |

Los emite `Universo.indicadores` para las dos bases (`rn` y `ba`) en las tres variantes,
así que añadir una a la plantilla no requiere tocar código. Sustituyen a los antiguos
`fecha_corte_rnpdno`, `fecha_corte_banci` y `fecha_corte`, que ya no se generan.

---



## 12. Ejemplos

| Abreviatura | Significado |
|---|---|
| `reg_rn_min-max_loc_cvid` | Registros de personas localizadas con vida del RNPDNO (sin filtrar fechas) |
| `reg_rn_01ene06-max_des_sind_sdat` | Registros de personas desaparecidas sin indicios de vida y sin datos con fechas que van del primero de enero de 2006 a la fecha máxima de la base |
| `reg_rn-si-ba_01oct24-max_des_cpar` | Registros de personas pesonas desaparecidas de RNPDNO que no estan en BANCI filtradas del primero de octubre de 2024 a la fecha máxima de la base y que fueron catalogadas como desapariciones cometida por particulares |
| `reg_rn-01oct24-max-si-ba-01ago25-max_des_cpar` | Registros de personas pesonas desaparecidas que fueron catalogadas como desapariciones cometida por particulares de RNPDNO que si estan en BANCI filtradas del primero de octubre de 2024 a la fecha máxima para RNPDNO y del primero de agosto de 2025 a la fecha máxima para BANCI |
| `reg_rn-01oct24-max-si-ba-01ago25-max` | Registros del RNPDNO que si estan en BANCI filtradas del primero de octubre de 2024 a la fecha máxima para RNPDNO y del primero de agosto de 2025 a la fecha máxima para BANCI |
| `reg_rn_01oct24-max_des_ent17` | Registros de personas desaparecidas del RNPDNO del primero de octubre de 2024 a la fecha máxima, sólo Morelos |
| `reg_rn-si-ba_01oct24-max_des_cfval_ent25` | Registros de personas desaparecidas del RNPDNO que sí están en BANCI, con folio válido, del sexenio, sólo Sinaloa |
| `fha_hoy_dia_mes_anio` | fecha de hoy con día mes y año |
| `fha_hoy_dia_mes` | fecha de hoy con día y mes unicamente |
| `fha_01ene06_mes_anio` | fecha del primero de enero de 2006 con mes y año unicamente |
| `gr_ent_reg_rn-no-ba_01oct24-max_des_sfval_sfvac` | Gráfica por entidades de los registros de desaparecidos con folio capturado pero no válido del rnpdno que no estan en banci filtrado a partir del primero de octubre de 2024 hasta la fecha máxima |


---
