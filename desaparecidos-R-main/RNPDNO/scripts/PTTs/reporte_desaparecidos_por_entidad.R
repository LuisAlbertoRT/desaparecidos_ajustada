# --------------------------------------------------------- #
# Nombre: Jocelyn Rocha
# Contacto: maricelaymiel@gmail.com
# Script: reporte_desaparecidos_por_entidad.R
# Proyecto: Personas Desaparecidas
# Fecha: 2026-05-15
# Propósito: Generar presentación PPTX del 1. árbol del registros de desaparecidos y localizados 2. desglose por origen de dependencia y 3. resumen de carpetas de investigación
# --------------------------------------------------------- #
# Librerías -----
# --------------------------------------------------------- #

rm(list = ls()) # Limpiar el entorno de trabajo

pacman::p_load(
  readr, tidyverse, dplyr, lubridate, readxl,
  scales, magrittr, stringi, tsibble, svglite,
  here, janitor, officer, reticulate, purrr,
  glue,

  officer
)

# --------------------------------------------------------- #
# Funciones -------
# --------------------------------------------------------- #

#' Redondea un vector de pesos a porcentajes que suman exactamente 100
#'
#' Método del mayor residuo (Hamilton/Largest Remainder Method). Evita que
#' redondear cada porcentaje de forma independiente produzca sumas como
#' 99.9% o 101% (p. ej. 33.3 + 33.3 + 33.3 = 99.9, o 50% + 51% = 101%).
#'
#' @param pesos Vector numérico de conteos (o cualquier magnitud proporcional)
#'   que se convertirán a porcentajes sobre su propia suma.
#' @param decimales Número de decimales del porcentaje final. Default 0.
#'
#' @return Vector numérico del mismo largo que `pesos`, con los porcentajes
#'   redondeados a `decimales` decimales, garantizando que su suma sea 100.
#'
#' @examples
#' redondear_porcentajes(c(1, 1, 1), decimales = 0)      # 34, 33, 33 -> suma 100
#' redondear_porcentajes(c(30, 25, 22, 18, 5), decimales = 1)
redondear_porcentajes <- function(pesos, decimales = 0) {

  total <- sum(pesos, na.rm = TRUE)

  if (length(pesos) == 0 || total == 0) {
    return(rep(0, length(pesos)))
  }

  factor <- 10^decimales
  porcentajes_exactos <- pesos / total * 100

  # Redondeamos hacia abajo a la precisión deseada
  porcentajes_piso <- floor(porcentajes_exactos * factor) / factor
  residuos <- porcentajes_exactos - porcentajes_piso

  # Cuántas "unidades" (de tamaño 1/factor) faltan para llegar a 100
  unidades_faltantes <- round((100 - sum(porcentajes_piso)) * factor)

  if (unidades_faltantes > 0) {
    # Se las damos a quienes tengan mayor residuo (empates: el primero en orden)
    indices_a_ajustar <- order(-residuos)[seq_len(unidades_faltantes)]
    porcentajes_piso[indices_a_ajustar] <- porcentajes_piso[indices_a_ajustar] + 1 / factor
  }

  porcentajes_piso
}

# ---- Función de actualización y procesamiento de variables ---- #
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_actualizar_rnpdno_y_procesar_variables.R"))

# ------ Función para generar comprimido con intersección entre RNPDNO y BANCI ---- #
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_banci_rnpdno_matching_completo.R"))


# ------ Función para actualizar ppt de reporte semanal ------ #
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_actualizar_confrontas_de_PUI.R"))

# Función de Exportar Excel con formato institucional de la ATDT 
source(here::here("RNPDNO", "scripts", "funciones_auxiliares",
       "funciones_recurrentes.R"))

# --------------------------------------------------------- #
# Bases de datos -------
# --------------------------------------------------------- #

# ---- Actualizar RNPDNO ----- #
# Definimos la fecha de corte para la actualización del reporte semanal
fecha_corte <- today() - 1

comprimido <- actualizar_rnpdno_y_procesar(
  fecha_corte = fecha_corte,
  registros = registros,
  catalogo_estados_inegi = catalogo_estados_inegi,
  catalogo_municipios_inegi = catalogo_municipios_inegi,
  descargar = FALSE
)

# ------- Actualizar registros en intersección con BANCI ------ #
# Ruta de archivos de Secretariado originales
subeR <- readxl::read_excel(here("RNPDNO",
                        "input",
                        "datos_de_fiscalias",
                        "datos_originales",
                        "SUBIR_R_202607_julio.xlsx"), sheet = 2,
                        col_types = "text" # Leemos todo como texto para no perder datos
                        ) |> 
  clean_names()

# Limpiamos las columnas de fechas y avisamos si hay fechas que no se pudieron convertir
subeR <- subeR |> 
  mutate(across(matches("^fha|^fecha"), limpiar_y_avisar))

# Corección datos con fha_hechos mal etiquetadas
subeR <- subeR |> 
  mutate(
    fha_de_hchos = if_else(fha_de_hchos >= as.Date(fecha_corte), 
                            fha_de_hchos - years(1), 
                            fha_de_hchos)
  )

# --- Archivos más recientes de intersecciones BANCI-RNPDNO ---- #
archivos <- c("Base_BANCI_con_match_con_RNPDNO.RData",
              "Base_BANCI_sin_match_con_RNPDNO.RData")

