# ————————————————————————————————————————————————————————— #
# Nombre: Jocelyn Rocha
# Contacto: maricelaymiel@gmail.com
# Script: funcion_enriquecer_registros_pui.R
# Proyecto: Personas Desaparecidas
# Fecha: 2026-09-03
# Propósitos: 
# 1) Función que limpia el extracto crudo de la PUI (registros_pui) y
#            devuelve registros_pui_directorio, listo para cruzarse con
#            cualquier directorio (la unión con el directorio no ocurre aquí,
#            porque las columnas del directorio pueden variar de una versión a otra).
# 2) Función compartida por los distintos "directorios" (24 de junio,
#            "sin información" 079, y los que vengan después). Recibe un
#            directorio YA LEÍDO y unificado (la lectura/armado de cada fuente
#            se queda fuera de esta función porque difiere entre fuentes: un
#            solo xlsx vs. varias hojas por estado con columnas distintas) y:
#            1. Actualiza clasificación/estatus cruzando con comprimido (RNPDNO)
#            2. Recupera domicilio, teléfono y correo desde registros_pui_directorio
#            3. Marca con informacion_nueva_de_pui las filas que recibieron
#               algún dato nuevo de la PUI (para resaltarlas después en Excel)
#            4. Arma los resúmenes de antes/después por entidad
#            5. Exporta un xlsx por entidad y un xlsx de resumen consolidado
# ————————————————————————————————————————————————————————— #
# Librerías -----
# ————————————————————————————————————————————————————————— #

pacman::p_load(
  readr, tidyverse, dplyr, lubridate, readxl,
  scales, magrittr, stringi, tsibble, svglite,
  here, janitor
)

# ————————————————————————————————————————————————————————— #
# Función auxiliar: limpiar campos de texto de dirección -----
# ————————————————————————————————————————————————————————— #

# Quita prefijos de "sin dato" y deja NA si el campo queda vacío
.limpiar_campo_direccion <- function(x) {
  x |>
    toupper() |>
    str_squish() |>
    str_remove("^(SIN DATO|SE DESCONOCE|SD|ND)\\s*") |>
    str_squish() |>
    na_if("")
}

# Expande abreviaturas comunes de direcciones (AV, MZ, LT/LTE, S/N, COL)
.abreviar_direccion <- function(x) {
  case_when(
    str_detect(x, "\\bAV\\.?\\b") ~ str_replace_all(x, "\\bAV\\.?\\b", "AVENIDA"),
    str_detect(x, "\\bMZ\\b") ~ str_replace_all(x, "\\bMZ\\b", "MANZANA"),
    str_detect(x, "\\bLTE?\\.?\\b") ~ str_replace_all(x, "\\bLTE?\\.?\\b", "LOTE"),
    str_detect(x, "\\bS\\/?N\\b") ~ str_replace_all(x, "\\bS\\/?N\\b", "SIN NOMBRE"),
    str_detect(x, "\\bCOL\\b") ~ str_replace_all(x, "\\bCOL\\b", "COLONIA"),
    TRUE ~ x
  )
}

# Marca los correos como "válido" / "inválido" / NA
.validar_correo <- function(df) {
  df |>
    mutate(indicadora_correo_temp = case_when(
      !is.na(correo) & correo != "" & str_detect(correo, "@") & str_detect(correo, "\\.") ~ "válido",
      !is.na(correo) & correo != "" ~ "inválido",
      TRUE ~ NA_character_
    ))
}

# ————————————————————————————————————————————————————————— #
# Función principal: limpiar_registros_pui -----
# ————————————————————————————————————————————————————————— #

