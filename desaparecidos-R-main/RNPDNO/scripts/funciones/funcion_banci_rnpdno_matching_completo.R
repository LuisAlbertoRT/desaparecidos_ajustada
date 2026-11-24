# ————————————————————————————————————————————————————————— #
# Nombres: Jocelyn Rocha y Ariadna Martinez
# Contacto: maricelaymiel@gmail.com
# Script: funcion_matching_banci_rnpdno_matching_completo.R
# Proyecto: Personas desaparecidas
# Fecha de actualización: 2026-08-19

# Propósito: Función de tratamiento de la BANCI y el RNPDNO en dos dimensiones: 1. matching entre ambas bases para identificar los registros de BANCI que sí están en RNPDNO y aquellos que no 2) generación del 'comprimido' (base final) ya sea con solamente la intersección o con la unión entre BANCI y RNPDNO. 

# ————————————————————————————————————————————————————————— #
# Preámbulo -------
# ————————————————————————————————————————————————————————— #

# tryCatch() = manejo de errores en quien llama a la función → va en el bot, no en la función

# Cambios a flujo de matching:

# - 14 de julio de 2026 : Para los casos evaluativos entre localizados de RNPDNO y desaparecidos de BANCI se añade la flexibilidad, antes estricto, de que la fecha de desaparición entre ambas bases pueda diferir hasta por 5 días. Para los casos entre desaparecidos de RNPDNO y desaparecidos de BANCI se flexibiliza la condición de que la fecha de nacimiento sea estrictamente idéntica, en cambio, se deja una ventana de 10 días para que se considere un match. Esto es para evitar falsos negativos en el matching por errores de digitación en las fechas de nacimiento.

# Cambio en flujo del matching: se crea una columna sobre ambas bases Base_BANCI_con_match_con_RNPDNO y Base_BANCI_sin_match_con_RNPDNO una columna extra llamada 'tolerancia_fecha_desaparicion' en donde se indique si en el match la fecha de desaparición coincide exactamente o si difiere hasta por 5 días, 10 días, 1 mes, 2-5 meses y 6-12 meses y otra columna que cuénte exactamente los días de diferencia. Para este fin debemos relajar el criterio de matching de fecha de desaparición entre BANCI y RNPDNO. Esto es para poder evaluar la calidad del matching y detectar posibles falsos negativos.

# ————————————————————————————————————————————————————————— #
# Librerías -------
# ————————————————————————————————————————————————————————— #

pacman::p_load(
  readr, tidyverse, dplyr, lubridate, readxl,
  scales, magrittr, stringi, tsibble, svglite,
  here, janitor, officer, reticulate, purrr,
  glue, fs
)

# ————————————————————————————————————————————————————————— #
# Bases de datos -------
# ————————————————————————————————————————————————————————— #

# ----- Registros administrativos de personas localizadas ------ #
# Nota importante: estos registros NO toman en cuenta las coincidencias administrativas de la PUI, solo los registros de confrontas manuales
# Alerta, es necesario contar con la base "comprimido"; es decir, el RNPDNO.
registros_localizados_path <- dir_ls(here::here(), recurse = TRUE, glob = "*resultados_final_confrontas/tabla_con_indicios_reducido_todo_rnpdno_07042026.xlsx")
registros_localizados <- openxlsx::read.xlsx(registros_localizados_path)

# ————————————————————————————————————————————————————————— #
# Funciones auxiliares -------
# ————————————————————————————————————————————————————————— #

#' Limpiar fechas mixtas (números de Excel y texto) y avisar sobre valores atípicos
#'
#' @param x Vector de tipo character con fechas en alguno de estos formatos: guiones
#'   ("YYYY-MM-DD"), diagonales ("DD/MM/YYYY") o números seriales de Excel (fechas
#'   leídas como numéricas desde hojas de cálculo).
#' @return Vector de clase Date con las fechas parseadas. Los valores con un formato
#'   irreconocible se convierten en NA. Como efecto secundario emite un `message()`
#'   listando los símbolos "raros" (distintos de dígitos, "/" o "-") detectados en `x`.
limpiar_y_avisar <- function(x) {

  # Detectar si hay algo que no sea número, guion o diagonal
  raros <- str_subset(x, "[^0-9/-]") |> unique() |> na.omit()
  
  if(length(raros) > 0) {
    message(paste("Ojo: Se detectaron símbolos extraños en las fechas:", paste(raros, collapse = ", ")))
  }
  
  # 2. Lógica de limpieza
  case_when(
    str_detect(x, "-") ~ as.Date(x, format = "%Y-%m-%d"), # Caso guiones
    str_detect(x, "/") ~ as.Date(x, format = "%d/%m/%Y"), # Caso Diagonales (por si acaso)
    TRUE ~ excel_numeric_to_date(as.numeric(x))           # Caso Números Excel
  )
}

#' Dividir un nombre completo en nombre(s), primer apellido y segundo apellido
#'
#' Versión 2 (última modificación: enero 2026). Usa una heurística basada en
#' preposiciones (de, del, la, los, y, etc.) para evitar que estas se separen
#' incorrectamente de apellidos compuestos, y luego asigna las últimas dos
#' "palabras" como apellidos y el resto como nombre(s).
#'
#' @param nombre_completo Cadena de texto (longitud 1) con el nombre completo a
#'   dividir. Puede ser NA.
#' @return Lista con tres elementos de tipo character: `nombres_corregido`,
#'   `primer_apellido_corregido` y `segundo_apellido_corregido`. Si `nombre_completo`
#'   es NA, los tres elementos regresan como `NA_character_`.
funcion_dividir_nombre_completo <- function(nombre_completo) {
  
  # Caso cero: Hay solo NAs en el nombre completo
  if (is.na(nombre_completo)) {
    return(list(nombres_corregido = NA_character_, 
                primer_apellido_corregido = NA_character_, 
                segundo_apellido_corregido = NA_character_))
  }
  
  # Primera limpieza
  nombre_limpio <- str_squish(nombre_completo)
  regex_preposiciones <- regex("\\b(de\\s+la|de\\s+las|de\\s+los|de|del|la|las|los|y)\\s+",
                               ignore_case = TRUE)
  
  # Preprocesamos los nombres considerando las preposiciones
  nombre_pre_procesado <- str_replace_all(
    nombre_limpio, 
    regex_preposiciones, 
    ~ str_replace_all(.x, "\\s+", "_") 
  )
  
  partes <- str_split(nombre_pre_procesado, " ")[[1]]
  partes <- partes[partes != ""]
  n <- length(partes)
  
  if (n >= 3) {
    # Regla de asignación: los últimos dos son los apellidos.
    # Todo lo anterior son los nombres
    res <- list(
      nombres_corregido = paste(partes[1:(n-2)], collapse = " "),
      primer_apellido_corregido = partes[n-1],
      segundo_apellido_corregido = partes[n]
    )
  } else if (n == 2) {
    # Solo dos partes: asumimos Nombre + Apellido Paterno
    res <- list(
      nombres_corregido = partes[1],
      primer_apellido_corregido = partes[2],
      segundo_apellido_corregido = NA_character_
    )
  } else {
    # Una sola palabra: se mantiene como nombre y no se asigna NA a los apellidos existentes
    res <- list(
      nombres_corregido = nombre_completo,
      primer_apellido_corregido = NULL,
      segundo_apellido_corregido = NULL
    )
  }
  
  # Limpieza final: quitar guiones bajos de todos los elementos
  return(lapply(res, function(x) str_replace_all(x, "_", " ")))
}

# ————————————————————————————————————————————————————————— #
# Función de limpieza de BANCI -------
# ————————————————————————————————————————————————————————— #

