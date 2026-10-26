


# Doble encuadre de datos
#install.packages("arrow")
library(arrow)
library(readr)
library(tidyverse)
library(broom)
library(skimr)
library(readxl)
library(lubridate)

# Configuración general -------------------------------------------------------
RAIZ <- "/Users/alberto/Documents/Secretariado presidencia/Desaparecidos/desaparecidos-python-main"
RUTA <- list(
  base_total = file.path(RAIZ, "output/Resultados_4_Generacion_Indicadores/reg_rn_min-max.parquet"),
  directorio_indicios = file.path(RAIZ, "input/domicilios_y_numeros_contacto/base_combinada_con_domicilio_y_numeros_de_contacto_24062026.xlsx"),
  mj_rips = file.path(RAIZ, "input/mj/MJ y RIPS (1062).xlsx"),
  corte_marzo_sisf = file.path(RAIZ, "input/datos_marzo/reg_rn_25mar26_des_sisf.xlsx"),
  corte_marzo_cind = file.path(RAIZ, "input/datos_marzo/reg_rn_25mar26_des_cisf_cind.xlsx"),
  corte_marzo_sind = file.path(RAIZ, "input/datos_marzo/reg_rn_25mar26_des_cisf_sind.xlsx"),
  corte_julio_sisf = file.path(RAIZ, "input/datos_julio/reg_rn_01jul26_des_sisf.xlsx"),
  corte_julio_cind = file.path(RAIZ, "input/datos_julio/reg_rn_01jul26_des_cisf_cind.xlsx"),
  corte_julio_sind = file.path(RAIZ, "input/datos_julio/reg_rn_01jul26_des_cisf_sind.xlsx")
)

normalizar_fub <- function(x) {
  stringr::str_to_upper(stringr::str_trim(as.character(x)))
}

#--------- Encuadre de base total-------

Base_maestra_fin <- read_parquet(RUTA$base_total) %>%
  mutate(
    # Variables generales reutilizadas por los tabulados de todas las láminas.
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    fecha_mes = format(fecha_periodo, "%Y-%m"),
    desaparecida = clasificacion_des_derivada_rnpdno %in% c("Desaparecidos", "Pendientes"),
    localizada = clasificacion_des_derivada_rnpdno == "Localizados",
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE),
    con_actividad_pui = coalesce(is_cind_derivada_pui, FALSE),
    datos_insuficientes = coalesce(is_sisf_derivada_rnpdno_pui, FALSE),
    con_vida = coalesce(is_cvid_derivada_rnpdno, FALSE),
    sin_vida = coalesce(is_svid_derivada_rnpdno, FALSE),
    con_delito = coalesce(is_cdel_derivada_rnpdno, FALSE),
    categoria_actividad = case_when(
      con_actividad_pui ~ "Con actividad (registro administrativo en PUI)",
      datos_insuficientes ~ "Datos insuficientes",
      TRUE ~ "Sin actividad PUI a la fecha (CURP válida)"
    ),
    institucion = case_when(
      fiscalia ~ "Fiscalía",
      comision ~ "Comisión",
      portal ~ "Portal",
      TRUE ~ "Sin clasificar"
    )
  )

openxlsx::write.xlsx(Base_maestra_fin,"/Users/alberto/Documents/Base_maestra_fin.xlsx")


#-----Diapositiva 1 ------
resumen <- skim(Base_maestra_fin)
Total_registros <- length(Base_maestra_fin$fub_rnpdno)
Desaparecidas <- Base_maestra_fin %>% filter(desaparecida)
length(Desaparecidas$fub_rnpdno)

localizadas <- Base_maestra_fin %>% filter(localizada)
length(localizadas$fub_rnpdno)





#---------Filtro de fecha

larga_data <- Desaparecidas %>%
  mutate(fecha_filtro = fecha_periodo) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro < ymd("2006-01-01")
  ) 

                       
length(larga_data$fub_rnpdno)