lapply(here::here("RNPDNO",
                  "output",
                  "cruces_banci_rnpdno",
                  "cruces_banci_rnpdno_18082026",
                  archivos), load,
       .GlobalEnv)

comprimido <- tratamiento_banci_rnpdno(
  subeR = subeR,
  comprimido = comprimido,
  nueva_BANCI = FALSE,
  fecha_inicio_BANCI = "2025-08-01",
  fecha_fin_BANCI = "2026-07-31",
  tipo_conjunto = "interseccion",
  guardar_bases_matching = FALSE,
  Base_BANCI_con_match_con_RNPDNO = Base_BANCI_con_match_con_RNPDNO,
  Base_BANCI_sin_match_con_RNPDNO = Base_BANCI_sin_match_con_RNPDNO,
  registros_localizados = registros_localizados
)

# ----- Actualizar confrontas de PUI ----- #
resultados <- actualizar_confrontas_de_pui(
        registros = registros,
        defunciones_df = defunciones_df,
        comprimido = comprimido,
        coincidencias_admin_con_inactivas = "2026-09-07",
        guardar_registros_con_pui = TRUE
)

# Extraer comprimido y registros_con_pui
comprimido <- resultados[["comprimido_actualizado"]]
registros_con_pui_activos <- resultados[["registros_con_pui_activos"]]

# Limpiar objetos intermedios
objetos_a_eliminar <- c("resultados", "coincidencias_admin_con_inactivas")
rm(list = intersect(objetos_a_eliminar, ls()))
gc()

# ————————————————————————————————————————————————————————— #
# Actualizar sub_clasificación de los registros de desaparecidos con base en matches consolidados entre BANCI y RNPDNO ----
# ————————————————————————————————————————————————————————— #

# Leer archivos desde Google Drive
readRenviron(".Renviron")
Sys.getenv("RNPDNO_data_raiz")

carpeta_matches_consolidados <- raiz_datos("RNPDNO", "output")

# Actualización de matches_consolidados
matches_consolidados <- readxl::read_excel(
  file.path(carpeta_matches_consolidados, "cruces_banci_rnpdno",
            "matches_consolidados", "actualizacion_18082026", "matches_consolidados_unicos_en_fub_sexenio_subeR_julio_18082026.xlsx")
)

matches_consolidados <- matches_consolidados |> 
  select(-fecha_hechos_modificada)

matches_consolidados <- matches_consolidados |> 
  left_join(comprimido |> select(fub, clasificacion_des_actualizado = clasificacion_des, fecha_hechos_modificada), by = c("fub_rnpdno" = "fub"))

matches_consolidados |> 
  count(clasificacion_des_actualizado)
#   clasificacion_des_actualizado    n
# 1                 Desaparecidos 5510
# 2                   Localizados  57
# 3                    Pendientes  940

matches_consolidados <- matches_consolidados |> 
  filter(clasificacion_des_actualizado != "Localizados")

# Solo considerar registros por encima del 01 del 08 de 2025
matches_consolidados_ppt <- matches_consolidados |> 
  filter(fecha_hechos_modificada >= "2025-08-01")

num_matches_consolidados_ppt <- matches_consolidados_ppt |> nrow()
cat("Hay ", num_matches_consolidados_ppt, " registros de desaparecidos con matches consolidados entre BANCI y RNPDNO\n")

# Si el registro se encuentra en matches_consolidados_ppt, entonces actualizamos dependencia_origen y se cambia a "Fiscalía con carpeta de investigación".
# También actualizamos 'indicadora_carpeta' a "Con carpeta"
comprimido <- comprimido |> 
  mutate(
    fub_en_matches_consolidados = if_else(fub %in% matches_consolidados_ppt$fub_rnpdno, "En matches consolidados", "No en matches consolidados")
  ) |> 
    mutate(
      dependencia_origen = case_when(
        fub_en_matches_consolidados == "En matches consolidados" ~ "Fiscalía con carpeta de investigación",
        TRUE ~ dependencia_origen
      ),
      indicadora_carpeta = case_when(
        fub_en_matches_consolidados == "En matches consolidados" ~ "Con carpeta",
        TRUE ~ indicadora_carpeta
      )
    )
# --------------------------------------------------------- #
# ------- Función: generar_ppt_entidad --------
# Propósito: Generar presentación PPTX por entidad con árbol de registros,
#            desglose por dependencia y resumen de carpetas de investigación
# --------------------------------------------------------- #

# Verificación de la fecha máxima en BANCI
fecha_banci <- max(subeR$fha_de_hchos, na.rm = TRUE)

# Verifica que sea Date
class(fecha_banci)  # Debe ser "Date"

