# FUNCIONES DE USO DEL CATÁLOGO DEL INEGI —————————————————————————————————————

#' Crear llaves de matching en un data.frame/tibble
#'
#' Crea columnas de llave de matching para entidad+municipio y, opcionalmente,
#' entidad+municipio+localidad. Si `mun = NULL`, crea una llave de matching de
#' SOLO entidad (columna `LLAVE_ENT`): primero homologa el nombre de la entidad
#' contra un catálogo interno de variantes (nombres oficiales largos, nombres
#' cortos, nombres históricos como "Distrito Federal" o "Querétaro de Arteaga",
#' abreviaturas comunes como "CDMX", "D.F.", "Edomex", "Q. Roo" o "N.L.", e
#' incluso claves numéricas 1-32) y después convierte el nombre canónico a
#' snake_case (Latin-ASCII). Por ejemplo, "México", "EDOMEX" y "Estado de
#' México" producen la misma llave: `estado_de_mexico`.
#'
#' La estandarización de nombres sigue la misma lógica utilizada en
#' `procesar_claves_combinadas`: title case respetando `stopwords_title_es`,
#' mantener números romanos en mayúsculas y luego transliterar a snake_case
#' (Latin-ASCII). El parámetro `nombres_ent_cortos` (por defecto TRUE) solo
#' afecta la versión usada para construir la llave y no modifica las columnas
#' originales del data.frame.
#'
#' @param df Data frame o tibble con los datos.
#' @param ent Nombre de la columna con el nombre de la entidad (string).
#' @param mun Nombre de la columna con el nombre del municipio (string). Si es NULL,
#'        se crea únicamente la llave de solo entidad `LLAVE_ENT`.
#' @param loc Nombre de la columna con el nombre de la localidad (string). Opcional, por defecto NULL.
#' @param cve_ent Nombre de la columna con la clave de entidad (2 dígitos INEGI). Opcional.
#'        Si se proporciona, se usa directamente (como prefijo en las llaves de
#'        municipio/localidad, o para homologar el nombre en la llave de solo entidad).
#'        Si no, se infiere a partir del nombre de la entidad usando un lookup interno.
#' @param nombres_ent_cortos Logical. Si TRUE, aplica simplificación (ej. "Coahuila de Zaragoza" → "Coahuila")
#'        solo en la versión usada para crear las llaves de nombre. No modifica las columnas originales.
#'        En la llave de solo entidad, TRUE usa nombres cortos/desambiguados
#'        (`coahuila`, `estado_de_mexico`, `michoacan`, `veracruz`); FALSE usa los
#'        nombres oficiales del INEGI (`coahuila_de_zaragoza`, `mexico`, etc.).
#' @param sobreescribir_resultados Logical. Si FALSE, evita sobrescribir columnas ya existentes de llaves.
#'
#' @return Data frame/tibble con las nuevas columnas añadidas: `NOM_ENT_MUN` (y
#'         `NOM_ENT_MUN_LOC` si se pidió localidad), o `LLAVE_ENT` cuando `mun = NULL`.
#' @examples
#' \dontrun{
#' df <- data.frame(
#'   NOM_ENT = c("COAHUILA DE ZARAGOZA", "VERACRUZ DE IGNACIO DE LA LLAVE", "MICHOACÁN DE OCAMPO", 
#'               "JALISCO", "NUEVO LEÓN", "GUANAJUATO", "PUEBLA", "CHIAPAS", "CIUDAD DE MÉXICO", "OAXACA"),
#'   NOM_MUN = c("SALTILLO", "XALAPA", "MORELIA", "GUADALAJARA", "MONTERREY", 
#'               "LEÓN", "PUEBLA", "TUXTLA GUTIÉRREZ", "BENITO JUÁREZ", "OAXACA DE JUÁREZ"),
#'   NOM_LOC = c("SALTILLO", "XALAPA-ENRÍQUEZ", "MORELIA", "GUADALAJARA", "MONTERREY",
#'               "LEÓN DE LOS ALDAMA", "PUEBLA DE ZARAGOZA", "TUXTLA GUTIÉRREZ", 
#'               "CIUDAD DE MÉXICO", "OAXACA DE JUÁREZ")
#' )
#' df2 <- crear_llave_matching(df, ent = "NOM_ENT", mun = "NOM_MUN")
#' df3 <- crear_llave_matching(df, ent = "NOM_ENT", mun = "NOM_MUN", loc = "NOM_LOC")
#'
#' # Llave de matching de SOLO entidad (mun = NULL): homologa variantes del nombre
#' df_ent <- data.frame(
#'   ESTADO = c("México", "EDOMEX", "Estado de México", "CDMX", "Distrito Federal",
#'              "Veracruz-Llave", "Q. Roo", "N.L.", "Coahuila de Zaragoza")
#' )
#' df4 <- crear_llave_matching(df_ent, ent = "ESTADO", mun = NULL)
#' # → LLAVE_ENT: estado_de_mexico, estado_de_mexico, estado_de_mexico,
#' #   ciudad_de_mexico, ciudad_de_mexico, veracruz, quintana_roo, nuevo_leon, coahuila
#' }
#' @export
crear_llave_matching <- function(
  df,
  ent = "NOM_ENT",
  mun = NULL,
  loc = NULL,
  cve_ent = NULL,
  nombres_ent_cortos = TRUE,
  sobreescribir_resultados = TRUE
) {
  
  # Paquetes mínimos necesarios
  pacman::p_load(dplyr, stringr, stringi, snakecase, crayon)

  #' Palabras que deben quedar en minúsculas en títulos en español
  stopwords_title_es <- c(
    # Artículos
    "el","la","los","las","un","una","unos","unas",
    # Contracciones
    "al","del",
    # Conjunciones
    "y","e","ni","o","u",
    # Preposiciones
    "a","con","de","en","por","sin"
  )

  # Validaciones básicas
  if (!ent %in% colnames(df)) stop(glue::glue("La columna de entidad '{ent}' no existe en el data.frame."))
  if (is.null(mun) && !is.null(loc)) stop("Para crear la llave con localidad ('loc') se requiere también la columna de municipio ('mun').")
  if (!is.null(mun) && !mun %in% colnames(df)) stop(glue::glue("La columna de municipio '{mun}' no existe en el data.frame."))
  if (!is.null(loc) && !loc %in% colnames(df)) stop(glue::glue("La columna de localidad '{loc}' no existe en el data.frame."))

  # Nombres de salida que se crearán
  nombre_llave_ent <- "LLAVE_ENT"
  nombre_nom_ent_mun <- "NOM_ENT_MUN"
  nombre_nom_ent_mun_loc <- "NOM_ENT_MUN_LOC"

  # # Evitar sobrescribir llaves ya existentes
  if (!sobreescribir_resultados) {

    if (is.null(mun)) {
      if (nombre_llave_ent %in% colnames(df)) {
        cat(crayon::green(paste0(">> La columna '", nombre_llave_ent, "' ya existe. No se realizó ninguna acción.\n")))
        return(df)
      }
    } else if (is.null(loc)) {
      if (nombre_nom_ent_mun %in% colnames(df)) {
        cat(crayon::green(paste0(">> La columna '", nombre_nom_ent_mun, "' ya existe. No se realizó ninguna acción.\n")))
        return(df)
      }
    } else {
      if (nombre_nom_ent_mun_loc %in% colnames(df) || nombre_nom_ent_mun %in% colnames(df)) {
        cat(crayon::green(paste0(">> Las columnas de llaves ya existen (", paste(intersect(c(nombre_nom_ent_mun, nombre_nom_ent_mun_loc), colnames(df)), collapse = ", "), "). No se realizó ninguna acción.\n")))
        return(df)
      }
    }
  
  }


  # Preparar versión de entidad para nombres cortos si se solicita (no muta df)
  # CAMBIO: Renombrar variable a ent_vals_procesados para evitar colisión
  ent_vals_procesados <- df[[ent]]
  if (isTRUE(nombres_ent_cortos)) {
    ent_vals_procesados <- ent_vals_procesados |>
      str_replace_all(regex("COAHUILA DE ZARAGOZA", ignore_case = TRUE), "COAHUILA") |>
      str_replace_all(regex("VERACRUZ DE IGNACIO DE LA LLAVE", ignore_case = TRUE), "VERACRUZ") |>
      str_replace_all(regex("MICHOACÁN DE OCAMPO", ignore_case = TRUE), "MICHOACÁN")
  }

  # Catálogo de entidades: CVE (2 dígitos INEGI) → nombre oficial (largo)
  nom_ent_largo <- c(
    "01" = "Aguascalientes",
    "02" = "Baja California",
    "03" = "Baja California Sur",
    "04" = "Campeche",
    "05" = "Coahuila de Zaragoza",
    "06" = "Colima",
    "07" = "Chiapas",
    "08" = "Chihuahua",
    "09" = "Ciudad de México",
    "10" = "Durango",
    "11" = "Guanajuato",
    "12" = "Guerrero",
    "13" = "Hidalgo",
    "14" = "Jalisco",
    "15" = "México",
    "16" = "Michoacán de Ocampo",
    "17" = "Morelos",
    "18" = "Nayarit",
    "19" = "Nuevo León",
    "20" = "Oaxaca",
    "21" = "Puebla",
    "22" = "Querétaro",
    "23" = "Quintana Roo",
    "24" = "San Luis Potosí",
    "25" = "Sinaloa",
    "26" = "Sonora",
    "27" = "Tabasco",
    "28" = "Tamaulipas",
    "29" = "Tlaxcala",
    "30" = "Veracruz de Ignacio de la Llave",
    "31" = "Yucatán",
    "32" = "Zacatecas"
  )

  # Versión corta/desambiguada de los nombres: simplifica los nombres largos y
  # homologa "México" → "Estado de México" para no confundirlo con la CDMX
  nom_ent_corto <- nom_ent_largo
  nom_ent_corto[c("05", "15", "16", "30")] <- c("Coahuila", "Estado de México", "Michoacán", "Veracruz")

  # Normalizador para el lookup: sin acentos, en mayúsculas y sin puntuación
  normalizar_ent <- function(x) {
    x |>
      as.character() |>
      stringi::stri_trans_general("Latin-ASCII") |>
      toupper() |>
      str_remove_all("\\.") |>
      str_replace_all("[^A-Z0-9]+", " ") |>
      str_squish()
  }

  # Lookup de CVE de entidad (2 dígitos INEGI): variante normalizada → CVE.
  # Incluye nombres oficiales, cortos, históricos y abreviaturas comunes.
  cve_ent_lookup <- c(
    "AGUASCALIENTES" = "01", "AGS" = "01",
    "BAJA CALIFORNIA" = "02", "BAJA CALIFORNIA NORTE" = "02", "BC" = "02",
    "BAJA CALIFORNIA SUR" = "03", "BCS" = "03",
    "CAMPECHE" = "04", "CAMP" = "04", "CAM" = "04",
    "COAHUILA DE ZARAGOZA" = "05", "COAHUILA" = "05", "COAH" = "05",
    "COLIMA" = "06", "COL" = "06",
    "CHIAPAS" = "07", "CHIS" = "07",
    "CHIHUAHUA" = "08", "CHIH" = "08",
    "CIUDAD DE MEXICO" = "09", "CD DE MEXICO" = "09", "CDMX" = "09", "CD MX" = "09",
    "DISTRITO FEDERAL" = "09", "DF" = "09", "MEXICO DF" = "09",
    "DURANGO" = "10", "DGO" = "10",
    "GUANAJUATO" = "11", "GTO" = "11",
    "GUERRERO" = "12", "GRO" = "12",
    "HIDALGO" = "13", "HGO" = "13",
    "JALISCO" = "14", "JAL" = "14",
    "MEXICO" = "15", "ESTADO DE MEXICO" = "15", "EDO DE MEXICO" = "15",
    "EDO DE MEX" = "15", "EDO MEX" = "15", "EDOMEX" = "15", "MEX" = "15",
    "MICHOACAN DE OCAMPO" = "16", "MICHOACAN" = "16", "MICH" = "16",
    "MORELOS" = "17", "MOR" = "17",
    "NAYARIT" = "18", "NAY" = "18",
    "NUEVO LEON" = "19", "NL" = "19",
    "OAXACA" = "20", "OAX" = "20",
    "PUEBLA" = "21", "PUE" = "21",
    "QUERETARO" = "22", "QUERETARO DE ARTEAGA" = "22", "QRO" = "22",
    "QUINTANA ROO" = "23", "QROO" = "23", "Q ROO" = "23",
    "SAN LUIS POTOSI" = "24", "SLP" = "24",
    "SINALOA" = "25", "SIN" = "25",
    "SONORA" = "26", "SON" = "26",
    "TABASCO" = "27", "TAB" = "27",
    "TAMAULIPAS" = "28", "TAMPS" = "28", "TAM" = "28",
    "TLAXCALA" = "29", "TLAX" = "29",
    "VERACRUZ DE IGNACIO DE LA LLAVE" = "30", "VERACRUZ" = "30",
    "VERACRUZ LLAVE" = "30", "VER" = "30",
    "YUCATAN" = "31", "YUC" = "31",
    "ZACATECAS" = "32", "ZAC" = "32"
  )

  # Inferir la CVE de entidad a partir del nombre (acepta también claves numéricas 1-32)
  inferir_cve_ent <- function(x) {
    x_norm <- normalizar_ent(x)
    cves <- unname(cve_ent_lookup[x_norm])
    es_numero <- !is.na(x_norm) & str_detect(x_norm, "^\\d{1,2}$")
    if (any(es_numero)) {
      nums <- suppressWarnings(as.integer(x_norm[es_numero]))
      cves[es_numero] <- ifelse(!is.na(nums) & nums >= 1 & nums <= 32, sprintf("%02d", nums), NA_character_)
    }
    return(cves)
  }

  # Determinar CVE de entidad (2 dígitos)
  if (!is.null(cve_ent) && cve_ent %in% colnames(df)) {
    cve_ent_vals <- sprintf("%02d", suppressWarnings(as.integer(df[[cve_ent]])))
  } else {
    cve_ent_vals <- inferir_cve_ent(ent_vals_procesados)
  }

  # Función local para estandarizar texto igual que en procesar_claves_combinadas
  estandarizar_nombre <- function(x) {
    # Manejar NAs: si el valor es NA, devolver NA directamente
    if_else(is.na(x), NA_character_,
      x |> 
        str_squish() |> 
        str_to_title() |> 
        stringr::str_replace_all(
          regex(paste0("(?<=\\s)\\b(", paste(stopwords_title_es, collapse = "|"), ")\\b(?=\\s)"),
                ignore_case = TRUE)
        , function(y) tolower(y)) |> 
        stringr::str_replace_all(
          regex("\\b([IVXLCDM]+)\\b", ignore_case = TRUE),
          function(z) if (!is.na(z) && str_detect(z, regex("^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", ignore_case = TRUE))) toupper(z) else z
        )
    )
  }

  # ——— Caso SOLO ENTIDAD: llave homologada por nombre (mun = NULL) ——————————
  if (is.null(mun)) {

    # 1) Validar la CVE obtenida y completar por nombre donde no sea válida
    cve_vals <- cve_ent_vals
    cve_vals[!cve_vals %in% names(nom_ent_largo)] <- NA_character_
    faltantes <- is.na(cve_vals)
    if (any(faltantes)) cve_vals[faltantes] <- inferir_cve_ent(df[[ent]][faltantes])

    # 2) Homologar al nombre canónico (corto/desambiguado u oficial largo)
    catalogo_canonico <- if (isTRUE(nombres_ent_cortos)) nom_ent_corto else nom_ent_largo
    ent_homologada <- unname(catalogo_canonico[cve_vals])

    # 3) Fallback: donde no hubo match, conservar el nombre original estandarizado
    sin_match <- is.na(ent_homologada) & !is.na(df[[ent]])
    if (any(sin_match)) {
      ent_homologada[sin_match] <- estandarizar_nombre(as.character(df[[ent]][sin_match]))
      no_reconocidos <- unique(as.character(df[[ent]][sin_match]))
      cat(crayon::yellow(paste0(
        ">> Aviso: ", length(no_reconocidos), " valor(es) de entidad no se reconocieron en el catálogo INEGI",
        " y se usó el nombre original estandarizado: ",
        paste(utils::head(no_reconocidos, 10), collapse = ", "),
        if (length(no_reconocidos) > 10) ", ..." else "", "\n"
      )))
    }

    # 4) Convertir a snake_case (Latin-ASCII) para obtener la llave final
    llave_ent_vals <- snakecase::to_any_case(ent_homologada, case = "snake", transliterations = "Latin-ASCII")
    llave_ent_vals[is.na(ent_homologada)] <- NA_character_

    # Añadir a df
    out <- df %>% mutate(!!nombre_llave_ent := llave_ent_vals)

    # Mensaje final informativo
    creadas <- setdiff(colnames(out), colnames(df))
    cat(crayon::green(paste0(">> Se agregaron las siguientes columnas: ", paste(creadas, collapse = ", "), "\n")))

    return(out)

  }

  # ——— Caso ENTIDAD + MUNICIPIO (+ LOCALIDAD) ———————————————————————————————

  # Estandarizar entidad/municipio/localidad para luego convertir a snake_case
  ent_est <- estandarizar_nombre(ent_vals_procesados)
  mun_est <- estandarizar_nombre(df[[mun]])
  loc_est <- NULL
  if (!is.null(loc)) loc_est <- estandarizar_nombre(df[[loc]])

  # browser()

  # Generar las llaves de nombre (snake_case con transliteration Latin-ASCII)
  nom_ent_mun <- paste(
    cve_ent_vals,
    snakecase::to_any_case(mun_est, case = "snake", transliterations = "Latin-ASCII"),
    sep = "_"
  )

  # Añadir a df
  out <- df %>% mutate(!!nombre_nom_ent_mun := nom_ent_mun)

  # Generar NOM_ENT_MUN_LOC y anexar si se pidió localidad
  if (!is.null(loc)) {
    nom_ent_mun_loc <- paste(
      cve_ent_vals,
      snakecase::to_any_case(mun_est, case = "snake", transliterations = "Latin-ASCII"),
      snakecase::to_any_case(loc_est, case = "snake", transliterations = "Latin-ASCII"),
      sep = "_"
    )
    out <- out %>% mutate(!!nombre_nom_ent_mun_loc := nom_ent_mun_loc)
  }

  # Mensaje final informativo
  creadas <- setdiff(colnames(out), colnames(df))
  cat(crayon::green(paste0(">> Se agregaron las siguientes columnas: ", paste(creadas, collapse = ", "), "\n")))

  return(out)

}


