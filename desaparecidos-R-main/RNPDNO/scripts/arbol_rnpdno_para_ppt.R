# ————————————————————————————————————————————————————————— #
# Nombre: Jocelyn Rocha
# Contacto: jocelyn.flores@transformaciondigital.gob.mx
# Script: arbol_rnpdno_para_ppt.R
# Proyecto: Personas Desaparecidas
# Fecha: 2026-07-09
# Propósito: Generar reporte de árbol de personas desaparecidas con diferentes cortes temporales. El output es una PPT.
# ————————————————————————————————————————————————————————— #
# Funciones ------
# ————————————————————————————————————————————————————————— #

# Funciones de gestión del RNPDNO
# ---- Función de actualización y procesamiento de variables ---- #
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_actualizar_rnpdno_y_procesar_variables.R"))

# ------ Función para generar comprimido con intersección entre RNPDNO y BANCI ---- #

## ----- No se contempla lo que solo está en BANCI ------ ##
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_banci_rnpdno_matching_completo.R"))

# ----- Función de actualización de información de confrontas de la PUI ----- #
source(here::here("RNPDNO", "scripts", "funciones",
       "funcion_actualizar_confrontas_de_pui.R"))


# ————————————————————————————————————————————————————————— #
# Bases de datos ------
# ————————————————————————————————————————————————————————— #

# ---- Actualizar RNPDNO ----- #
# Definimos la fecha de corte para la actualización del reporte semanal
fecha_corte <- today()

comprimido <- actualizar_rnpdno_y_procesar(
  fecha_corte = fecha_corte,
  registros = registros,
  catalogo_estados_inegi = catalogo_estados_inegi,
  catalogo_municipios_inegi = catalogo_municipios_inegi,
  descargar = TRUE
)

# Ruta de archivos de Secretariado originales
subeR <- readxl::read_excel(here("RNPDNO",
                        "input",
                        "datos_de_fiscalias",
                        "datos_originales",
                        "SUBIR_R_202610_octubre.xlsx"), 
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
  fecha_fin_BANCI = "2026-10-31",
  tipo_conjunto = "interseccion",
  guardar_bases_matching = FALSE,
  Base_BANCI_con_match_con_RNPDNO = Base_BANCI_con_match_con_RNPDNO,
  Base_BANCI_sin_match_con_RNPDNO = Base_BANCI_sin_match_con_RNPDNO,
  registros_localizados = registros_localizados
)

# ----- Coincidencias administrativas de la PUI con desapariciones inactivas ---- #
ruta_pui <- here::here("RNPDNO", "input",
                       "datos_procesados_de_la_pui",
                       "noviembre_2026",
                       "actualizacion_20112026",
                       "reporte_coincidencias_validas_2026-11-20.csv")

# Extrae automáticamente la fecha del nombre del folder "actualizacion_DDMMYYYY"
fecha_actualizacion <- ruta_pui |>
  str_extract(r"((?<=actualizacion_)\d{8})") |>
  as.Date(format = "%d%m%Y")

coincidencias_admin_con_inactivas <- read_csv(
  ruta_pui,
  locale = locale(encoding = "UTF-8")
) |> clean_names()

message("Se lee el archivo con fecha de actualización al ", format(fecha_actualizacion, "%d de %B de %Y"))

# ----- Defunciones ------ #
defunciones_df <- openxlsx::read.xlsx(here::here("Confrontas",
             "output",
             "resumen_todas_confrontas_historicas",
             "resultados_05052026",
             "tabla_defunciones_por_institucion_05052026.xlsx"))

# ----- Actualizar confrontas de PUI ----- #
resultados <- actualizar_confrontas_de_pui(
  registros = registros,
  defunciones_df = defunciones_df,
  comprimido = comprimido,
  coincidencias_admin_con_inactivas = NULL,
  guardar_registros_con_pui = TRUE
)

# Extraer comprimido y registros_con_pui
comprimido <- resultados[["comprimido_actualizado"]]
registros_con_pui_activos <- resultados[["registros_con_pui_activos"]]
registros_en_pui_no_activos <- resultados[["registros_en_pui_no_activos"]]

# Limpiar objetos intermedios
objetos_a_eliminar <- c("resultados", "coincidencias_admin_con_inactivas")
rm(list = intersect(objetos_a_eliminar, ls()))
gc()

# Actualización de matches_consolidados