#' Genera el PPT de personas desaparecidas y localizadas de una entidad
#'
#' A partir de la base `comprimido` (RNPDNO/BANCI ya cruzada y clasificada),
#' calcula los conteos y porcentajes de una entidad federativa y llena un
#' template de PowerPoint con 4 slides: portada, árbol (desaparecidos vs.
#' localizados, con/sin datos, con/sin registro administrativo, con/sin
#' delito, con/sin vida), fiscalías (origen de los registros sin indicios:
#' Portal, Comisión, Fiscalía) y una gráfica de localizados por fiscalías a
#' través del tiempo. También guarda un tabulado en Excel con el desglose
#' por año y dependencia.
#'
#' Los porcentajes se redondean con [redondear_porcentajes()] (método del
#' mayor residuo) para que los pares complementarios (p. ej. % con delito +
#' % sin delito) sumen exactamente 100%: 0 decimales en la slide del árbol,
#' 1 decimal en la slide de fiscalías.
#'
#' @param comprimido Data frame con el universo completo de personas
#'   desaparecidas/localizadas (todas las entidades), ya con las columnas
#'   `estado_desaparicion`, `clasificacion_des`, `sub_clasificacion`,
#'   `fecha_hechos_modificada`, `indicadora_curp_valida`,
#'   `indicadora_indicio_de_vida`, `dependencia_origen`, `delitolocalizacion`,
#'   `estatus`, entre otras usadas dentro de la función.
#' @param entidad_de_interes Character. Nombre exacto de la entidad a
#'   procesar, tal como aparece en `comprimido$estado_desaparicion`. Se valida
#'   al inicio de la función y se detiene con un error si no existe.
#' @param fecha_banci Date. Fecha de corte de la Base Nacional de Carpetas de
#'   Investigación (BANCI), usada solo para mostrarse en los textos de fuente
#'   de las slides.
#' @param subeR Actualmente no se usa dentro de la función (parámetro
#'   reservado). Default `NULL`.
#' @param guardar_tabulado Logical. Si `TRUE` (default), guarda un `.xlsx`
#'   con el desglose de `tabla_clasificacion_comprimido_fiscalias` en
#'   `directorio_salida/tabulados_<ddmmyyyy>/`.
#' @param directorio_salida Character. Carpeta base donde se guardan el
#'   tabulado y el PPT. Si es `NULL` (default), usa
#'   `here::here("RNPDNO", "output", "PPT", "PPTs_generadas_por_entidad")`.
#'
#' @return Invisiblemente, una lista con:
#'   \describe{
#'     \item{presentacion}{El objeto `rpptx` ya con las 4 slides.}
#'     \item{archivo_salida}{Ruta del `.pptx` guardado en disco.}
#'     \item{tabla_clasificacion}{El tabulado (data frame) de clasificación
#'       por fiscalías y año.}
#'     \item{resultados_dependencias}{Data frame con el desglose por
#'       dependencia de origen (Portal/Comisión/Fiscalía) y sus porcentajes.}
#'   }
#'
#' @details Requiere el template
#'   `RNPDNO/docs/layout_por_entidad_federativa_arbol_y_fiscalias.pptx` (con
#'   los layouts `portada`, `slide_1`, `slide_2`, `slide_3`) y la función
#'   [redondear_porcentajes()]. Como efecto secundario, crea carpetas y
#'   escribe archivos en disco (`.pptx` y, opcionalmente, `.xlsx`).
#'
#' @examples
#' \dontrun{
#' resultado <- generar_ppt_entidad(
#'   comprimido = comprimido,
#'   entidad_de_interes = "Jalisco",
#'   fecha_banci = as.Date("2026-08-01")
#' )
#' resultado$archivo_salida
#' }
#'
#' @export
generar_ppt_entidad <- function(
  comprimido,
  entidad_de_interes,
  fecha_banci,
  subeR = NULL,
  guardar_tabulado = TRUE,
  directorio_salida = NULL
) {
  
  # Validaciones básicas
  if (!entidad_de_interes %in% comprimido$estado_desaparicion) {
    stop("La entidad '", entidad_de_interes, "' no existe en comprimido$estado_desaparicion")
  }
  
  # Configurar directorio de salida por defecto
  if (is.null(directorio_salida)) {
    directorio_salida <- here::here("RNPDNO", "output", "PPT", "PPTs_generadas_por_entidad")
  }

  # --------------------------------------------------------- #
  # Segmentación y cálculos -----
  # --------------------------------------------------------- #
  
  # Segmentamos entidad de "comprimido"
  comprimido_entidad <- comprimido |> 
    filter(estado_desaparicion == entidad_de_interes)
  
  # ----- REGISTROS TOTALES ----- #
  registros_entidad <- comprimido_entidad |> nrow()
  
  # ------ DESAPARECIDOS ------ #
  desaparecidos_totales_entidad <- comprimido_entidad |> 
    filter(!clasificacion_des %in% "Localizados") 
  
  numero_desaparecidos_totales_entidad <- desaparecidos_totales_entidad |> nrow()
  
  ## Corte especial desde 2006
  desaparecidos_corte_entidad <- desaparecidos_totales_entidad |> 
    filter(fecha_hechos_modificada >= "2006-01-01") 
  
  numero_desaparecidos_corte_entidad <- desaparecidos_corte_entidad |> nrow()
  
  ### Desaparecidos sin datos
  sin_datos_entidad <- desaparecidos_corte_entidad |> 
    filter(clasificacion_des %in% "Pendientes" & 
             indicadora_indicio_de_vida == "sin registro administrativo")
  
  numero_sin_datos_entidad <- sin_datos_entidad |> nrow()
  # NOTA: no encontré en el código nada que garantice que "sin datos" y
  # "con datos" (más abajo) sean una partición exhaustiva de
  # numero_desaparecidos_corte_entidad, así que aquí los dejé con redondeo
  # independiente (round a 0 decimales) en vez de forzar que sumen 100.
  # Si sí son complementarios, avísame y lo ajusto igual que los demás pares.
  porcen_sin_datos_entidad <- round((numero_sin_datos_entidad * 100)/numero_desaparecidos_corte_entidad, 0)
  
  #### Datos faltantes de "sin datos"
  dato_municipios_entidad <- sin_datos_entidad |> filter(is.na(cve_municipio_desaparicion)) |> nrow()
  dato_fecha_nacimiento_entidad <- sin_datos_entidad |> filter(is.na(fechanacimiento)) |> nrow()
  dato_fecha_desaparicion_entidad <- sin_datos_entidad |> filter(is.na(fechahechos)) |> nrow()
  dato_nombre_entidad <- sin_datos_entidad |> 
    filter(is.na(nombre_vic) | is.na(primerapellido_vic) | is.na(segundoapellido_vic)) |> nrow()
  dato_sexo_entidad <- sin_datos_entidad |> filter(sexo %in% "INDETERMINADO" | is.na(sexo)) |> nrow()
  
  ### Desaparecidos con datos
  con_datos_entidad <- desaparecidos_corte_entidad |> 
    filter(!clasificacion_des %in% "Localizados") |> 
    filter(indicadora_curp_valida == "valida" | 
             indicadora_indicio_de_vida == "con registro administrativo") 
  
  numero_con_datos_entidad <- con_datos_entidad |> nrow()
  porcen_con_datos_entidad <- round((numero_con_datos_entidad * 100) / numero_desaparecidos_corte_entidad, 0)
  
  #### Desaparecidos con datos y CON registro administrativo
  con_datos_con_registro_admin_entidad <- con_datos_entidad |> 
    filter(sub_clasificacion == "Desaparecido con registro administrativo")
  
  numero_con_datos_con_registro_admin_entidad <- nrow(con_datos_con_registro_admin_entidad)
  
  ### Desaparecidos con datos y SIN registro administrativo
  con_datos_sin_registro_admin_entidad <- con_datos_entidad |> 
    filter(sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo")
  
  numero_con_datos_sin_registro_admin_entidad <- nrow(con_datos_sin_registro_admin_entidad)
  numero_con_datos_sin_registro_consolidado_entidad <- numero_con_datos_sin_registro_admin_entidad
  numero_final_entidad <- numero_con_datos_sin_registro_consolidado_entidad
  
  ## % con/sin registro administrativo: OJO, este mismo par se usa en la
  ## slide 1 (árbol, 0 decimales) Y en la slide 2 (fiscalías, 1 decimal) —
  ## por eso generamos ambas versiones, cada una sumando 100% por su cuenta.
  pct_registro_admin_0d <- redondear_porcentajes(
    c(numero_con_datos_con_registro_admin_entidad, numero_con_datos_sin_registro_admin_entidad),
    decimales = 0
  )
  pct_registro_admin_1d <- redondear_porcentajes(
    c(numero_con_datos_con_registro_admin_entidad, numero_con_datos_sin_registro_admin_entidad),
    decimales = 1
  )
  
  # Slide 1 (árbol)
  porcen_numero_con_datos_con_registro_admin_entidad <- pct_registro_admin_0d[1]
  porcen_numero_con_datos_sin_registro_admin_entidad <- pct_registro_admin_0d[2]
  
  # Slide 2 (fiscalías) — mismo dato, a 1 decimal
  porcen_numero_con_datos_sin_registro_admin_entidad_1d <- pct_registro_admin_1d[2]
  
  # ------ LOCALIZADOS ------ #
  localizados_totales_entidad <- comprimido_entidad |> 
    filter(clasificacion_des %in% "Localizados")
  
  numero_localizados_totales_entidad <- localizados_totales_entidad |> nrow()
  
  ## % desaparecidos vs. % localizados: por construcción
  ## numero_desaparecidos_totales_entidad + numero_localizados_totales_entidad
  ## == registros_entidad, así que son complementarios exactos.
  pct_estatus_entidad <- redondear_porcentajes(
    c(numero_desaparecidos_totales_entidad, numero_localizados_totales_entidad),
    decimales = 0
  )
  porcentaje_des_entidad <- pct_estatus_entidad[1]
  porcentaje_loc_entidad <- pct_estatus_entidad[2]
  
  ## Localizados con y sin delito (partición exhaustiva: NA vs. no NA)
  localizados_con_delito_entidad <- localizados_totales_entidad |> 
    filter(!is.na(delitolocalizacion)) |> nrow()
  
  localizados_sin_delito_entidad <- localizados_totales_entidad |> 
    filter(is.na(delitolocalizacion)) |> nrow()
  
  pct_delito_entidad <- redondear_porcentajes(
    c(localizados_con_delito_entidad, localizados_sin_delito_entidad),
    decimales = 0
  )
  porcen_localizados_con_delito_entidad <- pct_delito_entidad[1]
  porcen_localizados_sin_delito_entidad <- pct_delito_entidad[2]
  
  ## Localizados con y sin vida
  ## (asumo que "LOCALIZADA CON VIDA" / "LOCALIZADA SIN VIDA" son los únicos
  ## dos valores posibles de `estatus` en localizados; si hay un tercer
  ## valor -p.ej. "no especificado"- esto ya no sumaría 100 real y habría
  ## que sacarlo aparte, avísame si es el caso)
  numero_localizados_con_vida_entidad <- localizados_totales_entidad |> 
    filter(estatus == "LOCALIZADA CON VIDA") |> nrow()
  
  numero_localizados_sin_vida_entidad <- localizados_totales_entidad |> 
    filter(estatus == "LOCALIZADA SIN VIDA") |> nrow()
  
  pct_vida_entidad <- redondear_porcentajes(
    c(numero_localizados_con_vida_entidad, numero_localizados_sin_vida_entidad),
    decimales = 0
  )
  porcen_localizados_con_vida_entidad <- pct_vida_entidad[1]
  porcen_localizados_sin_vida_entidad <- pct_vida_entidad[2]
  
  # ---------------------------------------------------- #
  # Dependencia de origen de las desapariciones -----
  # ---------------------------------------------------- #
  
  comprimido_con_datos_sin_registro_entidad <- comprimido |>
    filter(!clasificacion_des %in% "Localizados",
           fecha_hechos_modificada >= "2006-01-01",
           indicadora_curp_valida == "valida" | indicadora_indicio_de_vida == "con registro administrativo",
           sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo",
           estado_desaparicion == entidad_de_interes)
  
  num_comprimido_con_datos_sin_registro_entidad <- comprimido_con_datos_sin_registro_entidad |> nrow()
  
  # Calcular porcentajes por dependencia, a 1 decimal, garantizando que:
  #   - pct_global sume exactamente 100% entre los 3 grupos (Fiscalía/Comisión/Portal)
  #   - pct_interno sume exactamente 100% dentro de cada grupo
  # (ambos son particiones exhaustivas por construcción: cada fila cae en un
  # grupo_general vía el case_when con TRUE ~ "Portal" como default)
  resultados_finales_entidad <- comprimido_con_datos_sin_registro_entidad |> 
    count(dependencia_origen) |> 
    mutate(grupo_general = case_when(
      grepl("Fiscalía", dependencia_origen) ~ "Fiscalía",
      grepl("Comisión", dependencia_origen) ~ "Comisión",
      TRUE ~ "Portal"
    )) |> 
    mutate(total_base = sum(n)) |> 
    group_by(grupo_general) |> 
    mutate(
      n_grupo = sum(n),
      pct_interno_num = redondear_porcentajes(n, decimales = 1)
    ) |> 
    ungroup()
  
  totales_grupo_entidad <- resultados_finales_entidad |> 
    distinct(grupo_general, n_grupo) |> 
    mutate(pct_global_num = redondear_porcentajes(n_grupo, decimales = 1))
  
  resultados_finales_entidad <- resultados_finales_entidad |> 
    left_join(totales_grupo_entidad |> select(grupo_general, pct_global_num), by = "grupo_general") |> 
    select(grupo_general, dependencia_origen, n, pct_global_num, pct_interno_num) |> 
    mutate(
      pct_global = sprintf("%.1f%%", pct_global_num),
      pct_interno = sprintf("%.1f%%", pct_interno_num)
    )
  
  # ---- Datos para el tabulado ---- #
  
  # Localizados solo de fiscalías
  localizados_entidad <- comprimido_entidad |> 
    filter(clasificacion_des %in% "Localizados",
           dependencia_origen %in% c("Fiscalía con expediente genérico", 
                                     "Fiscalía con carpeta de investigación"))
  
  anio_minimo_localizados_entidad <- min(localizados_entidad$anio_hechos_modificada)
  numero_localizados_entidad <- localizados_entidad |> nrow()
  numero_localizados_entidad_2006 <- localizados_entidad |> 
    filter(anio_hechos_modificada >= 2006) |> nrow()
  
  tabla_localizados_entidad <- localizados_entidad |> 
    filter(anio_hechos_modificada >= 2006) |> 
    count(anio_hechos_modificada) |> 
    complete(anio_hechos_modificada = 2006:2026, fill = list(n = 0)) |> 
    arrange(anio_hechos_modificada)
  
  names(tabla_localizados_entidad) <- c("Año", "Localizados - fiscalías")
  
  # Tabla de clasificación por fiscalías
  tabla_clasificacion_comprimido_fiscalias <- comprimido_con_datos_sin_registro_entidad |> 
    filter(dependencia_origen %in% c("Fiscalía con expediente genérico",
                                     "Fiscalía con carpeta de investigación")) |> 
    count(anio_hechos_modificada, dependencia_origen) |> 
    filter(anio_hechos_modificada >= 2006) |> 
    complete(anio_hechos_modificada = 2006:2026, fill = list(n = 0)) |> 
    arrange(anio_hechos_modificada) |> 
    pivot_wider(names_from = dependencia_origen, values_from = n, values_fill = 0) |> 
    rename(Año = anio_hechos_modificada) |> 
    select(-any_of("NA"))
  
  # Pegar resultados de localizados
  tabla_clasificacion_comprimido_fiscalias <- tabla_clasificacion_comprimido_fiscalias |> 
    left_join(tabla_localizados_entidad, by = "Año")
  
  # Guardar tabulado
  if (guardar_tabulado) {
    fecha_actual_formato <- format(today(), "%d%m%Y")
    carpeta_tabulados <- file.path(directorio_salida, paste0("tabulados_", fecha_actual_formato))
    
    if (!dir.exists(carpeta_tabulados)) {
      dir.create(carpeta_tabulados, recursive = TRUE)
      message("Creando carpeta para tabulados: ", carpeta_tabulados)
    }
    
    writexl::write_xlsx(
      tabla_clasificacion_comprimido_fiscalias, 
      file.path(carpeta_tabulados,
                paste0("tabla_clasificacion_comprimido_fiscalias_", 
                       tolower(stri_trans_general(entidad_de_interes, "Latin-ASCII")), "_", 
                       format(as.Date(fecha_actual_formato, "%d%m%Y"), "%Y-%m-%d"), ".xlsx"))
    )
  }
  
  # --------------------------------------------------------- #
  # Generación del PPT -----
  # --------------------------------------------------------- #
  
  contador <- 0
  fecha_actual <- today()
  
  # Leer template
  presentacion <- read_pptx(here::here("RNPDNO", "docs", 
                                       "layout_por_entidad_federativa_arbol_y_fiscalias.pptx"))
  
  # ---- Slide 1: Portada ---- #
  contador <- contador + 1
  
  presentacion <- add_slide(presentacion, layout = "portada", master = "master") |>
    ph_with(value = entidad_de_interes, location = ph_location_label("entidad")) |>
    ph_with(value = format(fecha_actual, "%d de %B de %Y"), 
            location = ph_location_label("fecha")) |>
    ph_with(value = "Personas desaparecidas", 
            location = ph_location_label("personas_desaparecidas")) |> 
    ph_with(value = as.character(contador), location = ph_location_label("contador_1"))
  
  # ---- Slide 2: Árbol ---- #
  contador <- contador + 1
  
  titulo_1 <- fpar(
    ftext("Registro Nacional de Personas Desaparecidas y No Localizadas |1952 a 2026 | ", 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = TRUE)),
    ftext(entidad_de_interes, 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = FALSE))
  )
  
  fuente <- fpar(
    ftext("Fuente: ", fp_text(font.size = 8, color = "#434343", 
                              font.family = "Noto Sans", bold = TRUE)),
    ftext("RNPDNO al ", fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(format(fecha_actual, "%d de %B de %Y"), 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(" y la Base Nacional de Carpetas de Investigación, a partir de que entró en vigor la reforma a la ley en materia de desaparición de personas, con datos al ", 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(format(fecha_banci, "%d de %B de %Y"), 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(".", fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans"))
  )
  
  larga_data <- comma(numero_desaparecidos_totales_entidad - numero_desaparecidos_corte_entidad)
  
  presentacion <- add_slide(presentacion, layout = "slide_1", master = "master") |>
    ph_with(value = fuente, location = ph_location_label("fuente")) |> 
    ph_with(value = comma(numero_con_datos_con_registro_admin_entidad),
            location = ph_location_label("num_con_actividades")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_numero_con_datos_con_registro_admin_entidad),
            location = ph_location_label("porcen_con_actividades")) |> 
    ph_with(value = comma(numero_con_datos_sin_registro_consolidado_entidad),
            location = ph_location_label("num_sin_indicios")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_numero_con_datos_sin_registro_admin_entidad),
            location = ph_location_label("porcen_sin_indicios")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_localizados_con_delito_entidad),
            location = ph_location_label("porcen_con_delito")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_localizados_sin_delito_entidad),
            location = ph_location_label("porcen_sin_delito")) |> 
    ph_with(value = comma(localizados_con_delito_entidad),
            location = ph_location_label("num_con_delito")) |> 
    ph_with(value = comma(localizados_sin_delito_entidad),
            location = ph_location_label("num_sin_delito")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_localizados_con_vida_entidad),
            location = ph_location_label("porcen_con_vida")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_localizados_sin_vida_entidad),
            location = ph_location_label("porcen_sin_vida")) |> 
    ph_with(value = comma(numero_localizados_con_vida_entidad),
            location = ph_location_label("num_con_vida")) |> 
    ph_with(value = comma(numero_localizados_sin_vida_entidad),
            location = ph_location_label("num_sin_vida")) |> 
    ph_with(value = sprintf("%.0f%%", porcentaje_loc_entidad),
            location = ph_location_label("porcen_localizados")) |> 
    ph_with(value = comma(numero_localizados_totales_entidad),
            location = ph_location_label("num_localizados")) |> 
    ph_with(value = comma(dato_municipios_entidad),
            location = ph_location_label("municipio")) |> 
    ph_with(value = comma(dato_fecha_nacimiento_entidad),
            location = ph_location_label("fecha_nacimiento")) |> 
    ph_with(value = comma(dato_fecha_desaparicion_entidad),
            location = ph_location_label("fecha_desaparicion")) |> 
    ph_with(value = comma(dato_nombre_entidad),
            location = ph_location_label("nombre")) |> 
    ph_with(value = comma(dato_sexo_entidad),
            location = ph_location_label("sexo")) |> 
    ph_with(value = comma(numero_sin_datos_entidad),
            location = ph_location_label("curp")) |> 
    ph_with(value = comma(numero_sin_datos_entidad),
            location = ph_location_label("num_sin_datos")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_sin_datos_entidad),
            location = ph_location_label("porcen_sin_datos")) |> 
    ph_with(value = comma(numero_desaparecidos_corte_entidad),
            location = ph_location_label("desaparecidos_2006")) |> 
    ph_with(value = comma(numero_desaparecidos_totales_entidad),
            location = ph_location_label("desaparecidos")) |> 
    ph_with(value = sprintf("%.0f%%", porcentaje_des_entidad),
            location = ph_location_label("porcen_desaparecidos")) |> 
    ph_with(value = sprintf("%.0f%%", porcen_con_datos_entidad),
            location = ph_location_label("porcen_con_datos")) |> 
    ph_with(value = comma(numero_con_datos_entidad),
            location = ph_location_label("num_con_datos")) |> 
    ph_with(value = comma(registros_entidad),
            location = ph_location_label("total_registros")) |> 
    ph_with(value = titulo_1, location = ph_location_label("titulo")) |> 
    ph_with(value = as.character(contador), location = ph_location_label("contador_2")) |> 
    ph_with(value = larga_data, location = ph_location_label("larga_data"))
  
  # ---- Slide 3: Fiscalías ---- #
  contador <- contador + 1
  
  titulo_2 <- fpar(
    ftext("Registros con datos que no tienen coincidencias con registros administrativos | ", 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = TRUE)),
    ftext(entidad_de_interes, 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = FALSE))
  )
  
  fuente_2 <- fpar(
    ftext("Fuente: ", fp_text(font.size = 8, color = "#434343", 
                              font.family = "Noto Sans", bold = TRUE)),
    ftext("RNPDNO al ", fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(format(fecha_actual, "%d de %B de %Y"), 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(" y SESNSP de agosto al ", 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(format(fecha_banci, "%d de %B de %Y"), 
          fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans")),
    ftext(".", fp_text(font.size = 8, color = "#434343", font.family = "Noto Sans"))
  )
  
  # Extraer datos de dependencias
  porcen_portal <- resultados_finales_entidad |> pull(pct_global) |> _[5]
  porcen_comision_local <- resultados_finales_entidad |> pull(pct_interno) |> _[2]
  porcen_comision_nacional <- resultados_finales_entidad |> pull(pct_interno) |> _[1]
  porcen_comision_total <- resultados_finales_entidad |> pull(pct_global) |> _[1]
  porcen_reportes <- resultados_finales_entidad |> pull(pct_interno) |> _[4]
  porcen_carpetas <- resultados_finales_entidad |> pull(pct_interno) |> _[3]
  porcen_fiscalia <- resultados_finales_entidad |> pull(pct_global) |> _[3]
  
  num_portal <- resultados_finales_entidad |> pull(n) |> _[5]
  num_comision_local <- resultados_finales_entidad |> pull(n) |> _[2]
  num_comision_nacional <- resultados_finales_entidad |> pull(n) |> _[1]
  num_comision_total <- num_comision_local + num_comision_nacional
  num_reportes <- resultados_finales_entidad |> pull(n) |> _[4]
  num_carpetas <- resultados_finales_entidad |> pull(n) |> _[3]
  num_fiscalia <- num_reportes + num_carpetas
  
  presentacion <- add_slide(presentacion, layout = "slide_2", master = "master") |>
    ph_with(value = fuente_2, location = ph_location_label("fuente")) |> 
    ph_with(value = titulo_2, location = ph_location_label("titulo")) |> 
    ph_with(value = porcen_portal, location = ph_location_label("porcen_portal")) |> 
    ph_with(value = porcen_comision_local, location = ph_location_label("porcen_comision_local")) |> 
    ph_with(value = porcen_comision_nacional, location = ph_location_label("porcen_comision_nacional")) |> 
    ph_with(value = porcen_comision_total, location = ph_location_label("porcen_comision_total")) |> 
    ph_with(value = porcen_reportes, location = ph_location_label("porcen_reportes")) |> 
    ph_with(value = porcen_fiscalia, location = ph_location_label("porcen_fiscalia")) |> 
    ph_with(value = porcen_carpetas, location = ph_location_label("porcen_carpetas")) |> 
    ph_with(value = comma(numero_con_datos_sin_registro_consolidado_entidad),
            location = ph_location_label("num_sin_indicios")) |> 
    ph_with(value = sprintf("%.1f%%", porcen_numero_con_datos_sin_registro_admin_entidad_1d),
            location = ph_location_label("porcen_sin_indicios")) |> 
    ph_with(value = comma(num_portal), location = ph_location_label("num_portal")) |> 
    ph_with(value = comma(num_comision_local), location = ph_location_label("num_comision_local")) |> 
    ph_with(value = comma(num_comision_nacional), location = ph_location_label("num_comision_nacional")) |> 
    ph_with(value = comma(num_comision_total), location = ph_location_label("num_comision_total")) |> 
    ph_with(value = comma(num_reportes), location = ph_location_label("num_reportes")) |> 
    ph_with(value = comma(num_carpetas), location = ph_location_label("num_carpetas")) |> 
    ph_with(value = comma(num_fiscalia), location = ph_location_label("num_fiscalia")) |> 
    ph_with(value = as.character(contador), location = ph_location_label("contador_3"))
  
  # ---- Slide 4: Gráfica ---- #
  contador <- contador + 1
  
  num_ultimo_anio_carpeta <- tabla_clasificacion_comprimido_fiscalias |> 
    pull(`Fiscalía con carpeta de investigación`) |> _[20]
  num_ultimo_anio_reporte <- tabla_clasificacion_comprimido_fiscalias |> 
    pull(`Fiscalía con expediente genérico`) |> _[20]
  num_ultimo_anio_fiscalia <- num_ultimo_anio_reporte + num_ultimo_anio_carpeta
  
  titulo_3 <- fpar(
    ftext("De los ", fp_text(font.size = 17, color = "#6B1537", 
                             font.family = "Noto Sans", bold = TRUE)),
    ftext(comma(numero_con_datos_sin_registro_consolidado_entidad), 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = TRUE)),
    ftext(" registros sin indicios ", fp_text(font.size = 17, color = "#6B1537", 
                                               font.family = "Noto Sans", bold = TRUE)),
    ftext(comma(num_fiscalia), fp_text(font.size = 17, color = "#6B1537", 
                                       font.family = "Noto Sans", bold = TRUE)),
    ftext(" corresponden a reportes realizados por fiscalías | ", 
          fp_text(font.size = 17, color = "#6B1537", font.family = "Noto Sans", bold = TRUE)),
    ftext(entidad_de_interes, fp_text(font.size = 17, color = "#6B1537", 
                                      font.family = "Noto Sans", bold = FALSE))
  )

    # Si no hubo carpetas de investigación en el último año, todos los casos de
    # fiscalías de ese año son reportes -> cambia el texto en vez de decir
    # "de los cuales 0 corresponden a carpetas de investigación"
    if (num_ultimo_anio_carpeta == 0) {
     descripcion_3 <- fpar(
      ftext(paste0(comma(num_ultimo_anio_fiscalia), " "), 
            fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE)),
      ftext("casos de fiscalías en ", fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans")),
      ftext(format(fecha_corte, "%Y"), fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE)),
      ftext(", los cuales en su totalidad corresponden a reportes.", 
            fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE))
    )
   } else {
     descripcion_3 <- fpar(
      ftext(paste0(comma(num_ultimo_anio_fiscalia), " "), 
            fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE)),
      ftext("casos de fiscalías en ", fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans")),
      ftext(format(fecha_corte, "%Y"), fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE)),
      ftext(", de los cuales ", fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans")),
      ftext(paste0(comma(num_ultimo_anio_carpeta), " "), fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE)),
      ftext("corresponden a ", fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = FALSE)),
      ftext("carpetas de investigación.", fp_text(font.size = 12, color = "#595959", font.family = "Noto Sans", bold = TRUE))
    )
   }

  presentacion <- add_slide(presentacion, layout = "slide_3", master = "master") |>
    ph_with(value = fuente_2, location = ph_location_label("fuente")) |> 
    ph_with(value = titulo_3, location = ph_location_label("titulo")) |> 
    ph_with(value = comma(numero_localizados_entidad_2006),
            location = ph_location_label("localizados_2006")) |> 
    ph_with(value = paste0("(", comma(numero_localizados_entidad), " desde"),
            location = ph_location_label("localizados_historicos")) |> 
    ph_with(value = paste0(anio_minimo_localizados_entidad, ")"),
            location = ph_location_label("anio_localizados_historicos")) |> 
    ph_with(value = comma(num_fiscalia), location = ph_location_label("num_fiscalia")) |> 
    ph_with(value = as.character(contador), location = ph_location_label("contador_4")) |> 
    ph_with(value = descripcion_3, location = ph_location_label("descripcion")) |> 
    ph_with(value = comma(num_ultimo_anio_carpeta), location = ph_location_label("num_carpetas")) |> 
    ph_with(value = comma(num_ultimo_anio_reporte), location = ph_location_label("num_expedientes"))
  
  # ---- Guardar PPT ---- #
        
  # Creamos carpeta "paste0("actualizacion_", format(Sys.Date(), "%d%m%Y"))" si no existe
  if(!dir.exists(file.path(directorio_salida, paste0("actualizacion_", format(Sys.Date(), "%d%m%Y"))))) {
    dir.create(file.path(directorio_salida, paste0("actualizacion_", format(Sys.Date(), "%d%m%Y"))), recursive = TRUE)
    message("Creando carpeta para PPT: ", file.path(directorio_salida, paste0("actualizacion_", format(Sys.Date(), "%d%m%Y"))))
  } else {
        message("La carpeta para PPT ya existe: ", file.path(directorio_salida, paste0("actualizacion_", format(Sys.Date(), "%d%m%Y"))))
  }  
        
  archivo_salida <- file.path(
    directorio_salida,
    paste0("actualizacion_", format(Sys.Date(), "%d%m%Y")),
    paste0("personas_desaparecidas_", entidad_de_interes, "_", 
           format(Sys.Date(), "%d%m%Y"), ".pptx")
  )
  
  print(presentacion, target = archivo_salida)
  
  message("✓ PPT generada exitosamente: ", archivo_salida, " de la entidad: ", entidad_de_interes)
  
  # Retornar resultados útiles
  invisible(list(
    presentacion = presentacion,
    archivo_salida = archivo_salida,
    tabla_clasificacion = tabla_clasificacion_comprimido_fiscalias,
    resultados_dependencias = resultados_finales_entidad
  ))
}

# ————————————————————————————————————————————————————————— #
# Generar PPTx para Secretariado -------
# ————————————————————————————————————————————————————————— #

# Para cada entidad de estado_desaparicion de comprimido, generar la PPT
entidades_en_comprimido <- unique(comprimido$estado_desaparicion)

for(i in seq_along(entidades_en_comprimido)) {
  entidad_actual <- entidades_en_comprimido[i]
  message("Generando PPT para la entidad: ", entidad_actual)
  
  generar_ppt_entidad(
    comprimido = comprimido,
    entidad_de_interes = entidad_actual,
    fecha_banci = fecha_banci,
    guardar_tabulado = TRUE
  )
}

# Generar PPT para una entidad
generar_ppt_entidad(
    comprimido = comprimido,
    entidad_de_interes = "Zacatecas",
    fecha_banci = fecha_banci,
    guardar_tabulado = TRUE
  )