# registros_pui: data frame crudo leído del csv de la PUI (post clean_names())
# listas_negras: data frame con columna fub, de personas a excluir
# nombres_cuarenta_y_tres_desaparecidos: vector de nombres completos a excluir
# clean_telefonos: función para limpiar la columna telefono
# verbose: si TRUE, imprime los conteos de diagnóstico (igual que el script original)
limpiar_registros_pui <- function(registros_pui,
                                   listas_negras,
                                   nombres_cuarenta_y_tres_desaparecidos,
                                   clean_telefonos,
                                   verbose = TRUE) {

  if (verbose) {
    cat("Número de registros en la PUI:", comma(nrow(registros_pui)), "\n")
  }

  # ---- Crear variable de FUB (quitar UUID4) ---- #
  registros_pui <- registros_pui |>
    rename(fub_uuid = fub) |>
    mutate(fub = str_remove(fub_uuid, "([0-9A-F]-?){32}-?$")) |>
    mutate(fub = str_remove(fub, "-$"))

  # ---- Selección de columnas de interés ---- #
  registros_pui_directorio <- registros_pui |>
    select(-c(created_at, updated_at, is_valid, fecha_desaparicion, fub_uuid)) |>
    relocate(fub, .after = curp)

  # ---- Teléfono ---- #
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(telefono = clean_telefonos(telefono))

  # ---- Eliminar fubs que estén en listas negras ---- #
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(fub = toupper(stri_trim(fub))) |>
    filter(!fub %in% listas_negras$fub)

  # ---- Eliminar por nombre_completo_vic en nombres_cuarenta_y_tres_desaparecidos ---- #
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(nombre_completo_vic = paste(nombre, primer_apellido, segundo_apellido) |>
             str_squish() |> toupper() |> stri_trans_general("Latin-ASCII")) |>
    filter(!nombre_completo_vic %in% (
      nombres_cuarenta_y_tres_desaparecidos |>
        str_squish() |> toupper() |> stri_trans_general("Latin-ASCII")
    )) |>
    select(-nombre_completo_vic)

  if (verbose) {
    cat("Número de registros en la PUI una vez sin listas negras es:",
        comma(nrow(registros_pui_directorio)), "\n")
  }

  # ---- informacion_adicional: eliminar columna si está vacía ---- #
  if (all(is.na(registros_pui_directorio$informacion_adicional) |
          registros_pui_directorio$informacion_adicional == "")) {
    registros_pui_directorio <- registros_pui_directorio |> select(-informacion_adicional)
    if (verbose) message("La columna 'informacion_adicional' estaba vacía y ha sido eliminada.")
  }

  # ---- Correo electrónico ---- #
  if (all(is.na(registros_pui_directorio$correo) | registros_pui_directorio$correo == "")) {
    registros_pui_directorio <- registros_pui_directorio |> select(-correo)
    if (verbose) message("La columna 'correo' estaba vacía y ha sido eliminada.")
  } else {

    if (verbose) {
      num_no_na_correos <- registros_pui_directorio |>
        filter(!is.na(correo) & correo != "") |>
        nrow()
      message("Número de registros con correo no vacío: ", comma(num_no_na_correos))
    }

    registros_pui_directorio <- registros_pui_directorio |> .validar_correo()

    # Si tiene regex @gmail forzar a que el siguiente string sea ".com"
    registros_pui_directorio <- registros_pui_directorio |>
      mutate(correo = ifelse(str_detect(correo, regex("@gmail", ignore_case = TRUE)) &
                               !str_detect(correo, "\\.com$"),
                             str_replace(correo, regex("@gmail", ignore_case = TRUE), "@gmail.com"),
                             correo)) |>
      # Solo conservar el string que contenga el "@"
      mutate(correo = ifelse(!is.na(correo) & correo != "" & str_detect(correo, "@"),
                             str_extract(correo, "[^\\s]+@[^\\s]+"), correo)) |>
      # Eliminar sufijos "-com"
      mutate(correo = str_replace(correo, "-com$", ""))

    # Volver a correr la validación con el correo ya limpio
    registros_pui_directorio <- registros_pui_directorio |>
      .validar_correo() |>
      mutate(correo = ifelse(indicadora_correo_temp == "inválido", NA, correo)) |>
      select(-indicadora_correo_temp)
  }

  # ---- Dirección ---- #

  # Quitar "DOMICILIO CONOCIDO" de calle, colonia, código postal y dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(
      direccion     = str_remove_all(direccion, "DOMICILIO CONOCIDO") |> str_squish() |> na_if(""),
      calle         = str_remove_all(calle, "DOMICILIO CONOCIDO") |> str_squish() |> na_if(""),
      colonia       = str_remove_all(colonia, "DOMICILIO CONOCIDO") |> str_squish() |> na_if(""),
      codigo_postal = str_remove_all(codigo_postal, "DOMICILIO CONOCIDO") |> str_squish() |> na_if("")
    )

  # Expandir abreviaturas en calle y dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(
      calle     = .abreviar_direccion(calle),
      direccion = .abreviar_direccion(direccion)
    )

  # Código postal válido: 5 dígitos numéricos, si no cumple se vuelve NA
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(codigo_postal = ifelse(str_detect(codigo_postal, "^\\d{5}$"), codigo_postal, NA_character_))

  # Colapsar comas duplicadas y quitar coma inicial en dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(
      direccion = str_replace_all(direccion, ",{2,}", ","),
      direccion = str_remove(direccion, "^,\\s*")
    )

  # Limpiar "SIN DATO" / "SE DESCONOCE" de los campos de dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(
      direccion     = .limpiar_campo_direccion(direccion),
      calle         = .limpiar_campo_direccion(calle),
      colonia       = .limpiar_campo_direccion(colonia),
      codigo_postal = .limpiar_campo_direccion(codigo_postal)
    )

  # Actualizar indicadora_domicilio después de limpiar los campos de dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(indicadora_domicilio = case_when(
      !is.na(calle) | !is.na(codigo_postal) | !is.na(colonia) | !is.na(direccion) ~ "con domicilio",
      TRUE ~ "sin domicilio"
    ))

  # Últimos retoques de puntuación en dirección
  registros_pui_directorio <- registros_pui_directorio |>
    mutate(
      direccion = str_remove(direccion, "DOMICILIO DEL LUGAR DE LOS HECHOS: "),
      direccion = str_replace_all(direccion, "[,\\s]*,[,\\s]*", ", "),
      direccion = str_remove(direccion, "^,\\s*"),
      direccion = str_remove(direccion, ",\\s*$"),
      direccion = str_squish(direccion)
    )

  # ---- Unicidad de fub ---- #

  if (verbose) {
    n_fub_duplicados <- registros_pui_directorio |> group_by(fub) |> filter(n() > 1) |> nrow()
    cat("Registros con fub duplicado:", comma(n_fub_duplicados), "\n")
  }

  # Validar que los duplicados sean la misma persona (nombre/apellidos consistentes)
  num_validacion_repetidos_fubs <- registros_pui_directorio |>
    group_by(fub) |>
    filter(n() > 1) |>
    filter(!is.na(nombre) & !is.na(primer_apellido) & !is.na(segundo_apellido)) |>
    filter(n_distinct(nombre) > 1 | n_distinct(primer_apellido) > 1 | n_distinct(segundo_apellido) > 1) |>
    nrow()

  # Si num_validacion_repetidos_fubs == 0, quedarse con un solo registro por fub,
  # priorizando el registro con valor no NA en nombre, primer_apellido y segundo_apellido
  if (num_validacion_repetidos_fubs == 0) {
    registros_pui_directorio <- registros_pui_directorio |>
      arrange(desc(!is.na(nombre)), desc(!is.na(primer_apellido)), desc(!is.na(segundo_apellido))) |>
      distinct(fub, .keep_all = TRUE) |>
      ungroup()
  } else {
    warning("Hay fubs repetidos con información distinta en nombre, primer_apellido o segundo_apellido")
  }

  registros_pui_directorio
}