corta_data <- Desaparecidas %>%
  mutate(fecha_filtro = fecha_periodo) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro >= lubridate::ymd("2006-01-01")
  )


length(corta_data$fub_rnpdno)


corta_data %>% group_by(categoria_actividad) %>% count()






#-----localizadas---

localizadas_vida <- localizadas %>% filter(con_vida)
length(localizadas_vida$fub_rnpdno)

localizadas_svida <- localizadas %>% filter(sin_vida)
length(localizadas_svida$fub_rnpdno)


SinDelito <- localizadas %>%
  filter(!con_delito)

ConDelito <- localizadas %>%
  filter(con_delito)

length(ConDelito$fub_rnpdno)
length(SinDelito$fub_rnpdno)



#--- Diapositiva 2---------------

corta_data <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro >= lubridate::ymd("2006-01-01")
  )


length(corta_data$fub_rnpdno)


resumen_actividad <- corta_data %>%
  filter(estatus_loc_derivada_rnpdno == "des") %>%
  mutate(categoria = categoria_actividad)


#------------- Dispositiva 3 corte del 27 de marzo del 2026-------
corta_data_hasta_marzo <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro <= lubridate::ymd("2026-03-25")
  )


#-------Para datos insuficientes---------
table(resumen_actividad$categoria)
actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Datos insuficientes")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
# Línea base congelada de marzo
corte_marzo <- read_excel(
  RUTA$corte_marzo_sisf,
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, corte_marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(corte_marzo, actual_sisf, by = "fub")
length(bajas$fub)



#-----Con actividad------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Con actividad (registro administrativo en PUI)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
marzo <- read_excel(
  RUTA$corte_marzo_cind,
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)







#-----Sin actividad-------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Sin actividad PUI a la fecha (CURP válida)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
marzo <- read_excel(
  RUTA$corte_marzo_sind,
  col_types = "text"
) %>%
  transmute(fub = str_trim(fub)) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)






#-------------Dispopsitiva 4 corte del 1 de julio del 2026-------
corta_data_hasta_julio <- Desaparecidas %>%
  mutate(
    fecha_filtro = as.Date(fecha_hechos_modificada_derivada_rnpdno)
  ) %>%
  filter(
    estatus_loc_derivada_rnpdno == "des",
    !is.na(fecha_filtro),
    fecha_filtro <= lubridate::ymd("2026-07-01")
  )


#-------Para datos insuficientes---------
table(resumen_actividad$categoria)
actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Datos insuficientes")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
# Línea base congelada de marzo
corte_marzo <- read_excel(
  RUTA$corte_julio_sisf,
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, corte_marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(corte_marzo, actual_sisf, by = "fub")
length(bajas$fub)



#-----Con actividad------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Con actividad (registro administrativo en PUI)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
marzo <- read_excel(
  RUTA$corte_julio_cind,
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)







#-----Sin actividad-------


actual_sisf <- resumen_actividad %>% mutate(fub=fub_rnpdno) %>% filter(categoria=="Sin actividad PUI a la fecha (CURP válida)")
#    Datos insuficientes
#    Con actividad (registro administrativo en PUI)
#    Sin actividad PUI a la fecha (CURP válida)
marzo <- read_excel(
  RUTA$corte_julio_sind,
  col_types = "text"
) %>%
  transmute(fub = fub_rnpdno) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub)

# FUB del indicador actual que no estaban en marzo
altas <- anti_join(actual_sisf, marzo, by = "fub")
length(altas$fub_rnpdno)

# FUB que estaban en marzo y ya no están en el indicador actual
bajas <- anti_join(marzo, actual_sisf, by = "fub")
length(bajas$fub)


#-------------  Diapositiva 5 y 6   Victima con carpeta de investigacion valida octubre 24 hasta  la fecha-----


base_desde_octubre <- Base_maestra_fin %>%
  mutate(fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno)) %>%
  filter(
    is.na(fecha_periodo) | fecha_periodo >= as.Date("2024-10-01")
  ) 