#' Limpiar y validar la base BANCI (SubeR) de personas no localizadas
#'
#' Estandariza fechas, nombres, CURP y variables categóricas de la base BANCI,
#' calcula indicadoras de validez de identidad (nombre y/o CURP) y filtra los
#' registros de "No localizada" a partir de `fecha_inicio_BANCI`.
#'
#' @param subeR Data frame con la base BANCI/SubeR cruda, con columnas como
#'   `fha_de_hchos`, `nombres`, `primer_apellido`, `segundo_apellido`, `curp`,
#'   `entidad`/`entidad_federativa`, `localizado_o_no_localizado` y `ntra_ci`.
#' @param fecha_inicio_BANCI Fecha (character, "YYYY-MM-DD") a partir de la
#'   cual se contabilizan y filtran los registros. Default: "2025-08-01".
#' @param salida_base_BANCI_nombres_invalidos_desde_corte Lógico. Si es TRUE,
#'   además se regresa una base con únicamente los registros de nombre
#'   inválido desde `fecha_inicio_BANCI`. Default: FALSE.
#' @param salida_base_SubeR_por_entidad_reporta_desde_corte Lógico. Si es TRUE,
#'   además se regresa un conteo de casos por `entidad_reporta` desde
#'   `fecha_inicio_BANCI`, completado con el catálogo `catalogo_estados_inegi`
#'   (debe existir en el entorno). Default: FALSE.
#' @param fecha_fin_BANCI Fecha (character o Date) de corte más reciente de
#'   BANCI. Obligatorio: la función se detiene con `stop()` si es NULL. Se usa
#'   para corregir filas con `fha_de_hchos` mal etiquetadas (posteriores al
#'   corte, a las que se les resta 1 año).
#' @return Lista con cuatro elementos:
#'   \itemize{
#'     \item `subeR`: base completa limpia (fechas, nombres, CURP e
#'       indicadoras de validez), sin filtrar por fecha ni estatus.
#'     \item `subeR_no_loc_con_corte`: `subeR` filtrada a "No localizada" desde
#'       `fecha_inicio_BANCI`.
#'     \item `base_BANCI_nombres_invalidos_desde_corte`: NULL salvo que se
#'       solicite con el parámetro correspondiente.
#'     \item `base_SubeR_por_entidad_reporta_desde_corte`: NULL salvo que se
#'       solicite con el parámetro correspondiente.
#'   }
#' @note Requiere que `es_curp_valida()` y `catalogo_estados_inegi` ya estén
#'   cargados en el entorno (no se definen dentro de este script).
funcion_limpieza_banci <- function(subeR,
                                  fecha_inicio_BANCI = "2025-08-01",
                                  salida_base_BANCI_nombres_invalidos_desde_corte = FALSE,
                                  salida_base_SubeR_por_entidad_reporta_desde_corte = FALSE,
                                  fecha_fin_BANCI = NULL) {
  
  # Si no se proporciona la base fecha_fin_BANCI se advierte que se debe inyectar la fecha de corte de BANCI más reciente
  if(is.null(fecha_fin_BANCI)) {
    stop("Advertencia: No se ha proporcionado 'fecha_fin_BANCI'. Por favor, inyecta la fecha de corte de BANCI más reciente para asegurar que el análisis se realice correctamente.")
  } else {
    fecha_fin_BANCI <- as.Date(fecha_fin_BANCI)
  }

  # Doble check de fechas antes de correr el resto de la función
  if (interactive()) {
    eleccion <- utils::menu(
      choices = c("Sí, son correctas", "No, cancelar"),
      title = sprintf(
        "¿Confirmas que el rango de BANCI a usar es del %s al %s?",
        fecha_inicio_BANCI, fecha_fin_BANCI
      )
    )
    
    if (eleccion != 1) {
      stop("Ejecución cancelada: ajusta fecha_inicio_BANCI / fecha_fin_BANCI y vuelve a correr.")
    }
  } else {
    message("Modo no interactivo: se omitió la confirmación. Rango usado -> ",
            fecha_inicio_BANCI, " a ", fecha_fin_BANCI)
  }

  # Limpiar fechas de la BANCI
  subeR <- subeR |> 
    mutate(across(matches("^fha|^fecha"), limpiar_y_avisar))

  # Si existe una columna llamada entidad_federativa cambiar nombre a 'entidad'
  if("entidad_federativa" %in% colnames(subeR)) {
    subeR <- subeR |> 
      rename(entidad = entidad_federativa)
  }

  # Corección datos con fha_hechos mal etiquetadas
  # Si el máximo de fechas de hechos (fha_hechos) es mayor a fecha_fin_BANCI entonces hacer un warning: contar cuántas filas tienen ese caso 
  if(any(subeR$fha_de_hchos > fecha_fin_BANCI, na.rm = TRUE)) {
    num_filas_mal_etiquetadas <- sum(subeR$fha_de_hchos > fecha_fin_BANCI, na.rm = TRUE)
    warning(paste("Se detectaron", num_filas_mal_etiquetadas, "filas con 'fha_de_hchos' posterior a la fecha de corte de BANCI. Se restará 1 año a estas fechas para corregirlas."))
  }

  subeR <- subeR |> 
    mutate(
      fha_de_hchos = if_else(fha_de_hchos > fecha_fin_BANCI, fha_de_hchos - years(1), fha_de_hchos)
    )
  
  # Anunciar el rango de fechas de fha_de_hchos después de la limpieza
  rango_fechas_SubeR <- range(subeR$fha_de_hchos, na.rm = TRUE)

  message(paste("Después de la limpieza, el rango de fechas en 'fha_de_hchos' va desde", 
                format(rango_fechas_SubeR[1], "%Y-%m-%d"), "hasta", 
                format(rango_fechas_SubeR[2], "%Y-%m-%d")), "\n")
  
  # Asegurarnos de que las fechas siempre sean superiores a "1900-01-01" (fecha mínima en Excel)

  # Detectar cuántas filas tienen fechas de hechos anteriores a 1900-01-01
  num_filas_fechas_imposibles <- sum(subeR$fha_de_hchos < as.Date("1900-01-01"), na.rm = TRUE)

  subeR <- subeR |> 
    mutate(
      fha_de_hchos = if_else(fha_de_hchos < as.Date("1900-01-01"), as.Date(NA), fha_de_hchos)
    )
  
  message("Ojo: Se han convertido a NA las fechas de 'fha_de_hchos' que son anteriores a 1900-01-01, ya que estas no son fechas válidas en el contexto de este análisis. El número de filas afectadas por esta conversión es: ", num_filas_fechas_imposibles, "\n")
  
  # Corregimos procesamiento de nombres
  # Usamos función "funcion_dividir_nombre_completo"
  subeR <- subeR |> 
    mutate(
    # Identificar casos problemáticos
    necesita_correccion = !is.na(nombres) & str_detect(str_squish(nombres), "\\s+") & 
                      (is.na(primer_apellido) | is.na(segundo_apellido)),
    
    # Aplicar la función solo a los casos problemáticos
    temp_resultado = ifelse(
      necesita_correccion,
       map(nombres, funcion_dividir_nombre_completo),
       list(list(
          nombres_corregido = NA_character_,
          primer_apellido_corregido = NA_character_,
          segundo_apellido_corregido = NA_character_
        ))
      ),
    
      # Extraer los resultados
      nuevos_nombres = map_chr(temp_resultado, ~ .x$nombres_corregido),
      nuevo_primer_apellido = map_chr(temp_resultado, ~ .x$primer_apellido_corregido),
      nuevo_segundo_apellido = map_chr(temp_resultado, ~ .x$segundo_apellido_corregido),
    
      # Actualizar las columnas originales
      nombres = if_else(necesita_correccion, nuevos_nombres, nombres),
      primer_apellido = if_else(necesita_correccion & !is.na(nuevo_primer_apellido), 
                              nuevo_primer_apellido, primer_apellido),
      segundo_apellido = if_else(necesita_correccion & !is.na(nuevo_segundo_apellido), 
                               nuevo_segundo_apellido, segundo_apellido)
    ) |> 
    # Eliminar columnas temporales
    select(-necesita_correccion, -temp_resultado, -nuevos_nombres, 
         -nuevo_primer_apellido, -nuevo_segundo_apellido)
  
  # Hacer nombres, primer_apellido y segundo_apellido a mayúsculas todas las letras
  subeR <- subeR |> 
    mutate(
      nombres = toupper(nombres),
      primer_apellido = toupper(primer_apellido),
      segundo_apellido = toupper(segundo_apellido)
    )
  
  # Eliminamos los ceros y remplazamos por NA
  subeR <- subeR |> 
    mutate(across(c(nombres,
                  primer_apellido, 
                  segundo_apellido), ~ replace(.x, .x == "0", NA_character_)))
  
  ## ----- Crear columna que nos diga si el nombre es válido o no ---- ##

  # Regex con patrones inválidos
  patron_ruido <- regex(
    "SE DESCONOCE|RESTOS OSEOS|CUERPO|SIN VIDA|DESCONOCIDO|NO IDENTIFICADO|\\bSD\\b|\\bNA\\b|^M$|([a-z]\\.){2,}[a-z]?", 
    ignore_case = TRUE
  )

  # Creamos indicadora de nombre válido o no
  subeR <- subeR |> 
    mutate(nombre_completo_victima = str_squish(paste(nombres, primer_apellido, segundo_apellido))) |> 
    mutate(indicadora_nombre_valido = case_when(
      # Caso 1: Es NA
      is.na(nombre_completo_victima) ~ "invalido",
    
      # Caso 2: Tiene números
      str_detect(nombre_completo_victima, "\\d") ~ "invalido",
    
      # Caso 3: Contiene palabras prohibidas o abreviaturas 
      str_detect(nombre_completo_victima, patron_ruido) ~ "invalido",
    
      # Caso 4: Es demasiado corto (menos de 11 caracteres)
      nchar(nombre_completo_victima) < 11 ~ "invalido",
    
      TRUE ~ "valido"
    ))
  
  # Evaluar cuántos nombres inválidos tenemos desde fecha_inicio_BANCI
  num_nombres_invalidos_desde_fecha_inicio_BANCI <- subeR |> 
    filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI)) |> 
    summarise(num_invalidos = sum(indicadora_nombre_valido == "invalido", na.rm = TRUE)) |> 
    pull(num_invalidos)

  message("Desde la fecha de inicio de BANCI (", fecha_inicio_BANCI, ") se han detectado ", num_nombres_invalidos_desde_fecha_inicio_BANCI, " nombres inválidos según los criterios establecidos.", "\n")

  # Si base_BANCI_nombres_invalidos_desde_corte es TRUE entonces nos quedamos solo con los nombres inválidos desde fecha_inicio_BANCI para luego devolver esa base al final
  if(salida_base_BANCI_nombres_invalidos_desde_corte) {
    base_BANCI_nombres_invalidos_desde_corte <- subeR |> 
      filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI) & indicadora_nombre_valido == "invalido")
  }

  ## ----- Creamos indicadora de curp limpia válida ----- ##
  # Quitamos TODO el espacio en blanco (espacios, tabs, saltos de línea) y mandamos a mayúsculas
  subeR <- subeR |> 
    mutate(
      curp_limpia = str_remove_all(curp, "\\s+"),
      curp_limpia = str_to_upper(curp_limpia)
    )

  subeR <- subeR |> 
    mutate(indicadora_curp_valida = if_else(
      es_curp_valida(curp), "valida", "invalida"
    ),
    indicadora_curp_limpia_valida = if_else(
      es_curp_valida(curp_limpia), "valida", "invalida"
    ))
  
  subeR <- subeR |> 
    mutate(indicadora_identidad_valida = if_else(
      indicadora_curp_limpia_valida == "valida" | indicadora_nombre_valido == "valido", 
      "valida", "invalida"
    ))


  ## ----- Variable de entidad de hechos ----- ##

  # Renombramos 
  subeR <- subeR |> 
    rename(entidad_reporta = entidad)

  # Arreglar inconsistencias (si las hay) en "entidad_reporta"
  subeR <- subeR |> 
    mutate(
      entidad_reporta = case_when(
      entidad_reporta == "OAXACA" ~ "Oaxaca",
      entidad_reporta == "Ciudad De Mexico" ~ "Ciudad de México",
      TRUE ~ entidad_reporta
      )
    )
  
  ## ----- Variable de localización o NO localización ----- ##

  # Corregir typos en localizado_o_no_localizado (si los hay)
  subeR <- subeR |> 
    mutate(
      localizado_o_no_localizado = case_when(
        localizado_o_no_localizado == "NO LOCALIZADA" ~ "No localizada",
        localizado_o_no_localizado == "LOCALIZADA" ~ "Localizada",
        TRUE ~ localizado_o_no_localizado
      )
    )
  
  # Sumar casos desde fecha_inicio_BANCI por cada categoría de localizado_o_no_localizado
  num_localizados_desde_fecha_inicio_BANCI <- subeR |> 
    filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI)) |> 
    filter(localizado_o_no_localizado == "Localizada") |>
    nrow()

  num_no_localizados_desde_fecha_inicio_BANCI <- subeR |> 
    filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI)) |> 
    filter(localizado_o_no_localizado == "No localizada") |>
    nrow()

  message("Desde la fecha de inicio de BANCI (", fecha_inicio_BANCI, ") se han detectado ", comma(num_localizados_desde_fecha_inicio_BANCI), " casos localizados y ", comma(num_no_localizados_desde_fecha_inicio_BANCI), " casos no localizados.", "\n")

  # ————————————————————————————————————————————————————————— #
  # Filtramos la base desde fecha_inicio_BANCI ----- #
  # ————————————————————————————————————————————————————————— #
  
  # Solo No localizados
  subeR_con_corte <- subeR |> 
    filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI) & localizado_o_no_localizado == "No localizada")

  message("Después de filtrar la base de BANCI para quedarnos solo con los casos de 'No localizada' desde la fecha de inicio de BANCI (", fecha_inicio_BANCI, ") el número total de casos es: ", comma(nrow(subeR_con_corte)), "\n")

  ## ------ Variable de carpetas de investigación (ntra_ci) ----- ##

  # Ver casos de O o NAs en ntra_ci
  num_ci_vacias <- subeR_con_corte |> 
    filter(is.na(ntra_ci) | ntra_ci == "0") |> 
    nrow()
  
  message("En la base de BANCI filtrada para 'No localizada' desde la fecha de inicio de BANCI, se han detectado ", comma(num_ci_vacias), " casos con carpetas de investigación ('ntra_ci') vacía (NA o 0).", "\n")

  num_ci_duplicadas <- subeR_con_corte |> 
    count(ntra_ci) |>
    arrange(desc(n)) |>
    filter(n > 1) |>
    nrow()

  message("En la base de BANCI filtrada para 'No localizada' desde la fecha de inicio de BANCI, se han detectado ", comma(num_ci_duplicadas), " carpetas de investigación ('ntra_ci') que están duplicadas.", "\n")

  # Si base_SubeR_por_entidad_reporta_desde_corte es TRUE entonces generamos una base con el número de casos por entidad reporta desde fecha_inicio_BANCI para luego devolver esa base al final
  if(salida_base_SubeR_por_entidad_reporta_desde_corte) {
    base_SubeR_por_entidad_reporta_desde_corte <- subeR_con_corte |> 
      group_by(entidad_reporta) |> 
      summarise(num_casos_de_desaparicion = n()) |> 
      arrange(desc(num_casos_de_desaparicion))

    # Pegamos con el catálogo de estados para tener el nombre completo de la entidad
    base_SubeR_por_entidad_reporta_desde_corte <- base_SubeR_por_entidad_reporta_desde_corte |> 
      full_join(catalogo_estados_inegi, by = c("entidad_reporta" = "nom_ent")) |> 
      select(-cve_ent)
    
    # Rellenamos con 0 casos de NAs
    base_SubeR_por_entidad_reporta_desde_corte <- base_SubeR_por_entidad_reporta_desde_corte |> 
      mutate(num_casos_de_desaparicion = replace_na(num_casos_de_desaparicion, 0))
  }

  # Regresar las bases
  return(list(
    subeR = subeR,
    subeR_no_loc_con_corte = subeR_con_corte,
    base_BANCI_nombres_invalidos_desde_corte = if(salida_base_BANCI_nombres_invalidos_desde_corte) base_BANCI_nombres_invalidos_desde_corte else NULL,
    base_SubeR_por_entidad_reporta_desde_corte = if(salida_base_SubeR_por_entidad_reporta_desde_corte) base_SubeR_por_entidad_reporta_desde_corte else NULL
  ))
}

# ————————————————————————————————————————————————————————— #
# Función de tolarancia de fechas de desaparición -------
# ————————————————————————————————————————————————————————— #

#' Categorizar la diferencia en días entre dos fechas de desaparición
#'
#' Función vectorizada usada para evaluar la calidad del match entre BANCI y
#' RNPDNO: calcula la diferencia absoluta en días entre dos fechas y la
#' clasifica en bandas de tolerancia, con umbrales distintos según si el
#' contraste es contra desaparecidos (más flexible) o contra localizados
#' (más estricto).
#'
#' @param fecha1 Vector de fechas (Date) a comparar, típicamente `fha_de_hchos`
#'   de BANCI.
#' @param fecha2 Vector de fechas (Date) a comparar, típicamente
#'   `fecha_hechos_rnpdno` del RNPDNO. Debe tener la misma longitud que
#'   `fecha1` (o ser reciclable).
#' @param tipo_match Character. "desaparecidos" usa bandas de 5, 10, 30, 150 y
#'   365 días; "localizados" usa bandas más estrictas de 5, 15 y 30 días;
#'   cualquier otro valor regresa un vector de NAs. Default: "desaparecidos".
#' @return Vector de tipo character, de la misma longitud que
#'   `fecha1`/`fecha2`, con una de las categorías ("Exacta", "1-5 días", ...,
#'   "Más de 1 año" / "Más de 30 días"), o NA cuando la diferencia de fechas
#'   es NA.
categorizar_tolerancia_fecha <- function(fecha1, fecha2, tipo_match = "desaparecidos") {
  
  # Calcular diferencia en días (valor absoluto)
  diff_dias <- abs(as.numeric(difftime(fecha1, fecha2, units = "days")))
  
  # Categorizar según tipo de match (usando case_when que SÍ está vectorizado)
  if (tipo_match == "desaparecidos") {
    # Para desaparecidos vs desaparecidos (criterio más flexible)
    case_when(
      is.na(diff_dias) ~ NA_character_,  # ✅ Primero manejar NAs
      diff_dias == 0 ~ "Exacta",
      diff_dias <= 5 ~ "1-5 días",
      diff_dias <= 10 ~ "6-10 días",
      diff_dias <= 30 ~ "11-30 días (1 mes)",
      diff_dias <= 150 ~ "2-5 meses",
      diff_dias <= 365 ~ "6-12 meses",
      TRUE ~ "Más de 1 año"
    )
  } else if (tipo_match == "localizados") {
    # Para localizados vs desaparecidos (criterio más estricto)
    case_when(
      is.na(diff_dias) ~ NA_character_,  # ✅ Primero manejar NAs
      diff_dias == 0 ~ "Exacta",
      diff_dias <= 5 ~ "1-5 días",
      diff_dias <= 15 ~ "6-15 días",
      diff_dias <= 30 ~ "16-30 días",
      TRUE ~ "Más de 30 días"
    )
  } else {
    rep(NA_character_, length(diff_dias))  # ✅ Devolver vector de NAs del mismo tamaño
  }
}

# ————————————————————————————————————————————————————————— #
# Función de matching entre BANCI y RNPDNO -------
# ————————————————————————————————————————————————————————— #