# ————————————————————————————————————————————————————————— #
# Función auxiliar: conteo por entidad -----
# ————————————————————————————————————————————————————————— #

.contar_por_entidad <- function(data, entidad, indicadora) {
  entidad <- rlang::ensym(entidad)
  indicadora <- rlang::ensym(indicadora)

  data |>
    group_by(!!entidad) |>
    count(!!indicadora) |>
    ungroup() |>
    rename(Conteo = n) |>
    pivot_wider(
      names_from = !!indicadora,
      values_from = Conteo,
      values_fill = list(Conteo = 0)
    )
}

# ————————————————————————————————————————————————————————— #
# Función principal: enriquecer_directorio_con_pui -----
# ————————————————————————————————————————————————————————— #

# directorio: data frame ya leído/unificado de la fuente que sea (un xlsx único
#             o varias hojas ya unidas con bind_rows). Debe traer, como mínimo,
#             la columna fub y estado_de_desaparicion; el resto de columnas que
#             la función espera (calle, codigo_postal, colonia, direccion,
#             calle_datos_ine, etc.) se crean como NA si no vienen en la fuente,
#             para que la función no truene por columnas que solo existen en
#             algunas versiones del directorio.
# comprimido: base del RNPDNO ya actualizada, para refrescar clasificacion_des/estatus.
# registros_pui_directorio: salida de limpiar_registros_pui().
# carpeta_exportacion_entidades: ruta YA RESUELTA (ej. con here::here()) de la
#             carpeta donde se guarda un xlsx por entidad.
# prefijo_archivo_entidad: prefijo del nombre de archivo por entidad (ej. "base_contacto").
# sufijo_archivo: sufijo de fecha para el nombre de archivo (ej. "04092026").
# fecha_documento: fecha (Date) que se pasa al parámetro fecha de write_xlsx_atdt.
# titulo_exportacion_entidad: título base (se le concatena " - <entidad>").
# carpeta_resumen: ruta YA RESUELTA (ej. con here::here()) de la carpeta del resumen.
# nombre_archivo_resumen, titulo_resumen: nombre de archivo y título del xlsx
#             con los resúmenes de recuperación de información.
# verbose: si TRUE, imprime los conteos de diagnóstico.
enriquecer_directorio_con_pui <- function(directorio,
                                           comprimido,
                                           registros_pui_directorio,
                                           carpeta_exportacion_entidades,
                                           prefijo_archivo_entidad,
                                           sufijo_archivo,
                                           fecha_documento,
                                           titulo_exportacion_entidad,
                                           carpeta_resumen,
                                           nombre_archivo_resumen,
                                           titulo_resumen,
                                           verbose = TRUE) {

  if (verbose) {
    cat("Número de registros en el directorio:", comma(nrow(directorio)), "\n")
  }

  # ---- Garantizar que existan las columnas que usa la función ---- #
  # Distintas fuentes traen distintas columnas (ej. los datos de INE o
  # "otros_numeros" no siempre existen); las creamos como NA si faltan
  # para que el resto de la función no truene por columnas ausentes.
  columnas_esperadas <- c(
    "curp_de_la_victima",
    "calle", "codigo_postal", "colonia", "direccion",
    "calle_datos_ine", "codigo_postal_datos_ine", "colonia_datos_ine", "direccion_datos_ine",
    "numeros_del_reportante", "numeros_de_la_persona_desaparecida", "otros_numeros",
    "indicadora_de_domicilio", "indicadora_de_numero_de_contacto",
    "fecha_de_hechos_modificada", "fecha_de_captura_de_desaparicion"
  )

  faltantes <- setdiff(columnas_esperadas, names(directorio))
  if (length(faltantes) > 0) {
    if (verbose) message("Columnas ausentes en esta fuente (se crean como NA): ",
                         paste(faltantes, collapse = ", "))
    directorio[faltantes] <- NA
  }

  # ---- Cruzar con RNPDNO para ver si la clasificacion_des se actualizó ---- #
  directorio <- directorio |>
    mutate(fub = toupper(fub)) |>
    left_join(
      comprimido |> select(fub, clasificacion_des_actualizado = clasificacion_des,
                            anio_hechos_modificada, estatus_actualizado = estatus,
                            indicadora_de_indicio_de_vida_nueva = indicadora_indicio_de_vida),
      by = "fub"
    )

  if (verbose) {
    n_fub_repetidos <- directorio |> group_by(fub) |> filter(n() > 1) |> nrow()
    cat("Fubs repetidos en el directorio:", comma(n_fub_repetidos), "\n")
  }

  # ---- Resumen ANTES de recuperar información de la PUI ---- #
  resumen_estatus_anterior_numero <- directorio |>
    count(indicadora_de_numero_de_contacto) |>
    arrange(desc(n)) |>
    rename(Conteo = n)

  resumen_estatus_anterior_direccion <- directorio |>
    count(indicadora_de_domicilio) |>
    arrange(desc(n)) |>
    rename(Conteo = n)

  resumen_estatus_anterior_numero_por_entidad <- directorio |>
    .contar_por_entidad(estado_de_desaparicion, indicadora_de_numero_de_contacto)

  resumen_estatus_anterior_direccion_por_entidad <- directorio |>
    .contar_por_entidad(estado_de_desaparicion, indicadora_de_domicilio)

  resumen_estatus_anterior_por_entidad <- resumen_estatus_anterior_numero_por_entidad |>
    left_join(resumen_estatus_anterior_direccion_por_entidad, by = "estado_de_desaparicion")

  # ————————————————————————————————————————————————————————— #
  # RECUPERAR INFORMACIÓN DE LA PUI -----
  # ————————————————————————————————————————————————————————— #

  ## 1. Dirección, calle, colonia y código postal
  directorio_con_domicilio <- directorio |> filter(indicadora_de_domicilio == "Con domicilio")
  directorio_sin_domicilio <- directorio |> filter(indicadora_de_domicilio == "Sin domicilio")

  directorio_sin_domicilio <- directorio_sin_domicilio |>
    left_join(
      registros_pui_directorio |>
        select(fub, calle_pui = calle, codigo_postal_pui = codigo_postal,
               colonia_pui = colonia, direccion_pui = direccion),
      by = "fub"
    ) |>
    mutate(
      indicadora_domicilio_recuperada = case_when(
        !is.na(calle_pui) | !is.na(codigo_postal_pui) | !is.na(colonia_pui) | !is.na(direccion_pui) ~
          "Información de domicilio de PUI",
        TRUE ~ NA_character_
      )
    )

  resumen_estatus_domicilio_despues <- directorio_sin_domicilio |>
    count(indicadora_domicilio_recuperada) |>
    rename(Conteo = n) |>
    mutate(indicadora_domicilio_recuperada = ifelse(
      is.na(indicadora_domicilio_recuperada),
      "Sin información de domicilio de PUI",
      indicadora_domicilio_recuperada
    ))

  resumen_estatus_domicilio_despues_por_entidad <- directorio_sin_domicilio |>
    .contar_por_entidad(estado_de_desaparicion, indicadora_domicilio_recuperada)

  directorio <- directorio_con_domicilio |>
    bind_rows(directorio_sin_domicilio) |>
    mutate(
      calle = coalesce(calle, calle_pui),
      codigo_postal = coalesce(codigo_postal, codigo_postal_pui),
      colonia = coalesce(colonia, colonia_pui),
      direccion = coalesce(direccion, direccion_pui)
    ) |>
    select(-any_of(c("calle_pui", "codigo_postal_pui", "colonia_pui", "direccion_pui")))

  ## 2. Teléfono
  directorio_con_numero <- directorio |> filter(indicadora_de_numero_de_contacto == "Con número de contacto")
  directorio_sin_numero <- directorio |> filter(indicadora_de_numero_de_contacto == "Sin número de contacto")

  directorio_sin_numero <- directorio_sin_numero |>
    left_join(
      registros_pui_directorio |> select(fub, telefono_pui = telefono),
      by = "fub"
    ) |>
    mutate(
      indicadora_numero_recuperado = case_when(
        !is.na(telefono_pui) ~ "Información de teléfono de PUI",
        TRUE ~ "Sin información de teléfono en PUI"
      )
    )

  resumen_estatus_numero_despues <- directorio_sin_numero |>
    count(indicadora_numero_recuperado) |>
    rename(Conteo = n)

  resumen_estatus_numero_despues_por_entidad <- directorio_sin_numero |>
    .contar_por_entidad(estado_de_desaparicion, indicadora_numero_recuperado)

  # No hacer coalesce() porque no se sabe si el teléfono de la PUI es de la
  # persona desaparecida o del reportante
  directorio <- directorio_con_numero |>
    bind_rows(directorio_sin_numero)

  rm(directorio_con_domicilio, directorio_sin_domicilio, directorio_con_numero, directorio_sin_numero)

  ## 3. Correo electrónico (se calcula sobre la base completa)
  directorio <- directorio |>
    left_join(
      registros_pui_directorio |> select(fub, correo_pui = correo),
      by = "fub"
    ) |>
    mutate(
      indicadora_correo_recuperado = case_when(
        !is.na(correo_pui) ~ "Información de correo de PUI",
        TRUE ~ "Sin información de correo en PUI"
      )
    )

  resumen_recuperacion_correo <- directorio |>
    count(indicadora_correo_recuperado) |>
    rename(Conteo = n)

  resumen_correo_recuperado_por_entidad <- directorio |>
    .contar_por_entidad(estado_de_desaparicion, indicadora_correo_recuperado)

  # ---- Marcar filas con información nueva de la PUI (para resaltarlas después) ---- #
  directorio <- directorio |>
    mutate(informacion_nueva_de_pui = case_when(
      !is.na(indicadora_domicilio_recuperada) |
        indicadora_numero_recuperado %in% "Información de teléfono de PUI" |
        indicadora_correo_recuperado %in% "Información de correo de PUI" ~ "Información nueva de PUI",
      TRUE ~ NA_character_
    ))

  # ————————————————————————————————————————————————————————— #
  # BASE CONSOLIDADA -----
  # ————————————————————————————————————————————————————————— #

  # select(-any_of(...)) en vez de nombres fijos: algunas fuentes (ej. el
  # directorio "sin información" de la PUI-079) no traen estas columnas
  directorio <- directorio |>
    select(-any_of(c(
      "detalle_de_las_tasas_de_exito_de_las_instituciones_indicadoras_de_vida",
      "tasa_de_exito_de_localizacion",
      "anio_hechos_modificada",
      "clasificacion_des_actualizado",
      "indicadora_de_indicio_de_vida_nueva",
      "indicadora_correo_recuperado"
    )))

  # Donde is.na(estatus_actualizado) hacer "DESAPARECIDA"
  directorio <- directorio |>
    mutate(estatus_actualizado = ifelse(is.na(estatus_actualizado), "DESAPARECIDA", estatus_actualizado)) |>
    mutate(estatus_actualizado = str_to_sentence(estatus_actualizado))

  # Actualizar indicadora_de_numero_de_contacto
  directorio <- directorio |>
    mutate(indicadora_de_numero_de_contacto = case_when(
      !is.na(numeros_del_reportante) | !is.na(numeros_de_la_persona_desaparecida) |
        !is.na(otros_numeros) | !is.na(telefono_pui) ~ "Con número de contacto",
      TRUE ~ "Sin número de contacto"
    ))

  # Actualizar indicadora_de_domicilio
  directorio <- directorio |>
    mutate(indicadora_de_domicilio = case_when(
      !is.na(calle) | !is.na(codigo_postal) | !is.na(colonia) | !is.na(direccion) |
        !is.na(calle_datos_ine) | !is.na(codigo_postal_datos_ine) |
        !is.na(colonia_datos_ine) | !is.na(direccion_datos_ine) ~ "Con domicilio",
      TRUE ~ "Sin domicilio"
    ))

  # Eliminar columnas intermedias de recuperación (ya están resumidas en informacion_nueva_de_pui)
  directorio <- directorio |>
    select(-any_of(c("indicadora_domicilio_recuperada", "indicadora_numero_recuperado")))

  # Pasar telefono_pui al lado de otros_numeros
  directorio <- directorio |>
    relocate(telefono_pui, .after = otros_numeros)

  # Pasar correo_pui al lado de direccion_datos_ine
  directorio <- directorio |>
    relocate(correo_pui, .after = direccion_datos_ine)

  # Crear indicadora_correo y colocar antes de correo_pui
  directorio <- directorio |>
    mutate(indicadora_correo = case_when(
      !is.na(correo_pui) ~ "Con correo",
      TRUE ~ "Sin correo"
    )) |>
    relocate(indicadora_correo, .before = correo_pui)

  # Pasar fecha_de_captura_de_desaparicion después de fecha_de_hechos_modificada
  directorio <- directorio |>
    relocate(fecha_de_captura_de_desaparicion, .after = fecha_de_hechos_modificada)

  # Toda columna que inicie con fecha hacer as.character
  directorio <- directorio |>
    mutate(across(starts_with("fecha"), as.character))

  # Hacer CURP toupper()
  directorio <- directorio |>
    mutate(curp_de_la_victima = toupper(curp_de_la_victima))

  # Crear indicadora_domicilio_datos_ine y colocar antes de calle_datos_ine
  directorio <- directorio |>
    mutate(indicadora_domicilio_datos_ine = case_when(
      !is.na(calle_datos_ine) | !is.na(codigo_postal_datos_ine) |
        !is.na(colonia_datos_ine) | !is.na(direccion_datos_ine) ~ "Con domicilio",
      TRUE ~ "Sin domicilio"
    )) |>
    relocate(indicadora_domicilio_datos_ine, .before = calle_datos_ine)

  # Finalmente arreglar dirección: colapsar comas duplicadas y quitar residuos
  directorio <- directorio |>
    mutate(
      direccion = str_replace_all(direccion, "[,\\s]*,[,\\s]*", ", "),
      direccion = str_remove(direccion, "^,\\s*"),
      direccion = str_remove(direccion, ",\\s*$"),
      direccion = str_squish(direccion)
    ) |>
    mutate(direccion = str_remove(direccion, "DOMICILIO DEL LUGAR DE LOS HECHOS: "))

  # ————————————————————————————————————————————————————————— #
  # Exportar un xlsx por entidad -----
  # ————————————————————————————————————————————————————————— #

  edos <- unique(directorio$estado_de_desaparicion)

  for (i in edos) {
    nombre_limpio <- janitor::make_clean_names(i)

    directorio |>
      filter(estado_de_desaparicion == i) |>
      write_xlsx_atdt(
        file.path(carpeta_exportacion_entidades,
                  paste0(prefijo_archivo_entidad, "_", nombre_limpio, "_", sufijo_archivo, ".xlsx")),
        sheet_name = "Personas desaparecidas",
        max_col_width = 90,
        parse_names = TRUE,
        titulo = paste0(titulo_exportacion_entidad, " - ", i),
        fecha = fecha_documento,
        resaltar_columna = "informacion_nueva_de_pui",
        resaltar_valor = "Información nueva de PUI"
      )
  }

  # ————————————————————————————————————————————————————————— #
  # Resumen consolidado -----
  # ————————————————————————————————————————————————————————— #

  resumen_consolidado_por_entidad <- resumen_estatus_anterior_por_entidad |>
    left_join(
      resumen_estatus_domicilio_despues_por_entidad |>
        select(estado_de_desaparicion,
               `Domicilio recuperado (PUI)` = `Información de domicilio de PUI`),
      by = "estado_de_desaparicion"
    ) |>
    left_join(
      resumen_estatus_numero_despues_por_entidad |>
        select(estado_de_desaparicion,
               `Teléfono recuperado (PUI)` = `Información de teléfono de PUI`),
      by = "estado_de_desaparicion"
    ) |>
    left_join(
      resumen_correo_recuperado_por_entidad |>
        select(estado_de_desaparicion,
               `Correo recuperado (PUI)` = `Información de correo de PUI`),
      by = "estado_de_desaparicion"
    ) |>
    mutate(across(
      c(`Domicilio recuperado (PUI)`, `Teléfono recuperado (PUI)`, `Correo recuperado (PUI)`),
      ~ replace_na(.x, 0)
    ))

  resumen_recuperacion_pui <- list(
    "Estatus inicial - número"      = resumen_estatus_anterior_numero,
    "Estatus inicial - domicilio"   = resumen_estatus_anterior_direccion,
    "Estatus inicial por entidad"   = resumen_estatus_anterior_por_entidad,
    "Consolidado por entidad"       = resumen_consolidado_por_entidad,
    "Domicilio recuperado"          = resumen_estatus_domicilio_despues,
    "Domicilio recup. x entidad"    = resumen_estatus_domicilio_despues_por_entidad,
    "Teléfono recuperado"           = resumen_estatus_numero_despues,
    "Teléfono recup. x entidad"     = resumen_estatus_numero_despues_por_entidad,
    "Correo recuperado"             = resumen_recuperacion_correo,
    "Correo recuperado x entidad"   = resumen_correo_recuperado_por_entidad
  )

  write_xlsx_atdt(
    resumen_recuperacion_pui,
    file.path(carpeta_resumen, nombre_archivo_resumen),
    sheet_name = names(resumen_recuperacion_pui),
    max_col_width = 40,
    parse_names = TRUE,
    titulo = titulo_resumen,
    fecha = fecha_documento
  )

  invisible(list(
    directorio = directorio,
    resumen_recuperacion_pui = resumen_recuperacion_pui
  ))
}