length(base_desde_octubre$fub_rnpdno)



Desaparecidas <- base_desde_octubre %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Desaparecidos","Pendientes"))
length(Desaparecidas$fub_rnpdno)

localizadas <- base_desde_octubre %>% 
  filter(clasificacion_des_derivada_rnpdno %in%
           c("Localizados"))
length(localizadas$fub_rnpdno)


#---------------Con carpeta de investigacion por desaparicion forzada o particulares


Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>% summarise(
  con_match_banci = sum(tiene_match),
  por_desaparicion_forzada = sum(tiene_match & forzada),
  por_delitos_de_particulares = sum(tiene_match & particulares),
  sin_match_con_folio_valido = sum(!tiene_match & folio_valido),
  sin_match_sin_folio_valido = sum(!tiene_match & !folio_valido),
  sin_match_sin_folio_valido_estruc_inva = sum(!tiene_match & !folio_valido&!campo_vacio),
  sin_match_sin_folio_valido_vacio = sum(!tiene_match & !folio_valido&campo_vacio),
)





localizadas_vida <- localizadas %>% filter(is_cvid_derivada_rnpdno==TRUE)
length(localizadas_vida$fub_rnpdno)

localizadas_svida <- localizadas %>% filter(is_svid_derivada_rnpdno==TRUE)
length(localizadas_svida$fub_rnpdno)







SinDelito <- localizadas %>%
  filter(!replace_na(is_cdel_derivada_rnpdno, FALSE))
length(SinDelito$fub_rnpdno)

ConDelito <- localizadas %>%
  filter(replace_na(is_cdel_derivada_rnpdno, FALSE))

length(ConDelito$fub_rnpdno)



#---------Diapositiva 7  - Antes y despues de agosto

otros_delitos <- Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & folio_valido) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")





# Estructura invalida
invalida <-  Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & !folio_valido&!campo_vacio) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")








#Campo vacio
campo_vacio <- Desaparecidas %>% mutate(
  fecha = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)) %>% 
  filter(!tiene_match & !folio_valido&campo_vacio) %>% 
  mutate(
    periodo = case_when(
      !is.na(fecha) &
        fecha >= as.Date("2024-10-01") &
        fecha < as.Date("2025-08-01") ~ "Oct 2024–jul 2025",
      !is.na(fecha) &
        fecha >= as.Date("2025-08-01") ~ "Desde ago 2025",
      TRUE ~ NA_character_
    )
  ) %>%
  filter(!is.na(periodo)) %>%
  count(periodo, name = "registros")




# ----Lamina 9  ----


con_carpeta_FIN_9 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>% filter(tiene_match==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()


 



# ----Lamina 10  ----


con_carpeta_FIN_1O <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & folio_valido==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()







# ----Lamina 11  ----


con_carpeta_FIN_O_11 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 12  ----


con_carpeta_FIN_O_12 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()




# ----Lamina 13  ----


con_carpeta_FIN_O_13 <- Desaparecidas %>% mutate(
  fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
  tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
  folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
  forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
  particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
  campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE)
) %>%   filter(!tiene_match==TRUE & !folio_valido&campo_vacio==TRUE) %>% mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha) %>% count()


# ----Lamina 14  ----
con_carpeta_FIN_O_14 <- Desaparecidas %>% 
  mutate( grupo = case_when(
  coalesce(is_sisf_derivada_rnpdno_pui, FALSE) ~
    "Datos insuficientes",
  coalesce(is_cind_derivada_pui, FALSE) ~
    "Con actividad PUI",
  TRUE ~
    "Sin actividad PUI (CURP válida)")) %>% 
  mutate(Fecha=format(fecha_periodo, "%Y-%m")) %>% 
  group_by(Fecha,grupo) %>% count()








# ----Lamina 16  ----
con_carpeta_FIN_O_16 <- Desaparecidas %>% 
    mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% filter(!tiene_match==TRUE & folio_valido==TRUE) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
             institucion = case_when(
               fiscalia ~ "Fiscalía",
               comision ~ "Comisión",
               portal ~ "Portal",
               TRUE ~ "Sin clasificar"
             )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()