#' Hacer el matching jerárquico entre BANCI y RNPDNO (FUB > CURP > nombre)
#'
#' Cruza los registros de personas no localizadas de BANCI (`subeR`) contra el
#' RNPDNO (`comprimido`) en tres pasadas jerárquicas y excluyentes: 1) por FUB
#' + nombre, 2) por CURP y 3) por nombre completo (con criterios de tolerancia
#' en fecha de nacimiento, fecha de hechos y/o entidad). En cada paso
#' contrasta tanto contra el universo de desaparecidos como contra el de
#' localizados del RNPDNO, calculando además `tolerancia_fecha_desaparicion` y
#' `diferencia_dias_desaparicion` para evaluar la calidad del match (ver
#' [categorizar_tolerancia_fecha()]).
#'
#' @param subeR Data frame de BANCI ya limpio (ver [funcion_limpieza_banci()]),
#'   con columnas como `localizado_o_no_localizado`, `fha_de_hchos`,
#'   `indicadora_identidad_valida`, `indicadora_curp_limpia_valida`,
#'   `indicadora_nombre_valido`, `nombre_completo_victima`, `curp_limpia`,
#'   `folio_rnpdno` y `fha_de_ini`.
#' @param comprimido Data frame del RNPDNO ("comprimido"), con columnas como
#'   `fub`, `curp_victima`, `nombre_vic`, `primerapellido_vic`,
#'   `segundoapellido_vic`, `fechanacimiento`, `fechahechos`,
#'   `estado_desaparicion`, `indicadora_carpeta`, `clasificacion_des` y `sexo`.
#' @param fecha_inicio_BANCI Fecha (character, "YYYY-MM-DD") desde la cual se
#'   consideran los casos de BANCI. Default: "2025-08-01".
#' @param fecha_fin_BANCI Fecha (character o Date) de corte más reciente de
#'   BANCI; obligatoria (la función se detiene con `stop()` si es NULL o si
#'   falta `subeR`). Los casos de BANCI se filtran a
#'   `fecha_inicio_BANCI <= fha_de_hchos < fecha_fin_BANCI`.
#' @return Lista con dos data frames:
#'   \itemize{
#'     \item `Base_BANCI_con_match_con_RNPDNO`: registros de BANCI que sí
#'       encontraron pareja en el RNPDNO (una fila por `fub_rnpdno`), con
#'       columnas de evaluación del match (`tipo_match`, `variables_match`,
#'       `evaluacion_match`, `score`, `verif_curp`, `verif_nombre`,
#'       `verif_entidad`, `verif_sexo`, `verif_fecha_nac`,
#'       `fecha_hechos_status`, etc.).
#'     \item `Base_BANCI_sin_match_con_RNPDNO`: registros de BANCI (con y sin
#'       identidad válida) que no encontraron pareja en el RNPDNO.
#'   }
funcion_de_match_BANCI_y_RNPDNO <- function(subeR,
                                           comprimido,
                                           fecha_inicio_BANCI = "2025-08-01",
                                           fecha_fin_BANCI = NULL) {

  # Si no se proporciona la base 'subeR', se detiene la función y se muestra un mensaje de error
  if (missing(subeR)) {
    stop("Error: La base 'subeR' no ha sido proporcionada. Por favor, asegúrate de cargar la base 'subeR' antes de ejecutar esta función.")
  }

  # Si fecha_fin_BANCI es NULL se advierte que se debe inyectar la fecha de corte de BANCI más reciente
  if (is.null(fecha_fin_BANCI)) {
    stop("Advertencia: No se ha proporcionado 'fecha_fin_BANCI'. Por favor, inyecta la fecha de corte de BANCI más reciente para asegurar que el análisis se realice correctamente.")
  }
  
  # ----------------------------------------------------
  # 1. Preparación de la BANCI 
  # ----------------------------------------------------
  
  # 1.1. Solo quedarnos con personas NO localizadas
  subeR_no_localizados <- subeR |> 
  filter(localizado_o_no_localizado == "No localizada")
  
  # 1.2. Definir fecha de corte de BANCI
  subeR_no_localizados <- subeR_no_localizados |> 
    filter(fha_de_hchos >= fecha_inicio_BANCI & 
           fha_de_hchos < fecha_fin_BANCI)

  message("El número de personas desaparecidas totales en SubeR son: ",
  comma(nrow(subeR_no_localizados)), "\n")
  
  # 1.3. Creamos indicador de cada fila
  subeR_no_localizados$indicador <- 1:nrow(subeR_no_localizados)
  
  # Cambio del 09 de enero de 2025: de esta fecha en adelante se considerarán todos los registros de 'no localizados' de la BANCI, es decir, también aquellas filas que no cuentan con nombre o con curp. Para no alterar el proceso de deduplicación y limpieza de datos (pasos 1.5 a 1.7 del código), debemos agregar aquellos datos que cumplen con indicadora_identidad_valida == "invalida" al final de la función
  
  # 1.4. Limpiamos alguas columnas de la base 'SubeR_no_localizados'
  subeR_no_localizados <- subeR_no_localizados |> 
    mutate(
      indicadora_identidad_valida = trimws(tolower(indicadora_identidad_valida)),
      
      # Convertimos strings vacíos en NAs reales si los hubiera
      folio_rnpdno = ifelse(folio_rnpdno == "", NA, folio_rnpdno)
    )

  # 1.5. Filtramos aquellos que tienen identidad válida o que tienen fub no vacía
  subeR_no_localizados_identidad_valida <- subeR_no_localizados |> 
   filter(indicadora_identidad_valida == "valida" |
           !is.na(folio_rnpdno)) 
  
  message("El número de personas desaparecidas con idéntidad válida en SubeR son: ",
      comma(nrow(subeR_no_localizados_identidad_valida)), "\n")
  
  # Adicionalmente también separamos a las personas desaparecidas sin identidad válida
  subeR_no_localizados_sin_identidad_valida <- subeR_no_localizados |> 
   filter(indicadora_identidad_valida == "invalida" &
           is.na(folio_rnpdno)) 
  
  message("El número de personas desaparecidas que NO tienen identidad válida son: ", comma(nrow(subeR_no_localizados_sin_identidad_valida)), "\n")
  
  # 1.6 Ordenamos por fecha de hechos en forma descendente para quedarse con el último
  subeR_no_localizados_identidad_valida <-
    subeR_no_localizados_identidad_valida |> 
  arrange(desc(fha_de_hchos))
  
  # 1.7. Eliminar curps repetidas
  subeR_no_localizados_identidad_valida_curp <- subeR_no_localizados_identidad_valida %>%
  filter(indicadora_curp_limpia_valida == "valida")
  
  subeR_no_localizados_identidad_invalida_curp <- subeR_no_localizados_identidad_valida %>%
  filter(indicadora_curp_limpia_valida == "invalida")
  
  subeR_no_localizados_identidad_valida_curp <-
    subeR_no_localizados_identidad_valida_curp |> 
    distinct(curp, .keep_all = T)
  
  subeR_no_localizados_identidad_valida <- subeR_no_localizados_identidad_valida_curp |> 
  bind_rows(subeR_no_localizados_identidad_invalida_curp)
  
  rm(subeR_no_localizados_identidad_valida_curp, subeR_no_localizados_identidad_invalida_curp)
  
  # 1.8. Eliminar nombres repetidos (que además cumplan con otro criterio)
  
  # Usamos fecha inicio como verificador de que se trata de la misma persona
  message("De manera esperada, no hay NAs en la variable 'fecha_inicio' (aquella que se usa como verificadora de que se trata de la misma persona en caso de mismo nombre): ", sum(is.na(subeR_no_localizados_identidad_valida$fha_de_ini))," NAs",
      "\n")
  
  subeR_no_localizados_identidad_valida <-
    subeR_no_localizados_identidad_valida |> 
    mutate(nombre_concat = paste0(nombre_completo_victima, fha_de_ini))
  
  subeR_no_localizados_identidad_valida_nombre_valido <- subeR_no_localizados_identidad_valida |> 
  filter(indicadora_nombre_valido == "valido")
  
  subeR_no_localizados_identidad_valida_nombre_invalido <- subeR_no_localizados_identidad_valida |> 
  filter(indicadora_nombre_valido == "invalido")
  
  subeR_no_localizados_identidad_valida_nombre_valido <-
    subeR_no_localizados_identidad_valida_nombre_valido |> 
  distinct(nombre_concat, .keep_all = T)
  
  subeR_no_localizados_identidad_valida <- subeR_no_localizados_identidad_valida_nombre_valido |> 
  bind_rows(subeR_no_localizados_identidad_valida_nombre_invalido)
  
  rm(subeR_no_localizados_identidad_valida_nombre_valido, 
   subeR_no_localizados_identidad_valida_nombre_invalido)

  # ----------------------------------------------------
  # 2. Preparación de RNPDNO
  # ----------------------------------------------------

  # Añadimos variable de nombre completo
  comprimido <- comprimido |> 
    mutate(nombre_completo_victima = paste(
      nombre_vic, primerapellido_vic, segundoapellido_vic, sep = " "
    )) 
  
  # ------ No localizados -------
  
  # 2.1. Quedarnos con solo personas NO localizadas
  comprimido_no_localizados <- comprimido |> 
  filter(!clasificacion_des %in% "Localizados")
  
  # 2.2. Seleccionar variables relevantes del RNPDNO
  comprimido_no_localizados_abr <- comprimido_no_localizados %>%
  select(
    fub, curp_victima, nombre_completo_victima, fecha_nacimiento = fechanacimiento, 
    fecha_hechos = fechahechos, entidad_hechos = estado_desaparicion, indicadora_carpeta,
    clasificacion_des, sexo)

  # 2.3. Añadimos sufijos de nombres
  names(comprimido_no_localizados_abr) <- paste0(
  names(comprimido_no_localizados_abr), "_rnpdno"
)
  comprimido_no_localizados_abr$indicadora_rnpdno <- "rnpdno"
  
  # ------ Localizados -------
  
  # 2.4. Hacer un subset de personas localizadas
  comprimido_localizados <- comprimido |> 
    filter(clasificacion_des %in% "Localizados")

  
  # 2.5. Seleccionar variables relevantes del RNPDNO
  comprimido_localizados_abr <- comprimido_localizados %>%
  select(
    fub, curp_victima, nombre_completo_victima, fecha_nacimiento = fechanacimiento, 
    fecha_hechos = fechahechos, entidad_hechos = estado_desaparicion, indicadora_carpeta,
    clasificacion_des, sexo)

  # 2.6. Añadimos sufijos de nombres
  names(comprimido_localizados_abr) <- paste0(
  names(comprimido_localizados_abr), "_rnpdno"
)
  comprimido_localizados_abr$indicadora_rnpdno <- "rnpdno"
  
  # ----------------------------------------------------
  # 3. Pre-tratamiento para el matching
  # ----------------------------------------------------
  
  # ---- Sube R -----
  
  # 3.1. Creamos columna 'nombre_completo_mas_fub', la cual nos será útil para el match fub + nombre
  subeR_no_localizados_identidad_valida <- subeR_no_localizados_identidad_valida |> 
  mutate(nombre_completo_mas_fub = str_squish(toupper(paste(
    nombre_completo_victima, folio_rnpdno, sep = " "
  ))))
  
  # ----- Desaparecidos en RNPDNO -----
  
  # 3.2. Crear indicadora de match con fub + nombre de la víctima en RNPDNO desaparecidos
  comprimido_no_localizados_abr <- comprimido_no_localizados_abr |> 
    mutate(nombre_completo_mas_fub = str_squish(toupper(paste(
    nombre_completo_victima_rnpdno, fub_rnpdno, sep = " "
  ))))
  
  # ----- Localizados de RNPDNO ------
  
  # 3.3. Crear indicadora de match con fub + nombre de la víctima en RNPDNO localizados
  comprimido_localizados_abr <- comprimido_localizados_abr |> 
    mutate(nombre_completo_mas_fub = str_squish(toupper(paste(
    nombre_completo_victima_rnpdno, fub_rnpdno, sep = " "
  ))))
  
  # ----------------------------------------------------
  # 4. Match jerárquico: es decir, solo contamos una vez cada match entre BANCI y RNPDNO
  # ----------------------------------------------------

  # Se prioriza el siguiente orden: 1. match por fub, 2. match por curp y 3. match por nombre
  
  # ----------------------------------------------------
  # 4.1. Match por FUB
  # ----------------------------------------------------
  
  # 4.1.1 Creamos la tabla de FUB MATCHES (desparecidos_secretariado_fub_match)
  desparecidos_fub_match_temp <- subeR_no_localizados_identidad_valida |>
    mutate(tipo_match = case_when(nombre_completo_mas_fub %in% comprimido_no_localizados_abr$nombre_completo_mas_fub ~ "match_fub",
                                  TRUE ~ NA_character_))
  
  # 4.1.2 Intentamos hacer el match con las personas localizadas de RNPDNO 
  # siempre y cuando la fecha de desaparición coincida con una ventana de 5 días
  desparecidos_fub_match_temp <- desparecidos_fub_match_temp |> 
  left_join(
    comprimido_localizados_abr |> 
      select(nombre_completo_mas_fub, fub_rnpdno, indicadora_rnpdno, 
             fecha_hechos_rnpdno, entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
             indicadora_carpeta_rnpdno, clasificacion_des_rnpdno), 
    by = "nombre_completo_mas_fub",
    suffix = c("", "_loc")
  ) |> 
  mutate(
    # Calcular tolerancia para localizados
    tolerancia_fecha_desaparicion_temp = categorizar_tolerancia_fecha(
      fha_de_hchos, 
      fecha_hechos_rnpdno, 
      tipo_match = "localizados"
    ),
    # Match válido si cumple criterio de tolerancia (hasta 30 días)
    tipo_match = case_when(
      !is.na(tipo_match) ~ tipo_match,
      tolerancia_fecha_desaparicion_temp %in% c("Exacta", "1-5 días", "6-15 días", "16-30 días") ~ "match_fub",
      TRUE ~ NA_character_
    ),
    # Contar diferencia exacta en días (con signo)
    diferencia_dias_desaparicion_temp = if_else(
      tipo_match == "match_fub" & !is.na(fha_de_hchos) & !is.na(fecha_hechos_rnpdno),
      as.numeric(fha_de_hchos - fecha_hechos_rnpdno),
      NA_real_
    )
  )
  
  # 4.1.3. Hacemos el JOIN para traer la columnas del RPDNO en el caso de las personas que hicieron match con la base 'comprimido_no_localizados_abr'
  desparecidos_fub_match_temp <- desparecidos_fub_match_temp |>
  left_join(
    comprimido_no_localizados_abr |> 
      select(nombre_completo_mas_fub, fub_rnpdno, indicadora_rnpdno, 
             fecha_hechos_rnpdno, entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
             indicadora_carpeta_rnpdno, clasificacion_des_rnpdno), 
    by = "nombre_completo_mas_fub",
    suffix = c("_temp", "_no_loc")
  ) |>
  select(-nombre_completo_mas_fub)
  
  # 4.1.4. Limpiamos
  desparecidos_fub_match_temp <- desparecidos_fub_match_temp |> 
  mutate(
    # Consolidar columnas (priorizar no localizados)
    fub_rnpdno = coalesce(fub_rnpdno_no_loc, fub_rnpdno_temp),
    indicadora_rnpdno = coalesce(indicadora_rnpdno_no_loc, indicadora_rnpdno_temp),
    fecha_hechos_rnpdno = coalesce(fecha_hechos_rnpdno_no_loc, fecha_hechos_rnpdno_temp),
    entidad_hechos_rnpdno = coalesce(entidad_hechos_rnpdno_no_loc, entidad_hechos_rnpdno_temp),
    fecha_nacimiento_rnpdno = coalesce(fecha_nacimiento_rnpdno_no_loc, fecha_nacimiento_rnpdno_temp),
    indicadora_carpeta_rnpdno = coalesce(indicadora_carpeta_rnpdno_no_loc, indicadora_carpeta_rnpdno_temp),
    clasificacion_des_rnpdno = coalesce(clasificacion_des_rnpdno_no_loc, clasificacion_des_rnpdno_temp),
    
    # Calcular tolerancia final (distinguir tipo de match)
    tolerancia_fecha_desaparicion = case_when(
      # Si matcheó con desaparecidos (sin restricción de fecha)
      !is.na(fub_rnpdno_no_loc) ~ categorizar_tolerancia_fecha(
        fha_de_hchos, 
        fecha_hechos_rnpdno_no_loc, 
        tipo_match = "desaparecidos"
      ),
      # Si matcheó con localizados
      !is.na(fub_rnpdno) ~ tolerancia_fecha_desaparicion_temp,
      TRUE ~ NA_character_
    ),
    
    # Calcular diferencia exacta en días (consolidada)
    diferencia_dias_desaparicion = case_when(
      # Si matcheó con desaparecidos
      !is.na(fub_rnpdno_no_loc) & tipo_match == "match_fub" ~ 
        as.numeric(fha_de_hchos - fecha_hechos_rnpdno_no_loc),
      # Si matcheó con localizados
      !is.na(fub_rnpdno) & tipo_match == "match_fub" ~ 
        diferencia_dias_desaparicion_temp,
      TRUE ~ NA_real_
    )
  ) |> 
  select(-ends_with("_loc"), -ends_with("_no_loc"), 
         -diferencia_dias_desaparicion_temp, -tolerancia_fecha_desaparicion_temp)
  
  # Crear columna variables_match que avise el tipo de match que se realizó (NOMBRE 1.00 + FUB)
  desparecidos_fub_match_temp <- desparecidos_fub_match_temp |> 
    mutate(variables_match = case_when(
      tipo_match == "match_fub" ~ "NOMBRE 1.00 + FUB",
      TRUE ~ NA_character_
    ))
  
  # 4.1.5 Seleccionamos solo aquellos que tienen marca de match
  desparecidos_fub_match <- desparecidos_fub_match_temp |> 
    filter(tipo_match == "match_fub")
  
  # 4.1.6 Creamos la base remanente (registros que NO hicieron match)
  base_remanente <- desparecidos_fub_match_temp |> 
    filter(is.na(tipo_match))
  
  # 4.1.7 Limpiamos columnas
  # Nota: en 'base_remanente' hay filas no vacías en la columna 'indicadora_rnpdno'. Esto no es un error, ya que al haber hecho el join con 'comprimido_localizados' hubo coincidencias en el match fub+nombre pero como no cumplieron el requisito de que la fecha de desaparición fuese la misma NO cuentan como match.
  base_remanente <- base_remanente |> 
    select(-c(fub_rnpdno:clasificacion_des_rnpdno))
  
  # ----------------------------------------------------
  # 4.2. Match por CURP
  # ----------------------------------------------------
  
  # 4.2.1. Separamos la base remanente por CURP válida
  remanente_curp_valida <- base_remanente |> filter(indicadora_curp_limpia_valida == "valida")
  base_remanente_sin_curp <- base_remanente |> filter(indicadora_curp_limpia_valida == "invalida")

  # 4.2.2 Hacemos el JOIN solo con los de CURP válida de la remanente
  desparecidos_curp_match_temp <- remanente_curp_valida |>
    # En caso de que tengamos CURPS repetidas en BANCI ordenamos por fecha_inicio más reciente
    group_by(curp_limpia) |> 
    slice_max(order_by = fha_de_ini, n = 1, with_ties = FALSE) |> 
    ungroup() |> 
    left_join(
      comprimido_no_localizados_abr |> 
       # Solo consideramos la fecha más reciente de desaparición por CURP
        group_by(curp_victima_rnpdno) |> 
        slice_max(order_by = fecha_hechos_rnpdno, n = 1, with_ties = FALSE) |> 
        ungroup() |>
        select(curp_victima_rnpdno, indicadora_rnpdno, fub_rnpdno, 
              fecha_hechos_rnpdno, entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
              indicadora_carpeta_rnpdno, clasificacion_des_rnpdno), 
      by = c("curp_limpia" = "curp_victima_rnpdno")
    ) |>
    # Creamos la indicadora de match
    mutate(tipo_match = if_else(!is.na(indicadora_rnpdno), "match_curp", NA_character_))

    # 4.2.3 Hacemos el join con localizados
  desparecidos_curp_match_temp <- desparecidos_curp_match_temp |> 
    left_join(
      comprimido_localizados_abr |>
        select(curp_victima_rnpdno, fub_rnpdno, indicadora_rnpdno, fecha_hechos_rnpdno,
             entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
             indicadora_carpeta_rnpdno, clasificacion_des_rnpdno),
      by = c("curp_limpia" = "curp_victima_rnpdno"),
      suffix = c("", "_loc")
    ) |>
    mutate(
      # Calcular tolerancia para localizados
      tolerancia_fecha_desaparicion_temp = categorizar_tolerancia_fecha(
        fha_de_hchos, 
        fecha_hechos_rnpdno, 
        tipo_match = "localizados"
     ),
     # Match válido si cumple criterio de tolerancia
     tipo_match = case_when(
       !is.na(tipo_match) ~ tipo_match,
       tolerancia_fecha_desaparicion_temp %in% c("Exacta", "1-5 días", "6-15 días", "16-30 días") ~ "match_curp",
       TRUE ~ NA_character_
      ),
      # Diferencia en días
      diferencia_dias_desaparicion_temp = if_else(
       tipo_match == "match_curp" & !is.na(fha_de_hchos) & !is.na(fecha_hechos_rnpdno),
       as.numeric(fha_de_hchos - fecha_hechos_rnpdno),
       NA_real_
     )
    )
  
    # 4.2.4 Consolidar columnas
    desparecidos_curp_match_temp <- desparecidos_curp_match_temp |> 
    mutate(
      # Consolidar (priorizar no localizados que vienen del primer join sin sufijo)
    fub_rnpdno = coalesce(fub_rnpdno, fub_rnpdno_temp),  
    indicadora_rnpdno = coalesce(indicadora_rnpdno, indicadora_rnpdno_temp),
    fecha_hechos_rnpdno = coalesce(fecha_hechos_rnpdno, fecha_hechos_rnpdno_temp), 
    entidad_hechos_rnpdno = coalesce(entidad_hechos_rnpdno, entidad_hechos_rnpdno_temp),
    fecha_nacimiento_rnpdno = coalesce(fecha_nacimiento_rnpdno, fecha_nacimiento_rnpdno_temp),
    indicadora_carpeta_rnpdno = coalesce(indicadora_carpeta_rnpdno, indicadora_carpeta_rnpdno_temp),
    clasificacion_des_rnpdno = coalesce(clasificacion_des_rnpdno, clasificacion_des_rnpdno_temp),
    
    # Tolerancia final
    tolerancia_fecha_desaparicion = case_when(
      !is.na(indicadora_rnpdno) & is.na(indicadora_rnpdno_temp) ~ categorizar_tolerancia_fecha(
        fha_de_hchos, 
        fecha_hechos_rnpdno, 
        tipo_match = "desaparecidos"
      ),
      !is.na(indicadora_rnpdno_temp) ~ tolerancia_fecha_desaparicion,
      TRUE ~ NA_character_
    ),
    
    # Diferencia en días consolidada
    diferencia_dias_desaparicion = case_when(
      !is.na(indicadora_rnpdno) & is.na(indicadora_rnpdno_temp) & tipo_match == "match_curp" ~ 
        as.numeric(fha_de_hchos - fecha_hechos_rnpdno),
      !is.na(indicadora_rnpdno_temp) & tipo_match == "match_curp" ~ 
        diferencia_dias_desaparicion,
      TRUE ~ NA_real_
    )
  ) |>
  select(-ends_with("_temp"))
  
  # Si tipo_match == "match_curp" entonces variables_match = "CURP"
  desparecidos_curp_match_temp <- desparecidos_curp_match_temp |> 
    mutate(variables_match = case_when(
      tipo_match == "match_curp" ~ "CURP",
      TRUE ~ NA_character_
    ))
  
  # Crear verif_curp con valor de "COINCIDE" si tipo_match == "match_curp"
  desparecidos_curp_match_temp <- desparecidos_curp_match_temp |> 
    mutate(verif_curp = case_when(
      tipo_match == "match_curp" ~ "COINCIDE",
      TRUE ~ NA_character_
    ))
  
  # 4.2.5 Guardamos solo los que sí hicieron match
  desparecidos_curp_match <- desparecidos_curp_match_temp |>
    filter(tipo_match == "match_curp") 

  # 4.2.6. Agregamos los "NO match" de CURP a la base remanente
  base_remanente_sin_curp <- base_remanente_sin_curp |>
    bind_rows(
     desparecidos_curp_match_temp |> filter(is.na(tipo_match))
    )

  # 4.2.7. Limpiamos columnas
  base_remanente_sin_curp <- base_remanente_sin_curp |> 
    select(-c(fub_rnpdno, indicadora_rnpdno, fecha_hechos_rnpdno, 
            entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
            indicadora_carpeta_rnpdno, clasificacion_des_rnpdno,
            tolerancia_fecha_desaparicion, diferencia_dias_desaparicion))
  
  # ----------------------------------------------------
  # 4.3. Match por nombre completo
  # ----------------------------------------------------

  # 4.3.1. Separamos la base remanente por Nombre válido
  remanente_nombre_valido <- base_remanente_sin_curp |> filter(indicadora_nombre_valido == "valido")
  base_final_sin_match <- base_remanente_sin_curp |> filter(indicadora_nombre_valido == "invalido")

  # 4.3.2. Match con desaparecidos (criterio flexible de fecha)
  desparecidos_nombre_match_temp <- remanente_nombre_valido |>
  left_join(
    comprimido_no_localizados_abr |>
      select(nombre_completo_victima_rnpdno, fub_rnpdno, indicadora_rnpdno,
             fecha_hechos_rnpdno, entidad_hechos_rnpdno, fecha_nacimiento_rnpdno,
             indicadora_carpeta_rnpdno, clasificacion_des_rnpdno, sexo_rnpdno),
    by = c("nombre_completo_victima" = "nombre_completo_victima_rnpdno")
  ) |>
  mutate(
    entidad_reporta = stri_trans_general(str_to_title(entidad_reporta), id = "Latin-ASCII"),
    entidad_hechos_rnpdno = stri_trans_general(str_to_title(entidad_hechos_rnpdno), id = "Latin-ASCII"),
    fha_nac = as.Date(fha_nac),
    fecha_hechos_rnpdno = as.Date(fecha_hechos_rnpdno),
    fha_de_hchos = as.Date(fha_de_hchos)
  ) |> 
  mutate(
    # Calcular tolerancia para desaparecidos
    tolerancia_fecha_desaparicion_temp = categorizar_tolerancia_fecha(
      fha_de_hchos,
      fecha_hechos_rnpdno,
      tipo_match = "desaparecidos"
    ),
    
    # Criterio de match RELAJADO (hasta 1 año)
    tipo_match = case_when(
      # Caso 1: CON fecha de nacimiento válida
      # Fecha de nacimiento debe coincidir (5 días) Y fecha de hechos flexible (hasta 1 año)
      !is.na(fecha_nacimiento_rnpdno) & !is.na(fha_nac) & 
        abs(as.numeric(fecha_nacimiento_rnpdno - fha_nac)) <= 5 &
        tolerancia_fecha_desaparicion_temp %in% c("Exacta", "1-5 días", "6-10 días", 
                                                    "11-30 días (1 mes)", "2-5 meses", 
                                                    "6-12 meses") ~ "match_nombre",
      
      # Caso 2: Fecha de nacimiento NO coincide -> descartamos el match
      !is.na(fecha_nacimiento_rnpdno) & !is.na(fha_nac) & 
        abs(as.numeric(fecha_nacimiento_rnpdno - fha_nac)) > 5 ~ NA_character_,
      
      # Caso 3: SIN fecha de nacimiento válida
      # Usar entidad + tolerancia de fecha de hechos (hasta 1 año)
      (is.na(fecha_nacimiento_rnpdno) | is.na(fha_nac)) &
        tolerancia_fecha_desaparicion_temp %in% c("Exacta", "1-5 días", "6-10 días", 
                                                  "11-30 días (1 mes)", "2-5 meses", 
                                                  "6-12 meses") &
        !is.na(entidad_hechos_rnpdno) & !is.na(entidad_reporta) &
        entidad_hechos_rnpdno == entidad_reporta ~ "match_nombre",
      
      TRUE ~ NA_character_
    ),
    
    # Diferencia en días
    diferencia_dias_desaparicion_temp = if_else(
      tipo_match == "match_nombre" & !is.na(fha_de_hchos) & !is.na(fecha_hechos_rnpdno),
      as.numeric(fha_de_hchos - fecha_hechos_rnpdno),
      NA_real_
    )
  )

    # 4.3.3. Match con localizados
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |> 
    left_join(
      comprimido_localizados_abr |>
        select(nombre_completo_victima_rnpdno, fub_rnpdno, indicadora_rnpdno,
              fecha_hechos_rnpdno, fecha_nacimiento_rnpdno, entidad_hechos_rnpdno,
              indicadora_carpeta_rnpdno, clasificacion_des_rnpdno, sexo_rnpdno),
     by = c("nombre_completo_victima" = "nombre_completo_victima_rnpdno"),
      suffix = c("", "_loc")
    ) |> 
   mutate(
      entidad_hechos_rnpdno_loc = stri_trans_general(str_to_title(entidad_hechos_rnpdno_loc), id = "Latin-ASCII"),
      fecha_hechos_rnpdno = as.Date(fecha_hechos_rnpdno),
    
      # Tolerancia para localizados
      tolerancia_fecha_desaparicion_loc = categorizar_tolerancia_fecha(
       fha_de_hchos, 
        fecha_hechos_rnpdno, 
        tipo_match = "localizados"
      ),
    
    tipo_match = case_when(
      !is.na(tipo_match) ~ tipo_match,
      
      # Criterio localizados (30 días)
      !is.na(fecha_hechos_rnpdno) & !is.na(fha_de_hchos) & 
        tolerancia_fecha_desaparicion_loc %in% c("Exacta", "1-5 días", "6-15 días", "16-30 días") & (
          (!is.na(fecha_nacimiento_rnpdno_loc) & !is.na(fha_nac) & 
             abs(as.numeric(fecha_nacimiento_rnpdno_loc - fha_nac)) <= 5) |
          ((is.na(fecha_nacimiento_rnpdno_loc) | is.na(fha_nac)) &
             !is.na(entidad_hechos_rnpdno_loc) & !is.na(entidad_reporta) &
             entidad_hechos_rnpdno_loc == entidad_reporta)
        ) ~ "match_nombre",
      
      TRUE ~ NA_character_
    ),
    
    diferencia_dias_desaparicion_loc = if_else(
      tipo_match == "match_nombre" & !is.na(fha_de_hchos) & !is.na(fecha_hechos_rnpdno),
      as.numeric(fha_de_hchos - fecha_hechos_rnpdno),
      NA_real_
    )
  )

    # 4.3.4 Consolidar columnas
    if ("sexo_rnpdno_loc" %in% names(desparecidos_nombre_match_temp)) {
     desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
    mutate(sexo_rnpdno = coalesce(sexo_rnpdno, sexo_rnpdno_loc))
  }

    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
    mutate(
    fub_rnpdno = coalesce(fub_rnpdno, fub_rnpdno_loc),
    indicadora_rnpdno = coalesce(indicadora_rnpdno, indicadora_rnpdno_loc),
    fecha_hechos_rnpdno = coalesce(fecha_hechos_rnpdno, fecha_hechos_rnpdno_loc),
    entidad_hechos_rnpdno = coalesce(entidad_hechos_rnpdno, entidad_hechos_rnpdno_loc),
    fecha_nacimiento_rnpdno = coalesce(fecha_nacimiento_rnpdno, fecha_nacimiento_rnpdno_loc),
    indicadora_carpeta_rnpdno = coalesce(indicadora_carpeta_rnpdno, indicadora_carpeta_rnpdno_loc),
    clasificacion_des_rnpdno = coalesce(clasificacion_des_rnpdno, clasificacion_des_rnpdno_loc),
    tolerancia_fecha_desaparicion = coalesce(tolerancia_fecha_desaparicion_temp, tolerancia_fecha_desaparicion_loc),
    diferencia_dias_desaparicion = coalesce(diferencia_dias_desaparicion_temp, diferencia_dias_desaparicion_loc)
    ) |>
    select(-ends_with("_loc"), -ends_with("_temp"))
  
    # 4.3.4.1 Construir variables_match (NOMBRE 1.00 + coincidencias adicionales)
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(diff_dias_fecha_nac = abs(as.numeric(fecha_nacimiento_rnpdno - fha_nac)))

    # Base: todo match_nombre parte de "NOMBRE 1.00"
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(variables_match = case_when(
        tipo_match == "match_nombre" ~ "NOMBRE 1.00",
        TRUE ~ NA_character_
      ))

    # Fecha de nacimiento: coincide si difiere <= 5 días
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(
        verif_fecha_nac = if_else(
          tipo_match == "match_nombre" & !is.na(diff_dias_fecha_nac) & diff_dias_fecha_nac <= 5,
          paste0("COINCIDE", " (", diff_dias_fecha_nac, " DIAS)"),
          NA_character_
        ),
        variables_match = if_else(
          !is.na(verif_fecha_nac),
          paste0(variables_match, " + ", "FECHA NAC (+- 5 DIAS)"),
          variables_match
        )
      )

    # Entidad federativa: coincide si la entidad de hechos es la misma
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(
        verif_entidad = if_else(
          tipo_match == "match_nombre" & !is.na(entidad_hechos_rnpdno) & !is.na(entidad_reporta) &
            entidad_hechos_rnpdno == entidad_reporta,
          "COINCIDE",
          NA_character_
        ),
        variables_match = if_else(
          !is.na(verif_entidad),
          paste0(variables_match, " + ", "ENTIDAD FEDERATIVA"),
          variables_match
        )
      )

    # Sexo: coincide si el sexo es el mismo
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(
        verif_sexo = if_else(
          tipo_match == "match_nombre" & !is.na(sexo) & !is.na(sexo_rnpdno) &
            sexo == sexo_rnpdno,
          "COINCIDE",
          NA_character_
        ),
        variables_match = if_else(
          !is.na(verif_sexo),
          paste0(variables_match, " + ", "SEXO"),
          variables_match
        )
      ) |>
      select(-diff_dias_fecha_nac)
  
    # Crear columna verif_nombre con valor de "COINCIDE" si tipo_match == "match_nombre"
    desparecidos_nombre_match_temp <- desparecidos_nombre_match_temp |>
      mutate(verif_nombre = case_when(
        tipo_match == "match_nombre" ~ "COINCIDE",
        TRUE ~ NA_character_
      ))

    # 4.3.5 Seleccionar matches
    desparecidos_nombre_match <- desparecidos_nombre_match_temp |>
      filter(tipo_match == "match_nombre")

    # 4.3.6 Actualizar base sin match
    base_final_sin_match <- base_final_sin_match |>
      bind_rows(
        desparecidos_nombre_match_temp |> filter(is.na(tipo_match))
     )

    # 4.3.7 Limpiar columnas
    base_final_sin_match <- base_final_sin_match |> 
      select(-c(fub_rnpdno, indicadora_rnpdno, fecha_hechos_rnpdno, 
                entidad_hechos_rnpdno, fecha_nacimiento_rnpdno, 
                indicadora_carpeta_rnpdno, clasificacion_des_rnpdno,
               tolerancia_fecha_desaparicion, diferencia_dias_desaparicion))
  

  # ----------------------------------------------------
  # 5. Bases consolidadas
  # ----------------------------------------------------
  
   # 5.1. Agregamos los que NO matchearon a la base final de "Sin Match"
    # base_final_sin_match <- base_final_sin_match |>
    # bind_rows(
    #   desparecidos_nombre_match_pre |>
    #     filter(is.na(tipo_match)) 
    # )
  
  base_final_sin_match$tolerancia_fecha_desaparicion <- NA_character_
  base_final_sin_match$diferencia_dias_desaparicion <- NA_real_
  
  # 5.2. Eliminamos columnas innecesarias
  base_final_sin_match <- base_final_sin_match |> 
  select(-c(fub_rnpdno_temp, indicadora_rnpdno_temp, fecha_hechos_rnpdno_temp, 
            entidad_hechos_rnpdno_temp, fecha_nacimiento_rnpdno_temp, 
            indicadora_carpeta_rnpdno_temp, clasificacion_des_rnpdno_temp)) |> 
  mutate(indicadora_rnpdno = NA_character_)
  
  message("El número de personas desaparecidas con registro en BANCI pero no en RNPDNO, que tienen identidad válida son: ", comma(nrow(base_final_sin_match)), "\n")
  
  # 5.2 Añadir los casos sin idéntidad válida a base_final_sin_match
  # Partimos de la base "subeR_no_localizados_sin_identidad_valida"
  
  base_final_sin_match_final <- base_final_sin_match |> 
    bind_rows(subeR_no_localizados_sin_identidad_valida)
  
  numero_base_final_sin_match_final <- base_final_sin_match_final |> 
    nrow()
  
  message("La cantidad de personas desaparecidas, con identidad válida e inválida, que están en BANCI pero no en RNPDNO es de: ", comma(numero_base_final_sin_match_final), "registros",
      "\n")

  # ---- Base con matches ----
  base_datos_encontrados <- bind_rows(
  desparecidos_fub_match,
  desparecidos_curp_match,
  desparecidos_nombre_match)
  
  # Eliminar repetidos con fub del RNPDNO
  base_datos_encontrados <- base_datos_encontrados |> 
    group_by(fub_rnpdno) |> 
    filter(row_number() == 1 | is.na(fub_rnpdno)) |> 
    ungroup()
  
  numero_base_datos_encontrados <- base_datos_encontrados |>
    nrow()
  
  message("En total tenemos ", comma(numero_base_datos_encontrados), " registros en BANCI y RNPDNO (intersección)\n")

  # ————————————————————————————————————————————————————————— #
  # Modificaciones a Base_BANCI_con_match_con_RNPDNO (base_datos_encontrados) para asegurar compatibilidad con datos de matcheo de carpetas tipo fuzzy (Ariadna) -----
  # ————————————————————————————————————————————————————————— #

  # Partimos de base_datos_encontrados

  # Columnas estáticas
  base_datos_encontrados$evaluacion_match = "DEFINITIVO"
  base_datos_encontrados$score = 100
  base_datos_encontrados$verif_carpeta = "NO APLICA"
  base_datos_encontrados$'_id_banci' = NA
  base_datos_encontrados$'_id_rnpdno' = NA

  # Cuando verif_nombre sea NA entonces asignar "NO" a verif_nombre
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(verif_nombre = if_else(is.na(verif_nombre), "NO APLICA", verif_nombre))

  # Cuando verif_curp sea NA entonces asignar "NO APLICA"
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(verif_curp = if_else(is.na(verif_curp), "NO APLICA", verif_curp))

  # Cuando verif_entidad sea NA entonces asignar "NO APLICA"
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(verif_entidad = if_else(is.na(verif_entidad), "NO APLICA", verif_entidad))

  # Cuando verif_sexo sea NA entonces asignar "NO APLICA"
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(verif_sexo = if_else(is.na(verif_sexo), "NO APLICA", verif_sexo))

  # Cuando verif_fecha_nac sea NA entonces asignar "NO APLICA"
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(verif_fecha_nac = if_else(is.na(verif_fecha_nac), "NO APLICA", verif_fecha_nac))

  # Cambio de nombres de columnas:
  # carpeta_investigacion_banci = ntra_ci
  base_datos_encontrados <- base_datos_encontrados |> 
    rename(carpeta_investigacion_banci = ntra_ci)

  # Cuando diferencia_dias_desaparicion tenga un valor abosoluto menor o igual a 10 entonces asignar la columna fecha_hechos_status con el valor de 
  # "COINCIDE" y en diferencia_dias_desaparicion hacer paste0("(", abs(diferencia_dias_desaparicion), " DIAS)")
  # En caso contrario dejar "DIFIERE" y en diferencia_dias_desaparicion igual hacer paste0("(", abs(diferencia_dias_desaparicion), " DIAS)")
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(
      fecha_hechos_status = if_else(abs(diferencia_dias_desaparicion) <= 10, "COINCIDE", "DIFIERE"),
      fecha_hechos_status = paste0(fecha_hechos_status, " (", abs(diferencia_dias_desaparicion), " DIAS)"),
    )

  # Si str_detect(fecha_hechos_status, "COINCIDE") entonces en variables_match agregar "+FECHA DE HECHOS (+- 10 DIAS)"
  base_datos_encontrados <- base_datos_encontrados |> 
    mutate(variables_match = if_else(str_detect(fecha_hechos_status, "COINCIDE"), paste0(variables_match, "; " , "+FECHA DE HECHOS (+- 10 DIAS)"), variables_match))
  
  # Paso final: crear una lista con los insumos generados
  lista_con_insumos = list(
    Base_BANCI_sin_match_con_RNPDNO = base_final_sin_match_final,
    Base_BANCI_con_match_con_RNPDNO = base_datos_encontrados
  )
}

