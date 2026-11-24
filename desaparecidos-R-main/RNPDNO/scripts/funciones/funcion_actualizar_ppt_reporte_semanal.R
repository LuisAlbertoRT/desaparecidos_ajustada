# --------------------------------------------------------- #
# Nombre: Jocelyn Rocha
# Contacto: maricelaymiel@gmail.com
# Script: funcion_actualizar_ppt_reporte_semanal.R
# Proyecto: Personas desaparecidas
# Fecha: 2026-06-12
# Propósito: Función de creación de variables para PPT de reporte semanal interno.
# --------------------------------------------------------- #
# Librerías ----------
# --------------------------------------------------------- #

pacman::p_load(
  readr, tidyverse, dplyr, lubridate, readxl,
  scales, magrittr, stringi, tsibble, svglite,
  here, janitor, officer, reticulate, purrr,
  glue, cli,

  # Para PPTx
  officer # se utiliza para crear y manipular documentos de PowerPoint y Microsoft Word directamente desde R.
)

# --------------------------------------------------------- #
# Funciones auxiliares ------
# --------------------------------------------------------- #

source(here::here("RNPDNO", "scripts", "funcion_actualizar_confrontas_de_pui.R"))

limpiar_rdatas_antiguos <- function(directorio, max_archivos = 2) {
  archivos <- list.files(
    path = directorio,
    pattern = "^defunciones_.*\\.RData$",
    full.names = TRUE
  )
  
  if (length(archivos) > max_archivos) {
    # Extraer fechas con error handling
    nombres <- basename(archivos)
    fechas <- suppressWarnings(
      as.Date(
        gsub("defunciones_|.RData", "", nombres),
        format = "%d_%m_%Y"
      )
    )
    
    # Verificar que se extrajeron correctamente
    if (anyNA(fechas)) {
      warning("Algunos archivos tienen formato de fecha incorrecto")
      return(invisible(NULL))
    }
    
    # Ordenar y eliminar
    idx_ordenado <- order(fechas, decreasing = TRUE)
    archivos_eliminar <- archivos[idx_ordenado][(max_archivos + 1):length(archivos)]
    
    invisible(sapply(archivos_eliminar, function(x) {
      file.remove(x)
      message("✓ Eliminado:", basename(x), "\n")
    }))
  }
}

#------------------------------------------------------- #
# Función que depdende de si se cuentan con nuevos datos de la PUI -----
# --------------------------------------------------------- #