# ----Lamina 17  ----
con_carpeta_FIN_O_17 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()













# ----Lamina 18  ----
con_carpeta_FIN_O_18 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & folio_valido==TRUE&fecha_periodo>= as.Date("2026-08-01") ) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()







# ----Lamina 19  ----
con_carpeta_FIN_O_19 <- Desaparecidas %>% 
  mutate(
    fecha_periodo = as.Date(fecha_hechos_modificada_derivada_rnpdno),
    tiene_match = coalesce(in_banci_derivada_rnpdno_banci, FALSE),
    folio_valido = coalesce(is_cfval_derivada_rnpdno, FALSE),
    forzada = coalesce(is_dfor_derivada_rnpdno_banci, FALSE),
    particulares = coalesce(is_cpar_derivada_rnpdno_banci, FALSE),
    campo_vacio = coalesce(is_cfvac_derivada_rnpdno, FALSE),
    fiscalia = coalesce(is_fis_derivada_rnpdno_banci, FALSE),
    comision = coalesce(is_com_derivada_rnpdno_banci, FALSE),
    portal = coalesce(is_por_derivada_rnpdno_banci, FALSE)) %>% 
  filter(!tiene_match==TRUE & !folio_valido&!campo_vacio==TRUE&fecha_periodo>= as.Date("2026-08-01")) %>%   
  mutate(Fecha=format(fecha_periodo, "%Y-%m"),
         institucion = case_when(
           fiscalia ~ "Fiscalía",
           comision ~ "Comisión",
           portal ~ "Portal",
           TRUE ~ "Sin clasificar"
         )) %>% 
  group_by( institucion,nombre_entidad_derivada_rnpdno) %>% count()













# ----Lamina 20  ---
ruta_parquet <- RUTA$base_total
ruta_directorio <- RUTA$directorio_indicios

entidades_participantes <- c(
  "Estado de México", "Tamaulipas", "Michoacán", "Sinaloa", "Guerrero",
  "Veracruz", "Ciudad de México", "Sonora", "Baja California", "Zacatecas",
  "Puebla", "Nayarit", "Chiapas", "Tabasco", "Hidalgo", "San Luis Potosí",
  "Quintana Roo", "Morelos", "Colima", "Baja California Sur", "Oaxaca",
  "Yucatán", "Tlaxcala", "Campeche"
)

# Clasificación actual en RNPDNO. El FUB se conserva como texto.
rn <- read_parquet(ruta_parquet, as_data_frame = TRUE) %>%
  transmute(
    fub = str_to_upper(str_trim(as.character(fub_rnpdno))),
    clasificacion = as.character(clasificacion_des_derivada_rnpdno)
  ) %>%
  filter(!is.na(fub), fub != "") %>%
  distinct(fub, .keep_all = TRUE)

# Directorio congelado al 24/06/2026.
directorio <- read_excel(ruta_directorio, sheet = 1) %>%
  transmute(
    fub = str_to_upper(str_trim(as.character(FUB))),
    entidad = str_trim(as.character(`Estado de Desaparición`))
  ) %>%
  filter(!is.na(fub), fub != "") %>%
  mutate(
    entidad = na_if(entidad, ""),
    entidad = replace_na(entidad, "Sin información"),
    entidad = recode(entidad, "México" = "Estado de México")
  ) %>%
  distinct(fub, .keep_all = TRUE)

# Cruce del directorio con el estatus actual de RNPDNO.
base <- directorio %>%
  left_join(rn, by = "fub") %>%
  mutate(
    participante = entidad %in% entidades_participantes,
    formalizada = clasificacion == "Localizados",
    todavia_desaparecida =
      clasificacion %in% c("Desaparecidos", "Pendientes") | is.na(clasificacion)
  )