# ————————————————————————————————————————————————————————— #
# Función que guarda las bases de match entre BANCI y RNPDNO -------
# ————————————————————————————————————————————————————————— #

#' Guardar en disco las bases de matching entre BANCI y RNPDNO
#'
#' Extrae los dos data frames de `lista_con_insumos` (ver
#' [funcion_de_match_BANCI_y_RNPDNO()]) y los guarda como archivos `.RData`
#' dentro de una carpeta con la fecha del día
#' (`RNPDNO/output/cruces_banci_rnpdno/cruces_banci_rnpdno_DDMMYYYY`), creando
#' la carpeta si no existe.
#'
#' @param lista_con_insumos Lista con los elementos
#'   `Base_BANCI_sin_match_con_RNPDNO` y `Base_BANCI_con_match_con_RNPDNO`, tal
#'   como la regresa [funcion_de_match_BANCI_y_RNPDNO()].
#' @return No regresa ningún valor útil (el `NULL` implícito de `save()`); su
#'   efecto es guardar dos archivos `.RData` en disco, con un `message()` que
#'   confirma si la carpeta de destino se creó o ya existía.
guardar_bases_match_BANCI_RNPDNO <- function(lista_con_insumos) {

  # Definimos objetos de base sin match (base_final_sin_match) y base con match (base_datos_encontrados)
  Base_BANCI_sin_match_con_RNPDNO <- lista_con_insumos["Base_BANCI_sin_match_con_RNPDNO"] |> 
    map_dfr(.f = identity)

  Base_BANCI_con_match_con_RNPDNO <- lista_con_insumos["Base_BANCI_con_match_con_RNPDNO"] |> 
    map_dfr(.f = identity)

  # Guardar cruces Base_BANCI_sin_match_con_RNPDNO y Base_BANCI_con_match_con_RNPDNO
  fecha_actual <- today()

  string_fecha <- paste0(
      substr(fecha_actual, 9, 10),
      substr(fecha_actual, 6, 7),
      substr(fecha_actual, 1, 4)
    ) 

  # Crear carpeta si no existe
  carpeta <- here::here("RNPDNO",
                            "output",
                            "cruces_banci_rnpdno",
                            paste0("cruces_banci_rnpdno_",string_fecha))

  if (!dir.exists(carpeta)) {
    if (dir.create(carpeta , recursive = TRUE)) {
      message("Carpeta creada: ", carpeta)
    } else {
      message("No se pudo crear carpeta: ", carpeta)
    }
  } else{
    message("La carpeta ", carpeta, " ya existe.")
  }

  save(Base_BANCI_sin_match_con_RNPDNO , file = paste0(carpeta,"/Base_BANCI_sin_match_con_RNPDNO.RData"))

  save(Base_BANCI_con_match_con_RNPDNO , file = paste0(carpeta, "/Base_BANCI_con_match_con_RNPDNO.RData"))
}