calcular_variables_reporte <- function(estatus_actualizacion,
                                       con_corte_semanal = FALSE,
                                       registros,
                                       defunciones_df,
                                       comprimido,
                                       coincidencias_admin_con_inactivas = NULL,
                                       fecha_actualizacion_pui = NULL,
                                       guardar_registros_con_pui = FALSE,
                                       fecha_corte = NULL
                                    ) {
  
  # ------ Mensajes iniciales ------
  message("Iniciando cálculo de variables de reporte...")
  message("Fecha de actualización PUI: ", fecha_actualizacion_pui)
  if(!is.null(fecha_corte)) {
    message("Fecha de corte: ", fecha_corte)
  }
  
  # Para cada valor de conteo con su respectiva institución indicadora de vida realicemos, con map, una variable que tenga el conteo de cada institucion, que empiecen todas con "num_" seguido del nombre de la institución_split
  function_creacion_variables_conteo <- function(diccionario_instituciones_indicadoras_de_vida) {
  
  instituciones <- diccionario_instituciones_indicadoras_de_vida$institucion_split
  conteos       <- diccionario_instituciones_indicadoras_de_vida$conteo
  
  nombres <- paste0("num_", make_clean_names(instituciones))
  
  # Devuelve lista nombrada
  setNames(as.list(conteos), nombres)
}
  # Si no se actualizan datos de PUI
  if (!estatus_actualizacion) {

    # Lanzar mensaje
    message("No se cuentan con nuevos indicios de vida en la PUI. Se actualizarán las variables de conteo para el reporte semanal sin considerar una actualización de PUI. En su lugar, se toma el archivo de PUI más reciente en disco.\n")

    # Escogemos la carpeta más reciente dentro de "datos_procesados_de_la_pui" para leer el archivo de esa carpeta
    carpeta_mas_reciente_pui <- list.dirs(
      here::here("RNPDNO", "input", "datos_procesados_de_la_pui"),
      full.names = TRUE,
      recursive = FALSE
    ) |>
      keep(~ str_detect(basename(.x), "^actualizacion_\\d{8}$")) |>
      {\(x) x[which.max(str_extract(basename(x), "\\d{8}") |> as.Date(format = "%d%m%Y"))]}()

    # Leemos el archivo de la carpeta más reciente
    coincidencias_admin_con_inactivas_mas_reciente <- read_csv(
      list.files(
        carpeta_mas_reciente_pui, 
        pattern = "coincidencias.*valid.*\\.csv$",
        full.names = TRUE,
        ignore.case = TRUE
      ),
      locale = locale(encoding = "UTF-8")
    ) |> clean_names()

    # Reutilizamos el procesamiento canónico de PUI para evitar duplicidad
    resultado_actualizacion_pui <- actualizar_confrontas_de_pui(
      registros = registros,
      defunciones_df = defunciones_df,
      comprimido = comprimido,
      coincidencias_admin_con_inactivas = coincidencias_admin_con_inactivas_mas_reciente,
      guardar_registros_con_pui = FALSE
    )

    comprimido <- resultado_actualizacion_pui$comprimido_actualizado
    registros_con_pui <- resultado_actualizacion_pui$registros_con_pui_activos
    
  # En caso de que se actualicen los indicios de vida de vida de PUI
  } else {

    if (!exists("actualizar_confrontas_de_pui", mode = "function")) {
      stop("No se encontró la función 'actualizar_confrontas_de_pui'. Cárgala antes de ejecutar 'calcular_variables_reporte'.")
    } else {
      message("Se cuentan con nuevos indicios de vida en la PUI. Se actualizarán las variables de conteo para el reporte semanal considerando la actualización de PUI.\n")
    }

    # Reutilizamos el procesamiento canónico de PUI para evitar duplicidad
    resultado_actualizacion_pui <- actualizar_confrontas_de_pui(
      registros = registros,
      defunciones_df = defunciones_df,
      comprimido = comprimido,
      coincidencias_admin_con_inactivas = coincidencias_admin_con_inactivas,
      guardar_registros_con_pui = FALSE
    )

    comprimido <- resultado_actualizacion_pui$comprimido_actualizado
    registros_con_pui <- resultado_actualizacion_pui$registros_con_pui_activos
  }

    # ------ DE AQUÍ EN ADELTANTE EL FLUJO ES COMÚN EN AMBOS CASOS (ACTUALIZACIÓN DE PUI O NO) ----- #

    # --------------------------------------------------------- #
    # Defunciones
    # --------------------------------------------------------- #

    # Cruzamos con comprimido actualizado y rescatamos solo aquellos después de 2006
    defunciones_df <- defunciones_df |>
      left_join(comprimido |> select(fub, clasificacion_des, fecha_hechos_modificada), by = "fub") |>
      filter(clasificacion_des %in% c("Desaparecidos", "Pendientes")) |>
      filter(fecha_hechos_modificada >= as.Date("2006-01-01"))

    # Siempre que numero_instituciones es NA significa que es un registro de defunción
    num_defunciones <- defunciones_df |> nrow()

    # Defunciones de RENAPO
    num_defunciones_renapo <- defunciones_df |>
      filter(tipo_defuncion_institucion == "defuncion_RENAPO") |> nrow()

    porcen_defunciones_renapo <- round((num_defunciones_renapo * 100) / num_defunciones, 1)

    # Defunciones de INE
    num_defunciones_ine <- defunciones_df |>
      filter(tipo_defuncion_institucion == "defuncion_INE") |> nrow()

    porcen_defunciones_ine <- round((num_defunciones_ine * 100) / num_defunciones, 1)

    # Defunciones de SSA
    num_defunciones_ssa <- defunciones_df |>
      filter(tipo_defuncion_institucion == "defuncion_SSA") |> nrow()

    porcen_defunciones_ssa <- 100 - porcen_defunciones_renapo - porcen_defunciones_ine
    round(porcen_defunciones_ssa, 1)

    # Asegurarnos que la suma de las defunciones por institución es igual al total de defunciones
    if (num_defunciones == (num_defunciones_renapo + num_defunciones_ine + num_defunciones_ssa)) {
      cat("¡Perfecto! La suma de las defunciones por institución coincide con el total de defunciones.\n")
    } else {
      cat("¡Atención! La suma de las defunciones por institución NO coincide con el total de defunciones. Revisa los datos para identificar la discrepancia.\n")
    }

    # Asegurarnos que el porcentaje de defunciones por institución suma 100%
    porcentaje_total_defunciones <- porcen_defunciones_renapo + porcen_defunciones_ine + porcen_defunciones_ssa
    if (round(porcentaje_total_defunciones, 1) == 100) {
      cat("¡Perfecto! El porcentaje de defunciones por institución suma 100%.\n")
    } else {
      cat("¡Atención! El porcentaje de defunciones por institución NO suma 100%. Revisa los datos para identificar la discrepancia.\n")
    }

    # --------------------------------------------------------- #
    # Variables que se mostrarán en la PPT
    # --------------------------------------------------------- #

    # registros_con_pui ya viene depurado desde actualizar_confrontas_de_pui
    registros_con_pui_activos <- registros_con_pui

    # Asegurarnos de solo mapear aquellos con fecha de desaparición después de 2006
    registros_con_pui_activos <- registros_con_pui_activos |>
      left_join(comprimido |> select(fub, fecha_hechos_modificada), by = "fub") |>
      filter(fecha_hechos_modificada >= as.Date("2006-01-01"))

    # Obtener los valores únicos de las instituciones indicadoras de vida y su conteo
    diccionario_instituciones_indicadoras_de_vida <- registros_con_pui_activos |>
      select(institucion_indicadora_de_vida) |>
      mutate(institucion_split = str_split(institucion_indicadora_de_vida, ",")) |>
      unnest(institucion_split) |>
      mutate(institucion_split = str_squish(institucion_split)) |>
      count(institucion_split) |>
      arrange(institucion_split)

    # Corrección: INAMI es lo mismo que INM, entonces hacemos ambas INAMI y sumamos los conteos
    diccionario_instituciones_indicadoras_de_vida <- diccionario_instituciones_indicadoras_de_vida |>
      mutate(institucion_split = case_when(
        institucion_split %in% c("INAMI", "INM") ~ "INAMI",
        TRUE ~ institucion_split
      )) |>
      group_by(institucion_split) |>
      summarise(conteo = sum(n), .groups = "drop") |>
      arrange(institucion_split)

    # Crear nueva condición: si se quiere el desglose por institución indicadora de vida solo de la semana corriente
    if (con_corte_semanal) {

      fecha_inicio_semana <- as.Date(fecha_actualizacion_pui) - 7
      message("Fecha inicio de semana: ", fecha_inicio_semana)

      # Semana sobre la salida ya procesada: solo indicios de vida (sin defunciones)
      coincidencias_admin_con_inactivas_semana_agrupado <- registros_con_pui_activos |>
        filter(
          !is.na(fecha_evento),
          fecha_evento >= fecha_inicio_semana,
          numero_instituciones > 0
        )

      num_indicios_de_vida_semana <- coincidencias_admin_con_inactivas_semana_agrupado |> nrow()

      diccionario_instituciones_indicadoras_de_vida_semana <- coincidencias_admin_con_inactivas_semana_agrupado |>
        select(institucion_indicadora_de_vida) |>
        mutate(institucion_split = str_split(institucion_indicadora_de_vida, ",")) |>
        unnest(institucion_split) |>
        mutate(institucion_split = str_squish(institucion_split)) |>
        count(institucion_split) |>
        arrange(institucion_split) |>
        mutate(institucion_split = case_when(
          institucion_split %in% c("INAMI", "INM") ~ "INAMI",
          TRUE ~ institucion_split
        )) |>
        group_by(institucion_split) |>
        summarise(conteo = sum(n), .groups = "drop") |>
        arrange(institucion_split)

      ## ----- RESULTADOS DE CONTEOS GENERALES ----- ##
      num_registros_admin <- nrow(registros_con_pui_activos)

      num_indicios_de_vida <- nrow(registros_con_pui_activos) - num_defunciones

      porcen_indicios_de_vida <- round((num_indicios_de_vida * 100) / num_registros_admin, 0)

      porcen_defunciones <- round((num_defunciones * 100) / num_registros_admin, 0)

      porcen_indicios_de_vida_semana <- round((num_indicios_de_vida_semana * 100) / num_indicios_de_vida, 2)

      signo_porcen_indicios_de_vida_semana <- case_when(
        porcen_indicios_de_vida_semana > 0 ~ "+",
        porcen_indicios_de_vida_semana == 0 ~ "",
        porcen_indicios_de_vida_semana < 0 ~ "-"
      )

      ## ----- DEFUNCIONES DE LA SEMANA ----- ##

      # Debemos considerar que la mayoría de las localizaciones de personas no cuentan con información de fecha de localización, por lo que se imputa la fecha de desaparición en esos casos.

      # Defunciones hasta la fecha, usamos df_defunciones_hasta_la_fecha

      archivo_defunciones <- here::here("RNPDNO", "output", "PPT", "PPT_reportes_periodicos_con_avance", "fallecimientos_historicos", paste0("defunciones_", format(fecha_actualizacion_pui, "%d_%m_%Y"), ".RData"))

      # Construir df_defunciones_hasta_la_fecha a partir de defunciones_df ya filtrado
      df_defunciones_hasta_la_fecha <- defunciones_df |>
        left_join(comprimido |> select(fub, estatus, fechalocaliza_imputada), by = "fub") |>
        select(fub, estatus, tipo_defuncion_institucion)

      # Crear nombre dinámico del objeto df_defunciones_hasta_la_fecha
      nombre_objeto <- paste0("df_defunciones_hasta_la_fecha_", format(fecha_actualizacion_pui, "%d_%m_%Y"))

      # Asignar el objeto con ese nombre
      assign(nombre_objeto, df_defunciones_hasta_la_fecha)

      # Guardar usando el nombre dinámico
      save(list = nombre_objeto, file = archivo_defunciones)
      
      # Con la función limpiar_rdatas_antiguos, limpiamos la carpeta de fallecimientos históricos para que solo queden los dos archivos más recientes (el de la semana pasada y el de esta semana)
      limpiar_rdatas_antiguos(
        directorio = dirname(archivo_defunciones),
        max_archivos = 2
      )

      # De la carpeta de "fallecimientos_historicos" buscamos el archivo con fecha a fecha_inicio_semana para obtener el número de defunciones hasta la fecha de inicio de semana, y así poder calcular el número de defunciones de la semana (defunciones hasta la fecha - defunciones hasta la fecha de inicio de semana)
      archivo_defunciones_inicio_semana <- list.files(
        path = here::here("RNPDNO", "output", "PPT", "PPT_reportes_periodicos_con_avance", "fallecimientos_historicos"),
        pattern = paste0("defunciones_.*\\.RData"),
        full.names = TRUE
      ) |> 
        keep(~ str_detect(.x, format(fecha_inicio_semana, "%d_%m_%Y")))

      # Cargamos el archivo de defunciones hasta la fecha de inicio de semana. Si no existiese hacemos un warning
      if(length(archivo_defunciones_inicio_semana) == 1) {
        load(archivo_defunciones_inicio_semana)

        #Extraer el nombre del objeto cargado (es dinámico según la fecha)
        nombre_objeto_cargado <- paste0("df_defunciones_hasta_la_fecha_", format(fecha_inicio_semana, "%d_%m_%Y"))
  
        # Renombrar a nombre fijo
        df_defunciones_hasta_la_fecha_previo <- get(nombre_objeto_cargado)
  
        # Eliminar el objeto con nombre dinámico
        rm(list = nombre_objeto_cargado)

      } else {
        stop("No se encontró un archivo de defunciones hasta la fecha de inicio de semana. No se podrá calcular el número de defunciones de la semana.")
      }

      # En este punto tenemos dos data frames: df_defunciones_hasta_la_fecha (con defunciones hasta la fecha de actualización de PUI) y df_defunciones_hasta_la_fecha_previo (con defunciones hasta la fecha de inicio de semana)

      # Sacamos nrow de ambos y restamos para obtener el número de defunciones de la semana
      num_defunciones_semana <- nrow(df_defunciones_hasta_la_fecha) - nrow(df_defunciones_hasta_la_fecha_previo)

      # Cambiamos la columna de estatus a estatus_previo de df_defunciones_hasta_la_fecha_previo
      df_defunciones_hasta_la_fecha_previo <- df_defunciones_hasta_la_fecha_previo |> 
        rename(estatus_previo = estatus)

      # Para obtener el número de defunciones localizados con y sin vida, hacemos un left_join entre df_defunciones_hasta_la_fecha_previo y comprimido (solo agarramos fub y estatus)
      df_defunciones_hasta_la_fecha_previo <- df_defunciones_hasta_la_fecha_previo |> 
        left_join(comprimido |> select(fub, estatus), by = "fub")

      # Hacemos un count de estatus (el actualizado) y hacemos un pull en cada tipo de estatus 
      conteo_estatus <- df_defunciones_hasta_la_fecha_previo |> count(estatus)

      # Los valores posibles son "DESAPARECIDA", "NO LOCALIZADA", "LOCALIZADA CON VIDA" y "LOCALIZADA SIN VIDA". Sacamos el conteo de cada uno, y si no existe alguno hacemos que su conteo sea 0
      num_desaparecida <- conteo_estatus |> filter(estatus == "DESAPARECIDA") |> pull(n)
      num_no_localizada <- conteo_estatus |> filter(estatus == "NO LOCALIZADA") |> pull(n)
      num_localizada_con_vida <- conteo_estatus |> filter(estatus == "LOCALIZADA CON VIDA") |> pull(n)
      num_localizada_sin_vida <- conteo_estatus |> filter(estatus == "LOCALIZADA SIN VIDA") |> pull(n)

      # Si alguno de ellos es integer(0) (es decir, no existe ese estatus), entonces le asignamos 0 y como "no localizada" y "desaparecida" son la misma categoría, sumamos ambas y eliminamos "num_no_localizada"
      if(length(num_desaparecida) == 0) {
        num_desaparecida <- 0
      }
      if(length(num_no_localizada) == 0) {
        num_no_localizada <- 0
      }
      if(length(num_localizada_con_vida) == 0) {
        num_localizada_con_vida <- 0
      }
      if(length(num_localizada_sin_vida) == 0) {
        num_localizada_sin_vida <- 0
      }

      num_no_localizada <- num_no_localizada + num_desaparecida
      rm(num_desaparecida)

      # ---- Preparamos conteos de todo lo concerniente a defunciones ----- #

      # Ojo es lo mismo que nrow(df_defunciones_hasta_la_fecha) es lo mismo que num_defunciones
      
      # Porcentaje de defunciones respecto a todos los indicios de vida de PUI
      # porcen_defunciones
  
      defunciones_df_localizados <- defunciones_df |>
        select(-clasificacion_des) |>
        left_join(
          comprimido |> select(fub, clasificacion_des, estatus, fechalocaliza_imputada),
          by = "fub"
        ) |>
        filter(clasificacion_des == "Localizados")

      localizaciones_defunciones_semana <- defunciones_df_localizados |>
        filter(fechalocaliza_imputada >= fecha_inicio_semana)

      num_defunciones_localizadas_semana <- localizaciones_defunciones_semana |> nrow()
      porcen_defunciones_localizadas_semana <- round((num_defunciones_localizadas_semana * 100) / num_defunciones, 2)

      # --------------------------------------------------------- #
      # Avances de registros de personas desaparecidas por clasificación -----
      # --------------------------------------------------------- #

      # Creamos un archivo histórico .csv que guardará fila a fila los siguientes datos: fecha, num_desaparecidos_con_act, num_desaparecidos_sin_act y num_desaparecidos_sin_informacion.

     # ---- 1. Personas desaparecidas con registro administrativo -----
    num_desaparecidos_con_act <- comprimido |> 
      filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
             anio_hechos_modificada >= 2006,
            sub_clasificacion == "Desaparecido con registro administrativo") |> 
      nrow()

    # ---- 2. Personas desaparecidas sin registro administrativo -----
    num_desaparecidos_sin_act <- comprimido |> 
      filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
             anio_hechos_modificada >= 2006,
            sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo") |> 
      nrow()

    # ---- 3. Personas desaparecidas sin información -----
    num_desaparecidos_sin_informacion <- comprimido |> 
      filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
             anio_hechos_modificada >= 2006,
            sub_clasificacion == "Sin datos") |> 
      nrow()

    # Preparar nueva fila
    nueva_fila <- tibble(
      fecha = as.Date(fecha_actualizacion_pui),
      num_desaparecidos_con_act = num_desaparecidos_con_act,
      num_desaparecidos_sin_act = num_desaparecidos_sin_act,
      num_desaparecidos_sin_informacion = num_desaparecidos_sin_informacion
    )

    archivo_csv <- here::here("RNPDNO", "output", "PPT", "PPT_reportes_periodicos_con_avance", "avances_por_categoria_historicos", "avances_por_categoria_historicos.csv")

    # Crear o actualizar
    if (!file.exists(archivo_csv)) {
      message("Creando archivo histórico de avances por categoría...")
      write_csv(nueva_fila, archivo_csv)
  
    } else {
      message("Archivo histórico encontrado. Actualizando datos...")
      avances_por_categoria_historicos <- read_csv(archivo_csv)

      # Modifica la conversión de fecha (líneas ~432-434)
      avances_por_categoria_historicos <- avances_por_categoria_historicos |>
        mutate(fecha = as.Date(fecha, format = "%d/%m/%Y")) # Simplifica esto, read_csv debería detectarlo automáticamente
  
      # IMPORTANTE: Evitar duplicados si el bot corre 2 veces el mismo día
      avances_por_categoria_historicos <- avances_por_categoria_historicos |>
        filter(fecha != as.Date(fecha_actualizacion_pui))
  
      avances_por_categoria_historicos <- bind_rows(
        avances_por_categoria_historicos,
        nueva_fila
      )
      write_csv(avances_por_categoria_historicos, archivo_csv)
    }
      
      # Leer el archivo histórico para obtener la información de la semana pasada y así calcular el avance semanal en cada categoría (con registro administrativo, sin registro administrativo y sin información)
      avances_por_categoria_historicos <- read_csv(archivo_csv)

      # Asegurarnos de que fecha es del tipo Date "%d/%m/%Y"
      avances_por_categoria_historicos <- avances_por_categoria_historicos |>
        mutate(fecha = as.Date(fecha, format = "%d/%m/%Y"))

      # Obtener la fila de la semana pasada. Es decir, la fila con fecha igual a fecha_inicio_semana. Si no existe esa fila, hacemos un warning y no calculamos el avance semanal

      fila_semana_pasada <- avances_por_categoria_historicos |> filter(fecha == as.Date(fecha_inicio_semana))

      if(nrow(fila_semana_pasada) == 1) {
        message("Calculando avances semanales por categoría desde ", fecha_inicio_semana)
        
        avances_por_categoria_historicos |> filter(fecha == as.Date(fecha_inicio_semana))

      if(nrow(fila_semana_pasada) == 1) {

        # Números netos
        avance_semanal_con_act <- nueva_fila$num_desaparecidos_con_act - fila_semana_pasada$num_desaparecidos_con_act
        avance_semanal_sin_act <- nueva_fila$num_desaparecidos_sin_act - fila_semana_pasada$num_desaparecidos_sin_act
        avance_semanal_sin_informacion <- nueva_fila$num_desaparecidos_sin_informacion - fila_semana_pasada$num_desaparecidos_sin_informacion

        # Obtenemos signo de avance semanal (positivo, negativo o neutro)
        signo_avance_semanal_con_act <- case_when(
            avance_semanal_con_act > 0 ~ "+",
            avance_semanal_con_act == 0 ~ "",
            avance_semanal_con_act < 0 ~ "-"
          )
        signo_avance_semanal_sin_act <- case_when(
            avance_semanal_sin_act > 0 ~ "+",
            avance_semanal_sin_act == 0 ~ "",
            avance_semanal_sin_act < 0 ~ "-"
          )
        signo_avance_semanal_sin_informacion <- case_when(
            avance_semanal_sin_informacion > 0 ~ "+",
            avance_semanal_sin_informacion == 0 ~ "",
            avance_semanal_sin_informacion < 0 ~ "-"
          )
        
        # Porcentaje de diferencia
        porcen_avance_semanal_con_act <- ifelse(fila_semana_pasada$num_desaparecidos_con_act > 0, round((avance_semanal_con_act * 100) / fila_semana_pasada$num_desaparecidos_con_act, 2), NA)
        porcen_avance_semanal_sin_act <- ifelse(fila_semana_pasada$num_desaparecidos_sin_act > 0, round((avance_semanal_sin_act * 100) / fila_semana_pasada$num_desaparecidos_sin_act, 2), NA)
        porcen_avance_semanal_sin_informacion <- ifelse(fila_semana_pasada$num_desaparecidos_sin_informacion > 0, round((avance_semanal_sin_informacion * 100) / fila_semana_pasada$num_desaparecidos_sin_informacion, 2), NA)


      } else {
        stop("No se encontró registro histórico para la fecha ", fecha_inicio_semana, ". No se calcularán avances semanales por categoría.")
        avance_semanal_con_act <- NA
        avance_semanal_sin_act <- NA
        avance_semanal_sin_informacion <- NA
        porcen_avance_semanal_con_act <- NA
        porcen_avance_semanal_sin_act <- NA
        porcen_avance_semanal_sin_informacion <- NA
        signo_avance_semanal_con_act <- NA
        signo_avance_semanal_sin_act <- NA
        signo_avance_semanal_sin_informacion <- NA
      }

      # --------------------------------------------------------- #
      # Top 3 dependencias de origen de los registros de la semana ----
      # --------------------------------------------------------- #

      # De comprimido debemos considerar la columna dependencia_origen_original, la cual es el nombre completo y original de la dependencia ecarargada de reportar la desaparición.

      # Primero debemos limpiarla lo más posible

      # Hacer str_to_title directamente en comprimido
      comprimido <- comprimido |>
        mutate(dependencia_origen_original = str_to_title(dependencia_origen_original))

      # Al "Se Desconoce" le debemos imputar "Portal"
      comprimido <- comprimido |>
        mutate(dependencia_origen_original = ifelse(str_detect(dependencia_origen_original, regex("Se Desconoce", ignore_case = TRUE)), "Portal", dependencia_origen_original))

      # La manera en la que vamos a calcular el top es 3 es así:

      # 1. La fecha_hechos_modificada debe ser mayor o igual a fecha_inicio_semana
      # 2. Hacer count en dependencia_origen_original y quedarnos con las 3 más frecuentes en cada de las tres categorías

      # ---- 1. Personas desaparecidas con registro administrativo -----

      desaparecidos_con_act_semana <- comprimido |> 
        filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
               anio_hechos_modificada >= 2006,
                sub_clasificacion == "Desaparecido con registro administrativo") |> 
        left_join(registros_con_pui |> select(fub, fecha_evento), by = "fub") |> 
        filter(!is.na(fecha_evento),
               fecha_evento >= fecha_inicio_semana | fecha_hechos_modificada >= fecha_inicio_semana)
      
      if(nrow(desaparecidos_con_act_semana) == 0) {
        warning("No se encontraron registros de personas desaparecidas con registro administrativo en la semana. Se asignará NA a las variables de top 3 dependencias de origen y conteos.")
      } else {
        message("Registros con actualización administrativa: ", nrow(desaparecidos_con_act_semana))
      }

      count_dependencia_origen_con_act_semana <- desaparecidos_con_act_semana |> 
        count(dependencia_origen_original, sort = TRUE)

      # Cortamos top 3
      top3_dependencia_origen_con_act_semana <- count_dependencia_origen_con_act_semana |> 
        slice_head(n = 3)

      # Hacemos pull de cada dato
      top1_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 1, top3_dependencia_origen_con_act_semana$dependencia_origen_original[1], NA_character_)
      conteo1_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 1, top3_dependencia_origen_con_act_semana$n[1], NA)

      top2_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 2, top3_dependencia_origen_con_act_semana$dependencia_origen_original[2], NA_character_)
      conteo2_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 2, top3_dependencia_origen_con_act_semana$n[2], NA)

      top3_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 3, top3_dependencia_origen_con_act_semana$dependencia_origen_original[3], NA_character_)
      conteo3_con_act <- ifelse(nrow(top3_dependencia_origen_con_act_semana) >= 3, top3_dependencia_origen_con_act_semana$n[3], NA)

      # ------ 2. Personas desaparecidas sin registro administrativo -----

      desaparecidos_sin_act_semana <- comprimido |> 
        filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
               anio_hechos_modificada >= 2006,
                sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo") |>
        filter(fecha_hechos_modificada >= fecha_inicio_semana)

      if(nrow(desaparecidos_sin_act_semana) == 0) {
        warning("No se encontraron registros de personas desaparecidas sin registro administrativo en la semana. Se asignará NA a las variables de top 3 dependencias de origen y conteos.")
      } else {
        message("Registros sin actualización administrativa: ", nrow(desaparecidos_sin_act_semana))
      } 

      count_dependencia_origen_sin_act_semana <- desaparecidos_sin_act_semana |>
        count(dependencia_origen_original, sort = TRUE)

      # Cortamos top 3
      top3_dependencia_origen_sin_act_semana <- count_dependencia_origen_sin_act_semana |> 
        slice_head(n = 3)

      # Hacemos pull de cada dato
      top1_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 1, top3_dependencia_origen_sin_act_semana$dependencia_origen_original[1], NA_character_)
      conteo1_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 1, top3_dependencia_origen_sin_act_semana$n[1], NA)

      top2_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 2, top3_dependencia_origen_sin_act_semana$dependencia_origen_original[2], NA_character_)
      conteo2_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 2, top3_dependencia_origen_sin_act_semana$n[2], NA)

      top3_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 3, top3_dependencia_origen_sin_act_semana$dependencia_origen_original[3], NA_character_)
      conteo3_sin_act <- ifelse(nrow(top3_dependencia_origen_sin_act_semana) >= 3, top3_dependencia_origen_sin_act_semana$n[3], NA)

      # ------ 3. Personas desaparecidas sin información -----

      desaparecidos_sin_informacion_semana <- comprimido |> 
        filter(clasificacion_des %in% c("Desaparecidos", "Pendientes"),
               anio_hechos_modificada >= 2006,
                sub_clasificacion == "Sin datos") |>
        filter(fecha_hechos_modificada >= fecha_inicio_semana)

      if(nrow(desaparecidos_sin_informacion_semana) == 0) {
        warning("No se encontraron registros de personas desaparecidas sin información en la semana. Se asignará NA a las variables de top 3 dependencias de origen y conteos.")
      } else {
        message("Registros sin información: ", nrow(desaparecidos_sin_informacion_semana))
      }

      count_dependencia_origen_sin_informacion_semana <- desaparecidos_sin_informacion_semana |>
        count(dependencia_origen_original, sort = TRUE)

      # Cortamos top 3
      top3_dependencia_origen_sin_informacion_semana <- count_dependencia_origen_sin_informacion_semana |> 
        slice_head(n = 3)

      # Hacemos pull de cada dato
      top1_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 1, top3_dependencia_origen_sin_informacion_semana$dependencia_origen_original[1], NA_character_)
      conteo1_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 1, top3_dependencia_origen_sin_informacion_semana$n[1], NA)

      top2_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 2, top3_dependencia_origen_sin_informacion_semana$dependencia_origen_original[2], NA_character_)
      conteo2_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 2, top3_dependencia_origen_sin_informacion_semana$n[2], NA)

      top3_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 3, top3_dependencia_origen_sin_informacion_semana$dependencia_origen_original[3], NA_character_)
      conteo3_sin_informacion <- ifelse(nrow(top3_dependencia_origen_sin_informacion_semana) >= 3, top3_dependencia_origen_sin_informacion_semana$n[3], NA)

      # --------------------------------------------------------- #
      # Progreso en la localización de personas respecto a la semana previa -----
      # --------------------------------------------------------- #
      
      # Creamos una carpeta histórica "avances_localizaciones_historicos" la cual contendrá un archivo por semana con los avances en la localización de personas desaparición. Se irá actualizando cada semana. Tendrá información de fecha, num_localizados_con_indicios, num_localizados_sin_indicios y num_localizados_sin_informacion

      # ------- 1. Personas localizadas con registros --------
      num_localizados_con_indicios <- comprimido |> filter(indicadora_indicio_de_vida_localizados == "con registro administrativo",
                                     clasificacion_des == "Localizados") |> nrow()
      
      # ------- 2. Personas localizadas sin registros --------
      num_localizados_sin_indicios <- comprimido |> filter(indicadora_indicio_de_vida_localizados == "sin registro administrativo",
                                     clasificacion_des == "Localizados") |> nrow()
      
      # ------- 3. Personas localizadas sin información --------
      num_localizados_sin_informacion <- comprimido |> filter(indicadora_curp_valida == "invalida" & clasificacion_des == "Localizados") |> nrow()

      # Preparar nueva fila
      nueva_fila_localizaciones <- tibble(
        fecha = as.Date(fecha_actualizacion_pui),
        num_localizados_con_indicios = num_localizados_con_indicios,
        num_localizados_sin_indicios = num_localizados_sin_indicios,
        num_localizados_sin_informacion = num_localizados_sin_informacion
      )

      archivo_csv_localizaciones <- here::here("RNPDNO", "output", "PPT", "PPT_reportes_periodicos_con_avance", "avances_localizaciones_historicos", "avances_localizaciones_historicos.csv")

      # Crear o actualizar
      if (!file.exists(archivo_csv_localizaciones)) {
        message("Creando archivo histórico de avances de localizaciones...")
        write_csv(nueva_fila_localizaciones, archivo_csv_localizaciones)
  
      } else {
        message("Archivo histórico de localizaciones encontrado. Actualizando datos...")
        avances_localizaciones_historicos <- read_csv(archivo_csv_localizaciones)

        # Modifica la conversión de fecha
        avances_localizaciones_historicos <- avances_localizaciones_historicos |>
          mutate(fecha = as.Date(fecha, format = "%d/%m/%Y")) # Simplifica esto, read_csv debería detectarlo automáticamente
  
        # IMPORTANTE: Evitar duplicados si el bot corre 2 veces el mismo día
        avances_localizaciones_historicos <- avances_localizaciones_historicos |>
          filter(fecha != as.Date(fecha_actualizacion_pui))
  
        avances_localizaciones_historicos <- bind_rows(
          avances_localizaciones_historicos,
          nueva_fila_localizaciones
        )
        write_csv(avances_localizaciones_historicos, archivo_csv_localizaciones)
      }

      # Leer el archivo histórico para obtener la información de la semana pasada y así calcular el avance semanal en cada categoría (localizados con indicios, sin indicios y sin información)
      avances_localizaciones_historicos <- read_csv(archivo_csv_localizaciones)

      # Asegurarnos de que fecha es del tipo Date "%d/%m/%Y"
      avances_localizaciones_historicos <- avances_localizaciones_historicos |>
        mutate(fecha = as.Date(fecha, format = "%d/%m/%Y"))

      # Obtener la fila de la semana pasada. Es decir, la fila con fecha igual a fecha_inicio_semana. Si no existe esa fila, hacemos un warning y no calculamos el avance semanal
      fecha_semana_pasada_localizaciones <- as.Date(fecha_actualizacion_pui) - 7

      fila_semana_pasada_localizaciones <- avances_localizaciones_historicos |> filter(fecha == fecha_semana_pasada_localizaciones)

      if(nrow(fila_semana_pasada_localizaciones) == 1) {
        message("Calculando avances semanales de localizaciones desde ", fecha_semana_pasada_localizaciones)

        # Números netos
        avance_semanal_localizados_con_indicios <- nueva_fila_localizaciones$num_localizados_con_indicios - fila_semana_pasada_localizaciones$num_localizados_con_indicios
        avance_semanal_localizados_sin_indicios <- nueva_fila_localizaciones$num_localizados_sin_indicios - fila_semana_pasada_localizaciones$num_localizados_sin_indicios
        avance_semanal_localizados_sin_informacion <- nueva_fila_localizaciones$num_localizados_sin_informacion - fila_semana_pasada_localizaciones$num_localizados_sin_informacion

        # Porcentaje de diferencia
        porcen_avance_localizados_con_indicios <- ifelse(fila_semana_pasada_localizaciones$num_localizados_con_indicios > 0, round((avance_semanal_localizados_con_indicios * 100) / fila_semana_pasada_localizaciones$num_localizados_con_indicios, 2), NA)
        porcen_avance_localizados_sin_indicios <- ifelse(fila_semana_pasada_localizaciones$num_localizados_sin_indicios > 0, round((avance_semanal_localizados_sin_indicios * 100) / fila_semana_pasada_localizaciones$num_localizados_sin_indicios, 2), NA)
        porcen_avance_localizados_sin_informacion <- ifelse(fila_semana_pasada_localizaciones$num_localizados_sin_informacion > 0, round((avance_semanal_localizados_sin_informacion * 100) / fila_semana_pasada_localizaciones$num_localizados_sin_informacion, 2), NA)

        # Redondear todos a un decimal
        porcen_avance_localizados_con_indicios <- round(porcen_avance_localizados_con_indicios, 1)
        porcen_avance_localizados_sin_indicios <- round(porcen_avance_localizados_sin_indicios, 1)
        porcen_avance_localizados_sin_informacion <- round(porcen_avance_localizados_sin_informacion, 1)

      } else {
        stop("No se encontró registro histórico de localizaciones para la fecha ", fecha_semana_pasada_localizaciones, ". No se calcularán avances semanales de localizaciones.")

        avance_semanal_localizados_con_indicios <- NA
        avance_semanal_localizados_sin_indicios <- NA
        avance_semanal_localizados_sin_informacion <- NA
      }
        
      message("Cálculo de variables completado exitosamente.")

      return(c(
        list(
          comprimido = comprimido,
          registros_con_pui = registros_con_pui,
          num_registros_admin = num_registros_admin,
          num_indicios_de_vida = num_indicios_de_vida,
          porcen_indicios_de_vida = porcen_indicios_de_vida,
          num_defunciones = num_defunciones,
          porcen_defunciones = porcen_defunciones,
          num_defunciones_renapo = num_defunciones_renapo,
          porcen_defunciones_renapo = porcen_defunciones_renapo,
          num_defunciones_ine = num_defunciones_ine,
          porcen_defunciones_ine = porcen_defunciones_ine,
          num_defunciones_ssa = num_defunciones_ssa,
          porcen_defunciones_ssa = porcen_defunciones_ssa,
          defunciones_df = defunciones_df,
          diccionario_instituciones_indicadoras_de_vida = diccionario_instituciones_indicadoras_de_vida,
          # Variables semanales (NULL si con_corte_semanal = FALSE)
          num_indicios_de_vida_semana = num_indicios_de_vida_semana,
          porcen_indicios_de_vida_semana = porcen_indicios_de_vida_semana,
          signo_porcen_indicios_de_vida_semana = signo_porcen_indicios_de_vida_semana,
          num_defunciones_localizadas_con_vida_semana = num_localizada_con_vida,
          num_defunciones_localizadas_sin_vida_semana = num_localizada_sin_vida,
          num_defunciones_semana = num_defunciones_semana,
          num_defunciones_localizadas_semana = num_defunciones_localizadas_semana,
          porcen_defunciones_localizadas_semana = porcen_defunciones_localizadas_semana,
          coincidencias_admin_con_inactivas_semana_agrupado = coincidencias_admin_con_inactivas_semana_agrupado,
          diccionario_instituciones_indicadoras_de_vida_semana = diccionario_instituciones_indicadoras_de_vida_semana,

          # Variables de avance semanal en cada categoría
          avance_semanal_con_act = avance_semanal_con_act,
          avance_semanal_sin_act = avance_semanal_sin_act,
          avance_semanal_sin_informacion = avance_semanal_sin_informacion,
          porcen_avance_semanal_con_act = porcen_avance_semanal_con_act,
          porcen_avance_semanal_sin_act = porcen_avance_semanal_sin_act,
          porcen_avance_semanal_sin_informacion = porcen_avance_semanal_sin_informacion,
          signo_avance_semanal_con_act = signo_avance_semanal_con_act,
          signo_avance_semanal_sin_act = signo_avance_semanal_sin_act,
          signo_avance_semanal_sin_informacion = signo_avance_semanal_sin_informacion,

          # Variables de top 3 dependencias de origen de los registros de la semana en cada categoría
          top1_con_act = top1_con_act,
          conteo1_con_act = conteo1_con_act,
          top2_con_act = top2_con_act,
          conteo2_con_act = conteo2_con_act,
          top3_con_act = top3_con_act,
          conteo3_con_act = conteo3_con_act,

          top1_sin_act = top1_sin_act,
          conteo1_sin_act = conteo1_sin_act,
          top2_sin_act = top2_sin_act,
          conteo2_sin_act = conteo2_sin_act,
          top3_sin_act = top3_sin_act,
          conteo3_sin_act = conteo3_sin_act,

          top1_sin_informacion = top1_sin_informacion,
          conteo1_sin_informacion = conteo1_sin_informacion,
          top2_sin_informacion = top2_sin_informacion,
          conteo2_sin_informacion = conteo2_sin_informacion,
          top3_sin_informacion = top3_sin_informacion,
          conteo3_sin_informacion = conteo3_sin_informacion,

          # Variables de avance semanal en localizaciones
          avance_semanal_localizados_con_indicios = avance_semanal_localizados_con_indicios,
          avance_semanal_localizados_sin_indicios = avance_semanal_localizados_sin_indicios,
          avance_semanal_localizados_sin_informacion = avance_semanal_localizados_sin_informacion,
          porcen_avance_localizados_con_indicios = porcen_avance_localizados_con_indicios,
          porcen_avance_localizados_sin_indicios = porcen_avance_localizados_sin_indicios,
          porcen_avance_localizados_sin_informacion = porcen_avance_localizados_sin_informacion
        ),
        function_creacion_variables_conteo(diccionario_instituciones_indicadoras_de_vida_semana)
      ))

      } else {

      ## ----- RESULTADOS DE CONTEOS GENERALES ----- ##
      num_registros_admin <- nrow(registros_con_pui_activos)

      num_indicios_de_vida <- nrow(registros_con_pui_activos) - num_defunciones
      porcen_indicios_de_vida <- round((num_indicios_de_vida * 100) / num_registros_admin, 0)

      porcen_defunciones <- round((num_defunciones * 100) / num_registros_admin, 0)

      return(c(
        list(
          comprimido = comprimido,
          registros_con_pui = registros_con_pui,
          num_registros_admin = num_registros_admin,
          num_indicios_de_vida = num_indicios_de_vida,
          porcen_indicios_de_vida = porcen_indicios_de_vida,
          num_defunciones = num_defunciones,
          porcen_defunciones = porcen_defunciones,
          num_defunciones_renapo = num_defunciones_renapo,
          porcen_defunciones_renapo = porcen_defunciones_renapo,
          num_defunciones_ine = num_defunciones_ine,
          porcen_defunciones_ine = porcen_defunciones_ine,
          num_defunciones_ssa = num_defunciones_ssa,
          porcen_defunciones_ssa = porcen_defunciones_ssa,
          defunciones_df = defunciones_df,
          diccionario_instituciones_indicadoras_de_vida = diccionario_instituciones_indicadoras_de_vida,
          # Variables semanales (NULL porque con_corte_semanal = FALSE)
          num_indicios_de_vida_semana = NULL,
          porcen_indicios_de_vida_semana = NULL,
          signo_porcen_indicios_de_vida_semana = NULL,
          num_defunciones_localizadas_con_vida_semana = NULL,
          num_defunciones_localizadas_sin_vida_semana = NULL,
          num_defunciones_semana = NULL,
          num_defunciones_localizadas_semana = NULL,
          porcen_defunciones_localizadas_semana = NULL,
          coincidencias_admin_con_inactivas_semana_agrupado = NULL,
          diccionario_instituciones_indicadoras_de_vida_semana = NULL
        ),
        function_creacion_variables_conteo(diccionario_instituciones_indicadoras_de_vida)
      ))
    }
  }
                                    }