#' Obtener datos geográficos de INEGI desde la base de datos local en PostgreSQL.
#'
#' @description
#' Función que extrae datos geográficos de INEGI desde una base de datos PostgreSQL.
#' Permite consultar información a nivel de entidades, municipios o localidades.
#'
#' @param level Character. Nivel de desagregación geográfica deseado. Acepta variaciones
#'   de "entidades", "municipios" o "localidades" (e.g., "estado", "muni", "localidad").
#'   Por defecto: "de las municipalidades apá".
#' @param envfile Character. Ruta al archivo de variables de entorno (.env).
#'   Por defecto: ".env".
#' @param nombres_ent_cortos Logical. Si TRUE, simplifica los nombres de entidades
#'   (e.g., "Coahuila de Zaragoza" → "Coahuila"). También actualiza las claves
#'   combinadas NOM_ENT_MUN y NOM_ENT_MUN_LOC con los nombres cortos.
#'   Por defecto: TRUE.
#' 
#' Otros parámetros de conexión a la base de datos PostgreSQL:
#' 
#' @param dbname Character. Nombre de la base de datos PostgreSQL. 
#'   Por defecto: variable de entorno DB_NAME_INEGI_RO.
#' @param host Character. Host del servidor PostgreSQL.
#'   Por defecto: variable de entorno DB_HOST_INEGI_RO.
#' @param port Character. Puerto del servidor PostgreSQL.
#'   Por defecto: variable de entorno DB_PORT_INEGI_RO.
#' @param user Character. Usuario de la base de datos PostgreSQL.
#'   Por defecto: variable de entorno DB_USER_INEGI_RO.
#' @param password Character. Contraseña del usuario de PostgreSQL.
#'   Por defecto: variable de entorno DB_PASSWORD_INEGI_RO.
#'
#' @return Un tibble con los datos geográficos del nivel especificado. La función
#'   imprime un mensaje en consola indicando el número de registros importados.
#'
#' @details
#' La función utiliza coincidencia difusa (Jaro-Winkler) mediante `select_inegi_level()`
#' para interpretar el parámetro `level` y seleccionar automáticamente el nivel geográfico
#' más apropiado. Requiere credenciales de PostgreSQL que pueden especificarse directamente
#' como parámetros o cargarse desde un archivo .env (DB_NAME_INEGI_RO, DB_HOST_INEGI_RO,
#' DB_PORT_INEGI_RO, DB_USER_INEGI_RO, DB_PASSWORD_INEGI_RO).
#'
#' La función se conecta al esquema 'geo_inegi' en la base de datos y cierra automáticamente
#' la conexión al finalizar usando `on.exit()`.
#'
#' @examples
#' \dontrun{
#' # Obtener datos de municipios
#' municipios <- get_geo_inegi(level = "municipios")
#'
#' # Obtener datos de entidades (acepta variaciones)
#' estados <- get_geo_inegi(level = "estados")
#'
#' # Obtener datos de localidades con archivo .env personalizado
#' localidades <- get_geo_inegi(level = "localidades", envfile = "config/.env")
#' 
#' # Obtener datos sin simplificar nombres de entidades
#' municipios_nombres_largos <- get_geo_inegi(level = "municipios", nombres_ent_cortos = FALSE)
#' }
#'
#' @importFrom DBI dbConnect dbDisconnect Id
#' @importFrom RPostgres Postgres
#' @importFrom dplyr tbl collect
#' @importFrom dotenv load_dot_env
#' @importFrom crayon green
#' @export
get_geo_inegi <- function(
  # Parámetros de la función
  level = "de las municipalidades apá",
  envfile = ".env",
  nombres_ent_cortos = TRUE,
  # Datos de la base de datos
  dbname = NULL,
  host = NULL,
  port = NULL,
  user = NULL,
  password = NULL
) {

    # Función interna para seleccionar nivel de INEGI con coincidencia difusa
    select_inegi_level <- function(text = "Los municipios apá") {

        # Paquetes
        pacman::p_load(stringdist, stringr)

        # Posibles niveles de INEGI
        posibles_niveles <- c("entidades", "municipios", "localidades")

        # Enrutador y estandarización de level: minúsculas y quitar última "s"
        level_raw <- tolower(text) |>
            str_replace_all("estado|edo|estatal|^esta?d?o?s?$", "entidades") |>
            str_replace_all("municipio|muni|municipal", "municipios") |>
            str_replace_all("localidad|localidades|población|poblacional", "localidades")
        # Usar Jaro-Winkler para encontrar el nivel más cercano (rankear y seleccionar el mejor)
        idx_nivel_seleccionado <- which.min(stringdist::stringdist(level_raw, posibles_niveles, method = "jw"))
        # Seleccionar el nivel correcto
        level = posibles_niveles[idx_nivel_seleccionado]

        # Retornar nivel seleccionado
        return(level)

    }

    # Cargar paquetes
    pacman::p_load(DBI, RPostgres, stringdist, tibble, ellmer)

    # Cargar variables de entorno (antes de leer Sys.getenv)
    invisible(dotenv::load_dot_env(file = envfile))

    # Asignar valores desde .env si no se proporcionaron explícitamente
    dbname   <- dbname   %||% Sys.getenv("DB_NAME_INEGI_RO")
    host     <- host     %||% Sys.getenv("DB_HOST_INEGI_RO")
    port     <- port     %||% Sys.getenv("DB_PORT_INEGI_RO")
    user     <- user     %||% Sys.getenv("DB_USER_INEGI_RO")
    password <- password %||% Sys.getenv("DB_PASSWORD_INEGI_RO")
    
    # Enrutador de nivel de desagregación
    level <- level |> select_inegi_level()

    # Información de la base de datos:
    schema <- "geo_inegi"
    table <- level
    table_Id <- DBI::Id(schema = schema, table = table)

    # Conexión a la base de datos PostgreSQL
    con <- dbConnect(
        RPostgres::Postgres(),
        dbname = dbname,
        host = host,
        port = port,
        user = user,
        password = password
    )

    # Traer datos con dbplyr
    db_table <- tbl(con, table_Id) |> collect()

    # Procesamiento adicional: Nombres cortos de entidades
    if (nombres_ent_cortos) {
        cat("> Aplicando nombres cortos de entidades...\n")

        db_table <- db_table |>
        mutate(
        NOM_ENT = case_when(
        str_detect(NOM_ENT, "Coahuila de Zaragoza") ~ "Coahuila",
        str_detect(NOM_ENT, "Veracruz de Ignacio de la Llave") ~ "Veracruz",
        str_detect(NOM_ENT, "Michoacán de Ocampo") ~ "Michoacán",
        TRUE ~ NOM_ENT
        ),
        across(
        any_of(c("NOM_ENT_MUN", "NOM_ENT_MUN_LOC")),
        ~ str_replace_all(.x, "coahuila_de_zaragoza", "coahuila") |>
        str_replace_all("veracruz_de_ignacio_de_la_llave", "veracruz") |>
        str_replace_all("michoacan_de_ocampo", "michoacan")
        )
        )
    }

    # Desconectar al finalizar
    on.exit(dbDisconnect(con), add = TRUE)

    # Mensaje de cat, en color verde
    cat(paste0(">> Datos de '", crayon::green(level), "' cargados correctamente desde la base de datos.\n   Se han importado ", crayon::green(formatC(nrow(db_table), big.mark = ",")), " registros limpios con ", crayon::green("llaves de matching"), ".\n"))

    # Retorno de desarrollo
    return(db_table)

}