# ————————————————————————————————————————————————————————— #
# Función que hace genera la base final con dos modalidades posibles ----
# ————————————————————————————————————————————————————————— #

# Las modalidades posibles son:

# 1. Unión (unión entre todo RNPDNO y todos los NO localizados de BANCI desde la fecha de corte inyectada en la función, diferenciado si se trata de un registro en la intersección o que solo pertenece a la BANCI)

# 2. Intersección (RNPDNO con intersección de personas NO localizadas de  BANCI, es decir, solo aquellos registros que hacen match entre ambas bases y todos aquellos en RNPDNO)

#' Construir la base final del "comprimido" (intersección o unión BANCI-RNPDNO)
#'
#' A partir del RNPDNO (`comprimido`) y los resultados del matching con BANCI
#' (ver [funcion_de_match_BANCI_y_RNPDNO()]), reclasifica `dependencia_origen`,
#' `indicadora_carpeta` y `sub_clasificacion`, actualiza `registros_localizados`
#' con las nuevas localizaciones detectadas en `comprimido` y, si
#' `tipo_conjunto == "union"`, además le da forma a
#' `Base_BANCI_sin_match_con_RNPDNO` (entidades, municipios, edad, grupo
#' etario, UUID interno tipo "BANCI-...") y la agrega a `comprimido`.
#'
#' @param Base_BANCI_con_match_con_RNPDNO Data frame de BANCI con match en el
#'   RNPDNO, tal como lo regresa [funcion_de_match_BANCI_y_RNPDNO()].
#' @param Base_BANCI_sin_match_con_RNPDNO Data frame de BANCI sin match en el
#'   RNPDNO, tal como lo regresa [funcion_de_match_BANCI_y_RNPDNO()]. Solo se
#'   usa para construir la base final cuando `tipo_conjunto == "union"`.
#' @param comprimido Data frame del RNPDNO ("comprimido"), con columnas como
#'   `fub`, `clasificacion_des`, `indicadora_indicio_de_vida`,
#'   `indicadora_curp_valida`, `dependencia_origen`,
#'   `dependencia_origen_reclasificado` y `anio_hechos_modificada`.
#' @param registros_localizados Data frame de registros administrativos de
#'   personas localizadas (confrontas manuales, sin incluir coincidencias de
#'   la PUI), con al menos las columnas `fub` y `clasificacion_des`. Se
#'   actualiza dentro de la función cruzando con `comprimido` para detectar
#'   nuevas localizaciones.
#' @param tipo_conjunto Character. "interseccion" (default) deja `comprimido`
#'   solo con el RNPDNO reclasificado; "union" además agrega los registros de
#'   `Base_BANCI_sin_match_con_RNPDNO` que no tienen contraparte en el RNPDNO.
#' @return Lista con dos elementos: `comprimido` (data frame final, según
#'   `tipo_conjunto`) y `registros_localizados` (actualizado con las
#'   localizaciones detectadas durante la ejecución).
#' @note Este valor de retorno es una lista, no un data frame; quien llame a
#'   esta función debe extraer `$comprimido` explícitamente (así lo hace
#'   [tratamiento_banci_rnpdno()], que descarta el
#'   `$registros_localizados` actualizado para mantener compatibilidad con los
#'   scripts existentes que esperan recibir un data frame).
funcion_base_final <- function(
  Base_BANCI_con_match_con_RNPDNO,
  Base_BANCI_sin_match_con_RNPDNO,
  comprimido,
  registros_localizados,
  tipo_conjunto = "interseccion" # La otra opción es "union"
) {

  # --- Bloque común a ambas modalidades --- #

  # Pegar Base_BANCI_con_match_con_RNPDNO con comprimido_nuevo para identificar aquellos casos que sí tienen datos pero no tienen registro administrativo 
  comprimido <- comprimido |> 
      left_join(
        Base_BANCI_con_match_con_RNPDNO |> 
          mutate(indicadora_carpeta_banci = "con carpeta banci") |> 
          select(fub_rnpdno, indicadora_carpeta_banci),
        by = c("fub" = "fub_rnpdno")
      )
    
  # Obtener fecha máxima de fha_de_hchos de Base_BANCI_con_match_con_RNPDNO
  fecha_maxima_hcho <- max(Base_BANCI_con_match_con_RNPDNO$fha_de_hchos, na.rm = TRUE)
    
  message("El número de personas desaparecidas que tienen registro en BANCI y RNPDNO (intersección) es de: ", comma(nrow(Base_BANCI_con_match_con_RNPDNO)), "\n")
  message("La fecha máxima de desaparición (fha_de_hchos) en la base de personas desaparecidas con match entre BANCI y RNPDNO es: ", format(fecha_maxima_hcho, "%d de %B del %Y"), "\n")

  # Cuando indicadora_carpeta_banci es "con carpeta banci" entonces creamos columna origen_categoria_union con el valor de "Intersección banci y rnpdno", en caso contrario, asignar el valor de "Solo RNPNDO, sin intersección"
  comprimido <- comprimido |> 
    mutate(origen_categoria_union = case_when(
      indicadora_carpeta_banci == "con carpeta banci" ~ "Intersección BANCI y RNPDNO",
      TRUE ~ "Solo RNPDNO, sin intersección"
    ))

  # Si hay casos donde indicadora_carpeta_banci es "con carpeta banci" entonces definir que dependencia_origen_reclasificado == "Fiscalía con carpeta de investigación"
  comprimido <- comprimido |> 
    rename(dependencia_origen_original = dependencia_origen) |> 
    rename(dependencia_origen = dependencia_origen_reclasificado) |>
    mutate(
        dependencia_origen = case_when(
          indicadora_carpeta_banci == "con carpeta banci" ~ "Fiscalía con carpeta de investigación",
          TRUE ~ dependencia_origen
      )
      )
    
  # Consolidad columna de "indicadora_carpeta" con la siguiente regla: si indicadora_carpeta_banci es "con carpeta banci" entonces indicadora_carpeta == "Con carpeta" luego si TRUE ~ indicadora_carpeta y eliminamos la columna de "indicadora_carpeta_banci"
  comprimido <- comprimido |> 
    mutate(
    indicadora_carpeta = case_when(
        indicadora_carpeta_banci == "con carpeta banci" ~ "Con carpeta",
        TRUE ~ indicadora_carpeta
      )
    ) |> 
    select(-indicadora_carpeta_banci)

  # Actualizamos datos de expediente_reclasif
  comprimido <- comprimido |> 
    mutate(
      expediente_reclasif = case_when(
        indicadora_carpeta == "Con carpeta" ~ "carpeta de investigacion",
        indicadora_carpeta == "Sin carpeta" ~ "expediente genérico",
        TRUE ~ expediente_reclasif
      )
  )
  
  # Limpiamos casos de "SE DESCONOCE" y renombramos variable de dependencia de origen. Convención implementada según orden de Mariano Muñoz
  comprimido <- comprimido |> 
    mutate(
    dependencia_origen = case_when(
        dependencia_origen == "SE DESCONOCE" ~ "Portal",
        TRUE ~ dependencia_origen
      )
    )
  
  # Creamos la sub_clasificación de comprimido:
  comprimido <- comprimido |> 
    mutate(
    sub_clasificacion = case_when(

        clasificacion_des %in% "Pendientes" & indicadora_indicio_de_vida == "sin registro administrativo" ~ "Sin datos",

        clasificacion_des != "Localizados" &
        indicadora_indicio_de_vida == "con registro administrativo" ~ "Desaparecido con registro administrativo",

        clasificacion_des != "Localizados" &
        indicadora_curp_valida == "valida" & indicadora_indicio_de_vida != "con registro administrativo" ~ "Desaparecido sin coincidencia con registro administrativo",

        clasificacion_des %in% "Localizados" ~ "Desaparecidos que fueron localizados del periodo",
        TRUE ~ "Otros casos"
        )
      )
  
    # Validar que nadie se encuentre en "Otros casos"
    if(any(comprimido$sub_clasificacion == "Otros casos")) {
      warning("¡Atención! Hay casos clasificados como 'Otros casos' en sub_clasificacion. Revisa la base de datos para identificar por qué.\n")
    } else {
      message("¡Perfecto! No hay casos en 'Otros casos'.\n")
    }
    
    # Avisar los resultados de sub_clasificación desde 2006
    # Desaparecidos desde 2006
    desaparecidos_2006 <- comprimido |> 
      filter(clasificacion_des != "Localizados") |>
      filter(anio_hechos_modificada >= 2006) 

    message("El número de desaparecidos desde 2006 Sin datos es de:", comma(nrow(desaparecidos_2006 |> filter(sub_clasificacion == "Sin datos"))), ".\n")
    message("El número de desaparecidos desde 2006 con registro administrativo es de:", comma(nrow(desaparecidos_2006 |> filter(sub_clasificacion == "Desaparecido con registro administrativo"))), ".\n")
    message("El número de desaparecidos desde 2006 sin coincidencia con registro administrativo es de:", comma(nrow(desaparecidos_2006 |> filter(sub_clasificacion == "Desaparecido sin coincidencia con registro administrativo"))), ".\n")
  
    # Actualizamos localizaciones de registros_localizados
    ## Debemos comprobar si hay nuevas personas desaparecidas con indicio que se han localizado
    registros_localizados <- registros_localizados |>
    left_join(comprimido |> select(fub, clasificacion_des_actualizado = clasificacion_des, fecha_hechos_modificada), by = "fub")

    # Ver aquellas personas con clasificacion_des como NO localizados y con clasificacion_des_actualizado como Localizados
    registros_localizados <- registros_localizados |>
    filter(clasificacion_des_actualizado == "Localizados" | clasificacion_des == "Localizados")

    registros_localizados <- registros_localizados |>
    mutate(
     clasificacion_des = coalesce(clasificacion_des_actualizado, clasificacion_des)
    ) |> select(-clasificacion_des_actualizado)

    message("El número de registros localizados con la clasificación actualizada es de:", comma(nrow(registros_localizados)), ".\n")
  
    # Cruzamos con registros_localizados mediante fub, creamos indicadora_indicio_de_vida_localizados
    comprimido <- comprimido |> 
      left_join(
        registros_localizados |> mutate(indicadora_indicio_de_vida_localizados = "con registro administrativo") |> select(fub, indicadora_indicio_de_vida_localizados),
        by = "fub"
      ) |> 
      mutate(
        indicadora_indicio_de_vida_localizados = case_when(
          is.na(indicadora_indicio_de_vida_localizados) ~ "sin registro administrativo",
          TRUE ~ indicadora_indicio_de_vida_localizados
        )
      )
    

    # ---- Bloque de unión: aregar registros de solo BANCI ------ #
    if (tipo_conjunto == "union") {

    # 2. Partimos de la base sin match entre RNPDNO y BANCI:  Base_BANCI_sin_match_con_RNPDNO
      
    # 2.2 Añadimos variables nuevas necesarias para la base final (de la siguiente sección)
      
      # a. expediente
      Base_BANCI_sin_match_con_RNPDNO$expediente <- "carpeta de investigacion"
  
      # b. dependencia de origen
      Base_BANCI_sin_match_con_RNPDNO$dependencia_de_origen <- "Fiscalía con carpeta de investigación"

      # c. indicador de tipo de dato
      Base_BANCI_sin_match_con_RNPDNO$origen_categoria_union <- "Solo BANCI, sin intersección"

      # d. reclasificacion de los registros administrativos
      # No hay personas desaparecidas en solo BANCI de las que se hayan realizado confrontas
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(indicadora_indicio_de_vida = "sin registro administrativo")

      # e. clasificación de la persona desaparecida
    # CONSIDERACIÓN IMPORTANTE: como se mencionó en la primera parte del script, la clasificación "con datos" es arbitraria. Para el caso de los registros de la BANCI se supone que al tener los datos de la carpeta de investigación es suficiente para rastrear el caso de desaparición. Es decir, no es necesario contar con una CURP válida para contar el registro como válido.
    Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
      mutate(
         sub_clasificacion = "Desaparecido sin coincidencia con registro administrativo") # Es decir, desaparecido "con datos"
      
      # 2.3 Crear identificador interno en formato UUID por compatibilidad de columnas
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(
        fub = paste0("BANCI-", substr(uuid::UUIDgenerate(n = n()), 1, 31))
      )

      # 2.4 Limpiar entidad_nacimiento
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(entidad_nacimiento = str_to_sentence(entidad_nacimiento))

      entidades_unicas_nacimiento_banci <- Base_BANCI_sin_match_con_RNPDNO |> 
        select(entidad_nacimiento) |> 
        distinct() |> 
        arrange(entidad_nacimiento) |> unique()

      # Entidades válidas después de corrección (las que sí están en el catálogo)
      entidades_validas <- catalogo_estados_inegi$nom_ent

      directorio_de_correcciones <- 
        c(
          "Baja california" = "Baja California",
          "Baja california norte" = "Baja California",
          "Belice|No identificado|Null|Sd|Se desconoce|Sin dato" = NA_character_, # Se elimina porque no es una entidad de nacimiento válida en México
          "Cdmx" = "Ciudad de México",
          "Ciudad de mexico" = "Ciudad de México",
          "Ciudad de méxico" = "Ciudad de México",
          "Huatusco veracruz" = "Veracruz", # Se corrige porque no es una entidad de nacimiento válida, se asigna Veracruz que es la entidad correspondiente al municipio de Huatusco
          "Mexico" = "México",
          "Michoacan de ocampo" = "Michoacán",
          "Michoacán de ocampo" = "Michoacán",
          "Quintana roo" = "Quintana Roo",
          "Quntana roo" = "Quintana Roo",
          "San luis potosi" = "San Luis Potosí",
          "San luis potosí" = "San Luis Potosí",
          "Veracruz de ignacio de la llave" = "Veracruz",
          "Ciudad De Mexico" = "Ciudad de México",
          "San Luis Potosi" = "San Luis Potosí",
          "Mexico" = "México",
          "Michoacan" = "Michoacán"
        )
      
      # Aplicar correcciones secuencialmente
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(
          entidad_nacimiento = reduce(
      names(directorio_de_correcciones),
      .init = entidad_nacimiento,
      function(col, patron) {
        if_else(
          str_detect(col, regex(patron, ignore_case = FALSE)),
          directorio_de_correcciones[[patron]],
          col
        )
      }
    )
  )
      # Detectar entidades no corregidas (no vacías, no NA, no en catálogo)
      entidades_no_corregidas_entidad_nacimiento <- Base_BANCI_sin_match_con_RNPDNO |> 
        filter(!is.na(entidad_nacimiento) & entidad_nacimiento != "" & !entidad_nacimiento %in% entidades_validas) |> 
        distinct(entidad_nacimiento) |>
        pull(entidad_nacimiento)

    if (length(entidades_no_corregidas_entidad_nacimiento) > 0) {
      message("Las entidades de 'entidad_nacimiento' no corregidas son: ", paste(entidades_no_corregidas_entidad_nacimiento, collapse = ", "))
    } else {
      message("Todas las entidades de 'entidad_nacimiento' fueron corregidas correctamente.")
    }
      
      # Pegar con catalogo_estados_inegi para obtener cve_ent_nacimiento
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        left_join(catalogo_estados_inegi |> select(nom_ent, cve_ent_nacimiento = cve_ent), by = c("entidad_nacimiento" = "nom_ent"))

      # 2.5 Limpiar entidad_reporta
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(entidad_reporta = str_to_title(entidad_reporta))

        entidades_unicas_reporta_banci <- Base_BANCI_sin_match_con_RNPDNO |> 
          select(entidad_reporta) |> 
          distinct() |> 
          arrange(entidad_reporta) |> unique()
      
      # Aplicar correcciones secuencialmente
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(
          entidad_reporta = reduce(
            names(directorio_de_correcciones),
            .init = entidad_reporta,
            function(col, patron) {
              if_else(
                str_detect(col, regex(patron, ignore_case = FALSE)),
                directorio_de_correcciones[[patron]],
                col
              )
            }
          ))
      
      # Pegar con catalogo_estados_inegi para obtener cve_ent 
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        left_join(catalogo_estados_inegi |> select(nom_ent, cve_estado_desaparicion = cve_ent), by = c("entidad_reporta" = "nom_ent"))

      
      # Detectar entidades no corregidas (no vacías, no NA, no en catálogo)
      entidades_no_corregidas_entidad_reporta <- Base_BANCI_sin_match_con_RNPDNO |> 
        filter(!is.na(entidad_reporta) & entidad_reporta != "" & !entidad_reporta %in% entidades_validas) |> 
        distinct(entidad_reporta) |>
        pull(entidad_reporta)

    if (length(entidades_no_corregidas_entidad_reporta) > 0) {
      message("Las entidades de 'entidad_reporta' no corregidas son: ", paste(entidades_no_corregidas_entidad_reporta, collapse = ", "))
    } else {
      message("Todas las entidades de 'entidad_reporta' fueron corregidas correctamente.")
    }
      
      # 2.6 Limpiar nom_mun_hchos y id_mun_hchos

      # Hacer mayúsculas todas las letras de nom_mun_hchos
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(nom_mun_hchos = toupper(nom_mun_hchos))

      # Crear columna temporal de entidad_reporta en mayúsculas 
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(
          entidad_reporta_temp = toupper(entidad_reporta)
        )
      
      # Crear del catalogo_municipios_inegi unas columnas de nom_ent y nom_mun temporales en mayúsculas para hacer el join
      catalogo_municipios_inegi <- catalogo_municipios_inegi |> 
        clean_names() |>
        mutate(
          nom_ent_temp = toupper(nom_ent),
          nom_mun_temp = toupper(nom_mun)
        )
      
      # Unir con catalogo_municipios_inegi para obtener cve_ent y cve_mun
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        left_join(
          catalogo_municipios_inegi |> select(nom_ent_temp, nom_mun_temp, cvegeo, cve_mun), 
          by = c("entidad_reporta_temp" = "nom_ent_temp", "nom_mun_hchos" = "nom_mun_temp")
        ) |> 
        rename(cve_municipio_desaparicion = cve_mun,
        cvegeo_desaparicion = cvegeo) |> 
        select(-entidad_reporta_temp)

      # Detectar casos con cve_municipio_desaparicion NA pero con id_mun_hchos no NA

      # Si id_mun_hchos es no numérico o tiene menos de 1 dígito hay o ese dígito es 0 hay que hacerlo NA porque no es un código de municipio válido
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(id_mun_hchos = if_else(!str_detect(id_mun_hchos, "^\\d{1,}$") | str_length(id_mun_hchos) < 1 | id_mun_hchos == "0", NA_character_, id_mun_hchos))
      
      # id_mun_hchos debe tener formato de 3 dígitos, si tiene menos de 3 dígitos, rellenar con ceros a la izquierda
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(id_mun_hchos = str_pad(id_mun_hchos, width = 3, side = "left", pad = "0"))

      # crear cvegeo_temp: unirmos id_mun_hechos con cve_estado_desaparicion y luego pegamos con catalogo_municipios_inegi para obtener cvegeo y cve_mun, luego eliminamos la columna temporal de cvegeo_temp
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(cvegeo_temp = paste0(cve_estado_desaparicion, id_mun_hchos)) |> 
        left_join(
          catalogo_municipios_inegi |> select(cvegeo, cve_mun), 
          by = c("cvegeo_temp" = "cvegeo")
        ) |> 
        rename(cve_municipio_desaparicion_temp = cve_mun)

      # cvegeo_temp solo es válido si cve_municipio_desaparicion_temp es no NA entonces si cve_municipio_desaparicion_temp es NA entonces cvegeo_temp también debe ser NA porque no es un código de municipio válido
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(cvegeo_temp = if_else(is.na(cve_municipio_desaparicion_temp), NA_character_, cvegeo_temp))
      
      # Consolidar cve_municipio_desaparicion: si cve_municipio_desaparicion no es NA, conservarlo, pero si es NA entonces asignar el valor de cve_municipio_desaparicion_temp. Hacemos coalesce
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(cve_municipio_desaparicion = coalesce(cve_municipio_desaparicion, cve_municipio_desaparicion_temp)) |> 
        select(-cve_municipio_desaparicion_temp)

      # Consolidar cvegeo_desaparicion: si cvegeo_desaparicion no es NA conservarlo, pero si es NA entonces asignar el valor de cvegeo_temp. Hacemos coalesce
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(cvegeo_desaparicion = coalesce(cvegeo_desaparicion, cvegeo_temp)) |> 
        select(-cvegeo_temp)

      # 2.8 Crear fecha_hechos_modificada = fecha_hechos fictica
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(fecha_hechos_modificada = fha_de_hchos)

      # Crear anio_hechos y anio_hechos_modificada
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(anio_hechos = year(fha_de_hchos),
               anio_hechos_modificada = year(fecha_hechos_modificada))
      
      # Crear anio_mes_hechos_modificada nada más. Hacer que todos tengan el día 01 para evitar problemas de formato
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(anio_mes_hechos_modificada = make_date(year(fecha_hechos_modificada), month(fecha_hechos_modificada), 1))

      # 2.9 Crear variable de edad_al_momento_desaparicion as.integer(difftime(fha_de_hchos, fha_nac, units = "days") / 365.25)
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(edad_al_momento_desaparicion = as.integer(difftime(fha_de_hchos, fha_nac, units = "days") / 365.25))

      # Crear una variable de grupo etario
      Base_BANCI_sin_match_con_RNPDNO <- Base_BANCI_sin_match_con_RNPDNO |> 
        mutate(
      grupo_etario = case_when(
      is.na(edad_al_momento_desaparicion)                              ~ NA_character_,
      edad_al_momento_desaparicion < 0                                 ~ NA_character_, # edades imposibles
      edad_al_momento_desaparicion <= 11                               ~ "Niñez (0-11)",
      edad_al_momento_desaparicion <= 17                               ~ "Adolescencia (12-17)",
      edad_al_momento_desaparicion <= 29                               ~ "Madurez (18-29)",
      edad_al_momento_desaparicion <= 59                               ~ "Adultez (30-59)",
      edad_al_momento_desaparicion >= 60                               ~ "Adulto o adulta mayor (60+)",
      TRUE                                                             ~ NA_character_
    ),
    # factor ordenado para que los gráficos respeten el orden correcto
    grupo_etario = factor(grupo_etario, levels = c(
      "Niñez (0-11)",
      "Adolescencia (12-17)",
      "Madurez (18-29)",
      "Adultez (30-59)",
      "Adulto o adulta mayor (60+)"
    ))
  )
      
    # 2.10 Seleccionar variables compatibles con comprimido y modificar otras
    Base_BANCI_sin_match_con_RNPDNO <-
    Base_BANCI_sin_match_con_RNPDNO |> 
      mutate(clasificacion_des = "Desaparecidos",
      estatus = "DESAPARECIDA",
      indicadora_carpeta = "Con carpeta",
      expediente_reclasif = "carpeta de investigacion",
      dependencia_origen_reclasificado = "Fiscalía con carpeta de investigación",
      origen_categoria_union = "Solo BANCI, sin intersección",
      sub_clasificacion = "Desaparecido sin coincidencia con registro administrativo",
      indicadora_indicio_de_vida = "sin registro administrativo",
             fha_nac = as.Date(fha_nac),
             fha_de_hchos = as.Date(fha_de_hchos)) |> 
      select(
        fub,
        estatus,
        curp_victima = curp,
        nombre_vic = nombres,
        primerapellido_vic = primer_apellido,
        segundoapellido_vic = segundo_apellido,
        sexo,
        fechanacimiento = fha_nac,
        idestadonacimiento = cve_ent_nacimiento,
        nacionalidad = nacional,
        cve_estado_desaparicion,
        cve_municipio_desaparicion,
        fechahechos = fha_de_hchos,
        delito_desaparicion = dto,
        expediente = ntra_ci,

        clasificacion_des,
        entidad_reporta,
        clasificacion_des,
        fecha_hechos_modificada,
        fecha_hechos_modificada,
        anio_hechos,
        anio_hechos_modificada,
        anio_mes_hechos_modificada,indicadora_carpeta,
        expediente_reclasif,
        dependencia_origen_reclasificado,
         origen_categoria_union,
         sub_clasificacion,
         indicadora_indicio_de_vida,
         indicadora_curp_valida = indicadora_curp_limpia_valida,

         estado_desaparicion = entidad_reporta,
         entidad_nacimiento_nom = entidad_nacimiento,
         cvegeo_desaparicion,
         municipio_desaparicion = nom_mun_hchos,
         edad_al_momento_desaparicion,
         grupo_etario)
      
      # 2.11 Pegar con comprimido para tener la base final de "unión"
      comprimido <- comprimido |> 
        bind_rows(Base_BANCI_sin_match_con_RNPDNO)

    }
  
  # ---- Bloque de intersección: agregar solo los casos que hacen match entre BANCI y RNPDNO ------ #
  # Return único al final que contiene tanto la base de intersección como la base de unión para evitar confusiones
  return(list(comprimido = comprimido, registros_localizados = registros_localizados))
}