# Desglose por entidad: universo del directorio, formalizaciones y pendientes.
por_entidad <- base %>%
  group_by(entidad, participante) %>%
  summarise(
    personas_directorio = n(),
    formalizadas = sum(formalizada, na.rm = TRUE),
    todavia_desaparecidas = sum(todavia_desaparecida, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  arrange(desc(participante), desc(personas_directorio))

sum(por_entidad$personas_directorio)
# Totales: entidades participantes frente a las demás.
resumen <- base %>%
  mutate(grupo = if_else(participante, "Participantes", "Otras entidades")) %>%
  group_by(grupo) %>%
  summarise(
    personas_directorio = n(),
    formalizadas = sum(formalizada, na.rm = TRUE),
    todavia_desaparecidas = sum(todavia_desaparecida, na.rm = TRUE),
    .groups = "drop"
  )

# Total del país: formalizaciones de todo el directorio, sin limitar a las 24 entidades.
total_pais <- sum(base$formalizada, na.rm = TRUE)
formalizadas_participantes <- sum(base$formalizada & base$participante, na.rm = TRUE)

print(por_entidad, n = Inf)
print(resumen)
cat("Formalizadas en entidades participantes:", formalizadas_participantes, "\n")
cat("Formalizadas en todo el país:", total_pais, "\n")
cat("Formalizadas fuera de las entidades participantes:",
    total_pais - formalizadas_participantes, "\n")








# ----Lamina 21  ----

base %>%
  summarise(
    formalizadas_participantes = sum(formalizada & participante, na.rm = TRUE),
    formalizadas_otras = sum(formalizada & !participante, na.rm = TRUE),
    formalizadas_total_pais = sum(formalizada, na.rm = TRUE)
  )

# ----Lamina 22  ----


ruta_mj_rips <- RUTA$mj_rips

mj <- read_excel(ruta_mj_rips, sheet = "MJ UNICOS") %>%
  transmute(
    fub = str_to_upper(str_trim(as.character(FUB))),
    tipo = "MJ"
  )

rips <- read_excel(ruta_mj_rips, sheet = "RIPS UNICOS") %>%
  transmute(
    fub = str_to_upper(str_trim(as.character(FUB))),
    tipo = "RIPS"
  )

# Se concatenan las dos hojas; no usar distinct() aquí.
mr <- bind_rows(mj, rips)

# Conteo de registros por hoja y total
conteo_hojas <- mr %>%
  count(tipo, name = "registros")

conteo_total <- mr %>%
  summarise(
    registros_totales = n(),
    fubs_unicos = n_distinct(fub),
    registros_sin_fub = sum(is.na(fub) | fub == "")
  )

ruta_rn <- RUTA$base_total

rn <- read_parquet(
  ruta_rn,
  col_select = c(
    fub_rnpdno,
    estatus_loc_derivada_rnpdno,
    is_cvid_derivada_rnpdno,
    is_svid_derivada_rnpdno
  )
) %>%
  transmute(
    fub = str_to_upper(str_trim(as.character(fub_rnpdno))),
    estatus_loc = as.character(estatus_loc_derivada_rnpdno),
    con_vida = is_cvid_derivada_rnpdno,
    sin_vida = is_svid_derivada_rnpdno
  ) %>%
  distinct(fub, .keep_all = TRUE)

mr_con_estatus <- mr %>%
  left_join(rn, by = "fub") %>%
  mutate(
    estatus_loc = coalesce(estatus_loc, "des"),
    con_vida = replace_na(con_vida, FALSE),
    sin_vida = replace_na(sin_vida, FALSE)
  )

resumen <- mr_con_estatus  %>%
  summarise(
    total_registros = n(),
    desaparecidas_o_sin_cruce = sum(estatus_loc != "loc"),
    localizadas = sum(estatus_loc == "loc"),
    localizadas_con_vida = sum(estatus_loc == "loc" & con_vida),
    localizadas_sin_vida = sum(estatus_loc == "loc" & sin_vida)
  )

resumen