matches_consolidados <- readxl::read_excel(
  here::here("RNPDNO", "output", "cruces_banci_rnpdno", "cruces_banci_rnpdno_18082026", "matches_consolidados_unicos_en_fub_sexenio_subeR_julio_18082026.xlsx")
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
# 3,651

# ————————————————————————————————————————————————————————— #
# Función de creación de árbol RNPDNO ------
# ————————————————————————————————————————————————————————— #

generacion_arbol_rnpdno <- function(data,
                                    subeR,
                                    fecha_actual,
                                    fecha_inicio = NULL, 
                                    fecha_fin = NULL,
                                    anio_inicio = NULL,
                                    anio_fin = NULL,
                                    directorio_salida = NULL) {
  
  ## Aplicar filtros temporales si se especifican
  data_filtrada <- data
  
  if (!is.null(fecha_inicio)) {
    data_filtrada <- data_filtrada |> 
      filter(fecha_hechos_modificada >= as.Date(fecha_inicio))
  }
  
  if (!is.null(fecha_fin)) {
    data_filtrada <- data_filtrada |> 
      filter(fecha_hechos_modificada <= as.Date(fecha_fin))
  }
  
  if (!is.null(anio_inicio)) {
    data_filtrada <- data_filtrada |> 
      filter(anio_hechos_modificada >= anio_inicio)
  }
  
  if (!is.null(anio_fin)) {
    data_filtrada <- data_filtrada |> 
      filter(anio_hechos_modificada <= anio_fin)
  }

  # Configurar directorio de salida por defecto
  if (is.null(directorio_salida)) {
    directorio_salida <- here::here("RNPDNO", "output", "PPT", "PPT_arbol_datos_mañanera")
  }
  
  # Total registros
  num_total_registros <- nrow(data_filtrada)
  
  ## ----- LOCALIZADOS ----- ##
  localizados_totales <- data_filtrada |> 
    filter(clasificacion_des == "Localizados")
  
  num_localizados <- nrow(localizados_totales)
  porcen_localizados <- if (num_total_registros > 0) {
    round((num_localizados * 100) / num_total_registros, 0)
  } else 0
  
  num_localizados_con_vida <- data_filtrada |> 
    filter(clasificacion_des == "Localizados",
           estatus == "LOCALIZADA CON VIDA") |> 
    nrow()
  
  porcen_localizados_con_vida <- if (num_localizados > 0) {
    round((num_localizados_con_vida * 100) / num_localizados, 0)
  } else 0
  
  num_localizados_sin_vida <- data_filtrada |> 
    filter(clasificacion_des == "Localizados",
           estatus == "LOCALIZADA SIN VIDA") |> 
    nrow()
  
  porcen_localizados_sin_vida <- if (num_localizados > 0) {
    round((num_localizados_sin_vida * 100) / num_localizados, 0)
  } else 0
  
  num_localizados_con_delito <- localizados_totales |>
    filter(!is.na(delitolocalizacion) & delitolocalizacion != "") |> 
    nrow()
  
  porcen_localizados_con_delito <- if (num_localizados > 0) {
    round((num_localizados_con_delito * 100) / num_localizados, 0)
  } else 0
  
  num_localizados_sin_delito <- localizados_totales |>
    filter(is.na(delitolocalizacion) | delitolocalizacion == "") |> 
    nrow()
  
  porcen_localizados_sin_delito <- if (num_localizados > 0) {
    round((num_localizados_sin_delito * 100) / num_localizados, 0)
  } else 0
  
  ## ----- DESAPARECIDOS ----- ##
  num_desaparecidos_con_historico <- data_filtrada |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes")) |> 
    nrow()
  
  porcen_desaparecidos_con_historico <- if (num_total_registros > 0) {
    round((num_desaparecidos_con_historico * 100) / num_total_registros, 0)
  } else 0
  
  num_desaparecidos_desde_2006 <- data_filtrada |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
           anio_hechos_modificada >= 2006) |> 
    nrow()
  
  num_larga_data <- num_desaparecidos_con_historico - num_desaparecidos_desde_2006
  
  num_datos_insuficientes <- data_filtrada |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
           anio_hechos_modificada >= 2006,
           sub_clasificacion == "Sin datos") |> 
    nrow()
  
  porcen_datos_insuficientes <- if (num_desaparecidos_desde_2006 > 0) {
    round((num_datos_insuficientes * 100) / num_desaparecidos_desde_2006, 0)
  } else 0
  
  num_con_registro_admin <- data_filtrada |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
           anio_hechos_modificada >= 2006,
           sub_clasificacion == "Desaparecido con registro administrativo") |> 
    nrow()
  
  porcen_con_registro_admin <- if (num_desaparecidos_desde_2006 > 0) {
    round((num_con_registro_admin * 100) / num_desaparecidos_desde_2006, 0)
  } else 0
  
  num_sin_actividad <- data_filtrada |> 
    filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
           anio_hechos_modificada >= 2006,
           sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo") |> 
    nrow()
  
  porcen_sin_actividad <- if (num_desaparecidos_desde_2006 > 0) {
    round((num_sin_actividad * 100) / num_desaparecidos_desde_2006, 0)
  } else 0
  
  # ————————————————————————————————————————————————————————— #
  # Generar slide con los resultados ------
  # ————————————————————————————————————————————————————————— #

  # Preparamos contador de página 
  contador = 0

  contador = contador + 1

  # SLIDE PORTADA ----- #

  # Creamos 'fecha actual'
  # Recuperamos la fecha de descarga del RNPDNO
  fecha_actual <- as.Date(fecha_corte)

  # Leemos
  presentacion = read_pptx(here::here("RNPDNO",
                                    "docs",
                                    "layout_reporte_semanal_con_avances.pptx"))

  # Portada
  presentacion <- add_slide(presentacion, layout = "portada_reporte", master = "master") |>
  ph_with(value = "Reportes de personas desaparecidas en RNPDNO", location = ph_location_label("titulo")) |> # título
  ph_with(value = format(fecha_actual, "%B %Y"), location = ph_location_label("fecha")) |> # fecha
  ph_with(value = as.character(contador),location = ph_location_label("contador_1")) #Número de diapositiva
  
  titulo_1 <- fpar(
    ftext("Registro Nacional de Personas Desaparecidas y No Localizadas de ", 
          fp_text(font.size = 17, color = "#6B1537",
                  font.family = "Noto Sans", bold = TRUE)),
    ftext("1952 a 2026", 
          fp_text(font.size = 17, color = "#6B1537",
                  font.family = "Noto Sans", bold = FALSE))
  )

  # SLIDE ÁRBOL ----- #

  # Identificar mes de la primera y última fecha del RNPDNO
  fecha_rnpdno_inicio <- min(data_filtrada$fecha_hechos_modificada, na.rm = TRUE)
  fecha_rnpdno_fin <- max(data_filtrada$fechacaptura, na.rm = TRUE)

  fecha_rnpdno_inicio <- format(fecha_rnpdno_inicio, "%d de %B de %Y")
  fecha_rnpdno_fin <- format(fecha_rnpdno_fin, "%d de %B de %Y")


  # Identificar mes de la última fecha de la BANCI
  fecha_banci <- max(subeR$fha_de_hchos, na.rm = TRUE)
  fecha_banci_ultimo_dia_mes <- ceiling_date(fecha_banci, "month") - days(1)
  fecha_banci_ultimo_dia_mes <- format(fecha_banci_ultimo_dia_mes, "%d de %B de %Y")

  # Fuente
  fuente <- fpar(
    ftext("Fuente: ", fp_text(font.size = 8, color = "#434343",
                              font.family = "Noto Sans", bold = TRUE)),
    ftext("RNPDNO al ", fp_text(font.size = 8,  color = "#434343",
                                 font.family = "Noto Sans")),
    ftext(format(fecha_actual, "%d de %B de %Y"), 
          fp_text(font.size = 8,  color = "#434343",
                  font.family = "Noto Sans")),
    ftext(" y la Base Nacional de Carpetas de Investigación, a partir de que entró en vigor la reforma a la ley en materia de desaparición de personas, con datos al ", 
          fp_text(font.size = 8,  color = "#434343",
                  font.family = "Noto Sans")),
    ftext(fecha_banci_ultimo_dia_mes, 
          fp_text(font.size = 8,  color = "#434343",
                  font.family = "Noto Sans")),
    ftext(".", fp_text(font.size = 8,  color = "#434343",
                       font.family = "Noto Sans"))
  )

  # Incrementar contador
  contador <- contador + 1

  # Datos para slide
  presentacion <- add_slide(presentacion, layout = "arbol_reporte", master = "master") |>
    ph_with(value = fuente, location = ph_location_label("fuente")) |>
    ph_with(value = comma(num_total_registros), 
            location = ph_location_label("total_registros")) |>
    ph_with(value = comma(num_localizados), 
            location = ph_location_label("num_localizados")) |>
    ph_with(value = paste0(porcen_localizados, "%"), 
            location = ph_location_label("porcen_localizados")) |>
    ph_with(value = comma(num_localizados_con_vida), 
            location = ph_location_label("num_con_vida")) |>
    ph_with(value = paste0(porcen_localizados_con_vida, "%"), 
            location = ph_location_label("porcen_con_vida")) |>
    ph_with(value = comma(num_localizados_sin_vida), 
            location = ph_location_label("num_sin_vida")) |>
    ph_with(value = paste0(porcen_localizados_sin_vida, "%"), 
            location = ph_location_label("porcen_sin_vida")) |>
    ph_with(value = comma(num_localizados_con_delito), 
            location = ph_location_label("num_con_delito")) |>
    ph_with(value = paste0(porcen_localizados_con_delito, "%"), 
            location = ph_location_label("porcen_con_delito")) |>
    ph_with(value = comma(num_localizados_sin_delito), 
            location = ph_location_label("num_sin_delito")) |>
    ph_with(value = paste0(porcen_localizados_sin_delito, "%"), 
            location = ph_location_label("porcen_sin_delito")) |>
    ph_with(value = comma(num_desaparecidos_con_historico), 
            location = ph_location_label("num_desaparecidos_con_historico")) |>
    ph_with(value = paste0(porcen_desaparecidos_con_historico, "%"), 
            location = ph_location_label("porcen_desaparecidos_con_historico")) |>
    ph_with(value = comma(num_desaparecidos_desde_2006), 
            location = ph_location_label("num_desaparecidos_desde_2006")) |>
    ph_with(value = comma(num_larga_data), 
            location = ph_location_label("larga_data")) |>
    ph_with(value = comma(num_datos_insuficientes), 
            location = ph_location_label("num_datos_insuficientes")) |>
    ph_with(value = paste0(porcen_datos_insuficientes, "%"), 
            location = ph_location_label("porcen_datos_insuficientes")) |>
    ph_with(value = comma(num_con_registro_admin), 
            location = ph_location_label("num_con_registros")) |>
    ph_with(value = paste0(porcen_con_registro_admin, "%"), 
            location = ph_location_label("porcen_con_registros")) |>
    ph_with(value = comma(num_sin_actividad), 
            location = ph_location_label("num_sin_actividad")) |>
    ph_with(value = paste0(porcen_sin_actividad, "%"), 
            location = ph_location_label("porcen_sin_actividad")) |>
    ph_with(value = titulo_1, location = ph_location_label("titulo")) |>
    ph_with(value = as.character(contador), 
            location = ph_location_label("contador"))
  
  # ---- Guardar PPT ---- #
  
  # Crear carpeta si no existe
  carpeta_salida <- file.path(directorio_salida, 
                              paste0("actualizacion_", format(Sys.Date(), "%d%m%Y")))
  
  if (!dir.exists(carpeta_salida)) {
    dir.create(carpeta_salida, recursive = TRUE)
    message("Creando carpeta para PPT: ", carpeta_salida)
  } else {
    message("La carpeta para PPT ya existe: ", carpeta_salida)
  }  
  
  archivo_salida <- file.path(
    carpeta_salida,
    paste0("arbol_rnpdno_para_ppt_", 
           format(Sys.Date(), "%d%m%Y"), ".pptx")
  )
  
  print(presentacion, target = archivo_salida)
  
  # Rango de fechas para mensaje
  rango_fechas <- paste(
    format(min(data_filtrada$fecha_hechos_modificada, na.rm = TRUE), "%d/%m/%Y"),
    "al",
    format(max(data_filtrada$fechacaptura, na.rm = TRUE), "%d/%m/%Y")
  )
  
  message("✓ PPT generada exitosamente: ", archivo_salida, 
          "\n  Árbol del RNPDNO con corte temporal: ", rango_fechas)
  
  # Retornar resultados útiles
  invisible(list(
    presentacion = presentacion,
    contador = contador,
    archivo_salida = archivo_salida,
    num_registros_procesados = num_total_registros
  ))
}

# ————————————————————————————————————————————————————————— #
# Generación de presentación PPT -----
# ————————————————————————————————————————————————————————— #

generacion_arbol_rnpdno(
  data = comprimido,
  subeR = subeR,
  fecha_actual = fecha_corte,
  fecha_inicio = NULL,
  fecha_fin = NULL,
  anio_inicio = NULL,
  anio_fin = NULL,
  directorio_salida = here::here("RNPDNO", "output", "PPT", "PPT_arbol_datos_mañanera")
)



# Dato de la PUI para actualizar los 6,939

localizados_con_indicios <- comprimido |>
  filter(indicadora_indicio_de_vida_localizados == "con registro administrativo") |> 
  filter(clasificacion_des == "Localizados") |>
nrow()


write_parquet(comprimido, "output/Comprimido/comprimido_23112026.parquet")


write_parquet(registros_con_pui_activos, "output/Comprimido/registros_con_pui_activos_20112026.parquet")

write_parquet(registros, "output/Comprimido/registros_20112026.parquet")