# ————————————————————————————————————————————————————————— #
# Función final para generar el comprimido final -------
# ————————————————————————————————————————————————————————— #

#' Orquestar el flujo completo de matching y generación del comprimido final
#'
#' Función "wrapper" de alto nivel: si `nueva_BANCI = TRUE`, limpia BANCI (ver
#' [funcion_limpieza_banci()]) y ejecuta el matching contra el RNPDNO (ver
#' [funcion_de_match_BANCI_y_RNPDNO()]), opcionalmente guardando esas bases
#' intermedias (ver [guardar_bases_match_BANCI_RNPDNO()]); si
#' `nueva_BANCI = FALSE`, usa bases de matching ya calculadas. En ambos casos
#' termina generando la base final con [funcion_base_final()].
#'
#' @param subeR Data frame crudo de BANCI/SubeR. Requerido si
#'   `nueva_BANCI = TRUE`.
#' @param comprimido Data frame del RNPDNO ("comprimido"). Siempre requerido.
#' @param nueva_BANCI Lógico. TRUE para recalcular el matching desde `subeR` y
#'   `comprimido`; FALSE para reutilizar `Base_BANCI_con_match_con_RNPDNO` y
#'   `Base_BANCI_sin_match_con_RNPDNO` ya calculadas. Default: FALSE.
#' @param limpiar_BANCI Lógico. Si `nueva_BANCI = TRUE`, indica si `subeR` debe
#'   pasar primero por [funcion_limpieza_banci()] (TRUE) o si solo se filtra a
#'   "No localizada" desde `fecha_inicio_BANCI` (FALSE). Default: TRUE.
#' @param fecha_inicio_BANCI Fecha (character, "YYYY-MM-DD") desde la cual se
#'   consideran los casos de BANCI. Default: "2025-08-01".
#' @param fecha_fin_BANCI Fecha (character o Date) de corte más reciente de
#'   BANCI. Requerida si `nueva_BANCI = TRUE` (la función se detiene con
#'   `stop()` si falta).
#' @param tipo_conjunto Character. "interseccion" (default) o "union"; se pasa
#'   directamente a [funcion_base_final()].
#' @param guardar_bases_matching Lógico. Si `nueva_BANCI = TRUE`, indica si las
#'   bases intermedias de matching se guardan en disco con
#'   [guardar_bases_match_BANCI_RNPDNO()]. Default: FALSE.
#' @param Base_BANCI_con_match_con_RNPDNO Data frame de BANCI con match ya
#'   calculado. Requerido si `nueva_BANCI = FALSE`.
#' @param Base_BANCI_sin_match_con_RNPDNO Data frame de BANCI sin match ya
#'   calculado. Requerido si `nueva_BANCI = FALSE`.
#' @param registros_localizados Data frame de registros administrativos de
#'   personas localizadas. Obligatorio (la función se detiene con `stop()` si
#'   es NULL): se reenvía a [funcion_base_final()], que lo actualiza con las
#'   nuevas localizaciones detectadas en `comprimido`, pero esa versión
#'   actualizada NO se propaga de vuelta a quien llame a esta función (solo se
#'   usa dentro de esta ejecución).
#' @return El data frame `comprimido` final generado por
#'   [funcion_base_final()] (según `tipo_conjunto`); la porción
#'   `registros_localizados` de ese resultado se descarta para mantener
#'   compatibilidad con los scripts existentes que esperan un data frame.
tratamiento_banci_rnpdno <- function(
    subeR = NULL,
    comprimido = NULL,
    nueva_BANCI = FALSE,
    limpiar_BANCI = TRUE,
    fecha_inicio_BANCI = "2025-08-01",
    fecha_fin_BANCI = NULL,
    tipo_conjunto = "interseccion",   # La otra opción es "union"
    guardar_bases_matching = FALSE,
    Base_BANCI_con_match_con_RNPDNO = NULL,
    Base_BANCI_sin_match_con_RNPDNO = NULL,
    registros_localizados = NULL
) {

  # ---- 1. Obtener bases de matching ---- #

  if (nueva_BANCI) {

    # Validar inputs
    if (is.null(subeR) || is.null(comprimido)) {
      stop("Error: Por favor proporciona tanto 'subeR' como 'comprimido' para realizar el match.")
    }

    if (is.null(fecha_fin_BANCI)) {
      stop("Error: Por favor proporciona 'fecha_fin_BANCI' para realizar el match.")
    }

    # Limpiar BANCI antes del match si se pide
    if(limpiar_BANCI) {
      message("Limpiando la base BANCI...\n")
    resultado_limpieza <- funcion_limpieza_banci(
      subeR = subeR,
      fecha_inicio_BANCI = fecha_inicio_BANCI,
      fecha_fin_BANCI = fecha_fin_BANCI
    )
    
    subeR <- resultado_limpieza$subeR_no_loc_con_corte
    
    } else {
      # Solo No localizados
      subeR_con_corte <- subeR |> 
      filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI) & localizado_o_no_localizado == "No localizada")

      message("Después de filtrar la base de BANCI para quedarnos solo con los casos de 'No localizada' desde la fecha de inicio de BANCI (", fecha_inicio_BANCI, ") el número total de casos es: ", comma(nrow(subeR_con_corte)), "\n")

      subeR <- subeR_con_corte
    }

    # Hacer el match
    message("Realizando el match entre BANCI y RNPDNO...\n")
    lista_con_insumos <- funcion_de_match_BANCI_y_RNPDNO(
      subeR = subeR,
      comprimido = comprimido,
      fecha_inicio_BANCI = fecha_inicio_BANCI,
      fecha_fin_BANCI = fecha_fin_BANCI
    )

    # Guardar o extraer bases
    if (guardar_bases_matching) {
      message("Guardando las bases de matching entre BANCI y RNPDNO...\n")
      guardar_bases_match_BANCI_RNPDNO(lista_con_insumos)
    } else {
      message("No se guardarán las bases de matching entre BANCI y RNPDNO.\n")
    }

    Base_BANCI_sin_match_con_RNPDNO <- lista_con_insumos[["Base_BANCI_sin_match_con_RNPDNO"]]
    Base_BANCI_con_match_con_RNPDNO <- lista_con_insumos[["Base_BANCI_con_match_con_RNPDNO"]]

  } else {

    # Validar que se hayan inyectado las bases pre-existentes
    if (is.null(Base_BANCI_con_match_con_RNPDNO) || is.null(Base_BANCI_sin_match_con_RNPDNO)) {
      stop("Error: Si 'nueva_BANCI = FALSE' debes proporcionar 'Base_BANCI_con_match_con_RNPDNO' y 'Base_BANCI_sin_match_con_RNPDNO'.")
    }

    if (is.null(comprimido)) {
      stop("Error: Por favor proporciona 'comprimido'.")
    }

    message("Usando bases de matching pre-existentes...")
  }

  # ---- 2. Generar base final ---- #

  if (is.null(registros_localizados)) {
    stop("Error: Por favor proporciona 'registros_localizados' (base de registros administrativos de personas localizadas) para generar la base final.")
  }

  message("Generando base final con modalidad: '", tipo_conjunto, "'...")

  comprimido_final <- funcion_base_final(
    Base_BANCI_con_match_con_RNPDNO = Base_BANCI_con_match_con_RNPDNO,
    Base_BANCI_sin_match_con_RNPDNO = Base_BANCI_sin_match_con_RNPDNO,
    comprimido = comprimido,
    registros_localizados = registros_localizados,
    tipo_conjunto = tipo_conjunto
  )

  message("¡Listo! La base final tiene ", comma(nrow(comprimido_final$comprimido)), " registros.\n")

  return(comprimido_final$comprimido)
}


# ————————————————————————————————————————————————————————— #
# Función final para generar el comprimido final - editada -------
# Todavía en desarrollo, no usar.
# ————————————————————————————————————————————————————————— #
# 
# # Obtenemos datos de la carpeta compartida de Drive:
# readRenviron(".Renviron")
# Sys.getenv("RNPDNO_data_raiz")
# 
# raiz_datos <- function(...) {
#   raiz <- Sys.getenv("RNPDNO_data_raiz", unset = here::here())
#   file.path(raiz, ...)
# }
# 
# carpeta_matches_historicos_input <- raiz_datos("RNPDNO", "input", "datos_de_fiscalias")
# carpeta_matches_historicos_output <- raiz_datos("RNPDNO", "output")
# 
# tratamiento_banci_rnpdno_nueva <- function(
#     tipo_actualizacion = "archivos de matching más reciente", # Hay tres opciones: "archivos de matching más reciente", "archivos de matching específicos" (aquí con Interactive R el usuario podrá escoger los archivos específicos) y "nueva BANCI" (aquí se escojerá y validará la BANCI más reciente y se procederá a realizar los matches siguientes : mediante la jerarquización FUB - CURP - NOMBRE, mediante la comparación de carpetas de investigación (flujo de Ari), mediante los matches validados por el Secretariado)
#     subeR = NULL,
#     comprimido = NULL,
#     nueva_BANCI = FALSE,
#     limpiar_BANCI = TRUE,
#     fecha_inicio_BANCI = "2025-08-01",
#     fecha_fin_BANCI = NULL,
#     tipo_conjunto = "interseccion",   # La otra opción es "union"
#     guardar_bases_matching = FALSE,
#     Base_BANCI_con_match_con_RNPDNO = NULL,
#     Base_BANCI_sin_match_con_RNPDNO = NULL,
#     registros_localizados = NULL
# ) {
# 
#   # ----- 0. Tipo de matching ------- #
#   if (tipo_actualizacion == "archivos de matching más reciente") {
# 
#     ## ---- SUBER ------ ##
#     message("Se usará la opción de 'archivos de matching más reciente' para el tratamiento de BANCI y RNPDNO.\n")
# 
#     # Escoger los archivos de SubeR y Base_BANCI_con_match_con_RNPDNO/Base_BANCI_sin_match_con_RNPDNO más recientes
#     carpeta_subeR_historicos <- paste0(carpeta_matches_historicos_input, "/datos_originales")
# 
#     # Enlistar todos los archivos de SubeR en la carpeta
#     archivos_subeR <- list.files(carpeta_subeR_historicos, pattern = "subeR|subir", full.names = TRUE, ignore.case = TRUE)
# 
#     # Agarrar el archivo más reciente:
#     archivo_subeR_mas_reciente <- archivos_subeR[which.max(file.info(archivos_subeR)$mtime)]
# 
#     # Doble check: si el archivo más reciente es el correcto, en caso contrario se hace un stop
#     if (interactive()) {
#       message("El archivo más reciente de SubeR encontrado es: ", archivo_subeR_mas_reciente, "\n")
#       
#       eleccion <- utils::menu(
#         choices = c("Sí, es el correcto", "No, quiero escoger otro archivo"),
#         title = "¿Es este el archivo correcto de SubeR?"
#       )
# 
#       if (eleccion == 2) {
#         stop("Por favor selecciona el archivo correcto de SubeR antes de continuar.")
#       }
#     } else {
#       message("El archivo más reciente de SubeR encontrado es: ", archivo_subeR_mas_reciente, "\n")
#     }
# 
#     ## ----- RESULTADOS DE MATCHING DE METODOLOGÍA JERARQUICA ----- ##
#     carpetas_actualizacion_matching_jerarquico <- fs::dir_ls(
#       paste0(carpeta_matches_historicos_output, "/cruces_banci_rnpdno/matches_metodologia_jerarquica"),
#       type = "directory",
#       regexp = "actualizacion_"
#     )
# 
#     # Solo mantener la carpeta más cercana a la fecha de hoy
#     fechas <- str_extract(carpetas_actualizacion_matching_jerarquico, "\\d{2}\\d{2}\\d{4}") |> 
#       lubridate::dmy(quiet = TRUE)
# 
#     # Escoger la fecha más cercana a hoy
#     fecha_mas_cercana <- fechas[which.min(abs(difftime(fechas, Sys.Date(), units = "days")))]
# 
#     # Escoger la carpeta correspondiente a esa fecha
#     carpeta_mas_cercana <- carpetas_actualizacion_matching_jerarquico[which(fechas == fecha_mas_cercana)]
# 
#     # Avisarle al usuario cuál carpeta se escogió
#     message("Se usará la carpeta de matching más reciente: ", carpeta_mas_cercana, "\n")
# 
#     if (interactive()) {
#       eleccion <- utils::menu(
#         choices = c("Sí, es la correcta", "No, quiero escoger otra carpeta"),
#         title = "¿Es esta la carpeta correcta de matching?"
#       )
# 
#       if (eleccion == 2) {
#         stop("Por favor selecciona la carpeta correcta de matching antes de continuar.")
#       }
#     }
# 
#    # Descargar los archivos del tipo "Base_BANCI_con_match_con_RNPDNO" y "Base_BANCI_sin_match_con_RNPDNO" de la carpeta más reciente
#     # archivo_con_match <- fs::dir_ls(carpeta_mas_cercana, regexp = "Base_BANCI_con_match_con_RNPDNO", type = "file")
#     # archivo_sin_match <- fs::dir_ls(carpeta_mas_cercana, regexp = "Base_BANCI_sin_match_con_RNPDNO", type = "file")
# 
#     # # Leer los archivos
#     # Base_BANCI_con_match_con_RNPDNO <- load(archivo_con_match)
#     # Base_BANCI_sin_match_con_RNPDNO <- load(archivo_sin_match)
# 
#     ## ----- RESULTADOS DE MATCHING DE RECONOCIMIENTO FUZZY ----- ##
#     # Es decir, el fujo de matching que hace Ari con la metodología de reconocimiento fuzzy (basado en carpetas de investigación)
# 
#     carpetas_actualizacion_matching_fuzzy <- fs::dir_ls(
#       paste0(carpeta_matches_historicos_output, "/cruces_banci_rnpdno/datos_procesados_matching_carpetas"),
#       type = "directory",
#       regexp = "actualizacion_"
#     )
# 
#     # Solo mantener la carpeta más cercana a la fecha de hoy
#     fechas_v2 <- str_extract(carpetas_actualizacion_matching_fuzzy, "\\d{2}\\d{2}\\d{4}") |> 
#       lubridate::dmy(quiet = TRUE)
# 
#     # Escoger la fecha más cercana a hoy
#     fecha_mas_cercana_v2 <- fechas_v2[which.min(abs(difftime(fechas_v2, Sys.Date(), units = "days")))]
# 
#     # Escoger la carpeta correspondiente a esa fecha
#     carpeta_mas_cercana_v2 <- carpetas_actualizacion_matching_fuzzy[which(fechas_v2 == fecha_mas_cercana_v2)]
# 
#     # Extraer solo string actualizacion_%d%m%Y
#     actualizacion_carpeta_mas_cercana_v2 <- str_extract(carpeta_mas_cercana_v2, "actualizacion_\\d{2}\\d{2}\\d{4}")
# 
#     # Avisarle al usuario cuál carpeta se escogió
#     message("Se usará la carpeta de matching más reciente: ", actualizacion_carpeta_mas_cercana_v2, "\n")
# 
#     if (interactive()) {
#       eleccion <- utils::menu(
#         choices = c("Sí, es la correcta", "No, quiero escoger otra carpeta"),
#         title = "¿Es esta la carpeta correcta de matching?"
#       )
# 
#       if (eleccion == 2) {
#         stop("Por favor selecciona la carpeta correcta de matching antes de continuar.")
#       }
#     }
# 
#     ## ----- RESULTADOS DE LA REVISIÓN DE MATCHES MANUALES ----- ##
#     archivos_revisados_secretariado <- fs::dir_ls(
#       paste0(carpeta_matches_historicos_output, "/cruces_banci_rnpdno/datos_revisados_secretariado"),
#       type = "file"
#     )
# 
#     # Como los archivos que se reenvían desde el Secretariado no siguen un patrón explícito en el nombre debemos agarrar los más recientes según la fecha de modificación del archivo. Para eso usamos fs::file_info()
#     info_archivos <- fs::file_info(archivos_revisados_secretariado) |>
#       arrange(desc(modification_time)) |>
#       select(path, modification_time)
# 
#     archivos_mas_recientes <- info_archivos |>
#      slice_head(n = 2) |>
#      pull(path)
# 
# 
#     ## ----- DESCARGA DE LA BASE DE MATCHING CONSOLIDADA ----- ##
#     carpetas_actualizacion_matching_consolidado <- fs::dir_ls(
#       paste0(carpeta_matches_historicos_output, "/cruces_banci_rnpdno/datos_procesados_matching_carpetas"),
#       type = "directory",
#       regexp = "actualizacion_"
#     )
# 
#   }
# 
#   # ---- 1. Obtener bases de matching ---- #
# 
#   if (nueva_BANCI) {
# 
#     # Validar inputs
#     if (is.null(subeR) || is.null(comprimido)) {
#       stop("Error: Por favor proporciona tanto 'subeR' como 'comprimido' para realizar el match.")
#     }
# 
#     if (is.null(fecha_fin_BANCI)) {
#       stop("Error: Por favor proporciona 'fecha_fin_BANCI' para realizar el match.")
#     }
# 
#     # Limpiar BANCI antes del match si se pide
#     if(limpiar_BANCI) {
#       message("Limpiando la base BANCI...\n")
#     resultado_limpieza <- funcion_limpieza_banci(
#       subeR = subeR,
#       fecha_inicio_BANCI = fecha_inicio_BANCI,
#       fecha_fin_BANCI = fecha_fin_BANCI
#     )
#     
#     subeR <- resultado_limpieza$subeR_no_loc_con_corte
#     
#     } else {
#       # Solo No localizados
#       subeR_con_corte <- subeR |> 
#       filter(fha_de_hchos >= as.Date(fecha_inicio_BANCI) & localizado_o_no_localizado == "No localizada")
# 
#       message("Después de filtrar la base de BANCI para quedarnos solo con los casos de 'No localizada' desde la fecha de inicio de BANCI (", fecha_inicio_BANCI, ") el número total de casos es: ", comma(nrow(subeR_con_corte)), "\n")
# 
#       subeR <- subeR_con_corte
#     }
# 
#     # Hacer el match
#     message("Realizando el match entre BANCI y RNPDNO...\n")
#     lista_con_insumos <- funcion_de_match_BANCI_y_RNPDNO(
#       subeR = subeR,
#       comprimido = comprimido,
#       fecha_inicio_BANCI = fecha_inicio_BANCI,
#       fecha_fin_BANCI = fecha_fin_BANCI
#     )
# 
#     # Guardar o extraer bases
#     if (guardar_bases_matching) {
#       message("Guardando las bases de matching entre BANCI y RNPDNO...\n")
#       guardar_bases_match_BANCI_RNPDNO(lista_con_insumos)
#     } else {
#       message("No se guardarán las bases de matching entre BANCI y RNPDNO.\n")
#     }
# 
#     Base_BANCI_sin_match_con_RNPDNO <- lista_con_insumos[["Base_BANCI_sin_match_con_RNPDNO"]]
#     Base_BANCI_con_match_con_RNPDNO <- lista_con_insumos[["Base_BANCI_con_match_con_RNPDNO"]]
# 
#   } else {
# 
#     # Validar que se hayan inyectado las bases pre-existentes
#     if (is.null(Base_BANCI_con_match_con_RNPDNO) || is.null(Base_BANCI_sin_match_con_RNPDNO)) {
#       stop("Error: Si 'nueva_BANCI = FALSE' debes proporcionar 'Base_BANCI_con_match_con_RNPDNO' y 'Base_BANCI_sin_match_con_RNPDNO'.")
#     }
# 
#     if (is.null(comprimido)) {
#       stop("Error: Por favor proporciona 'comprimido'.")
#     }
# 
#     message("Usando bases de matching pre-existentes...")
#   }
# 
#   # ---- 2. Generar base final ---- #
# 
#   if (is.null(registros_localizados)) {
#     stop("Error: Por favor proporciona 'registros_localizados' (base de registros administrativos de personas localizadas) para generar la base final.")
#   }
# 
#   message("Generando base final con modalidad: '", tipo_conjunto, "'...")
# 
#   comprimido_final <- funcion_base_final(
#     Base_BANCI_con_match_con_RNPDNO = Base_BANCI_con_match_con_RNPDNO,
#     Base_BANCI_sin_match_con_RNPDNO = Base_BANCI_sin_match_con_RNPDNO,
#     comprimido = comprimido,
#     registros_localizados = registros_localizados,
#     tipo_conjunto = tipo_conjunto
#   )
# 
#   message("¡Listo! La base final tiene ", comma(nrow(comprimido_final$comprimido)), " registros.\n")
# 
#   return(comprimido_final$comprimido)
# }