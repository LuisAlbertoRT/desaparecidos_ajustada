from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
import random
from matplotlib.patches import Polygon

from funciones import limpiar_svg_con_scour 
from funciones import get_text_color_for_bg 
from funciones import mostrar_guardar_figura

import textwrap
def wrap_text(text, ax, fig, max_width, fontsize, fontweight):
    if ' ' not in text:
        return text
    for width in range(len(text), 1, -1):
        candidate = '\n'.join(textwrap.wrap(text, width=width, break_long_words=False))
        t = ax.text(0, 0, candidate, fontsize=fontsize, fontweight=fontweight)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bbox = t.get_window_extent(renderer=renderer)
        inv = ax.transData.inverted()
        bbox_data = inv.transform(bbox)
        text_width = bbox_data[1][0] - bbox_data[0][0]
        t.remove()
        if text_width <= max_width:
            return candidate
    # Fuerza una palabra por línea si nada cabe
    candidate = '\n'.join(textwrap.wrap(text, width=1, break_long_words=False))
    return candidate


# Función para ajustar el tamaño de fuente para que el texto no se salga del rectángulo
def ajustar_fontsize(ax, fig, texto, max_width, base_size, fontweight):
    fontsize = base_size
    t = ax.text(0, 0, texto, fontsize=fontsize, fontweight=fontweight)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox = t.get_window_extent(renderer=renderer)
    inv = ax.transData.inverted()
    bbox_data = inv.transform(bbox)
    text_width = bbox_data[1][0] - bbox_data[0][0]
    t.remove()
    while text_width > max_width and fontsize > 6:
        fontsize -= 1
        t = ax.text(0, 0, texto, fontsize=fontsize, fontweight=fontweight)
        fig.canvas.draw()
        bbox = t.get_window_extent(renderer=renderer)
        bbox_data = inv.transform(bbox)
        text_width = bbox_data[1][0] - bbox_data[0][0]
        t.remove()
    return fontsize

def calcular_fontsize(area, base, ajusta_tam_letra):
    base = base * ajusta_tam_letra  
    if area > 0.08:
        return base
    elif area > 0.06:
        return int(base * 20 / 26)
    elif area > 0.04:
        return int(base * 24 / 26)  
    elif area > 0.03:
        return int(base * 16 / 26)
    elif area > 0.02:
        return int(base * 14 / 26)
    elif area > 0.015:
        return int(base * 12 / 26)
    elif area > 0.01:
        return int(base * 11 / 26)
    elif area > 0.008:
        return int(base * 10 / 26)
    elif area > 0.006:
        return int(base * 9 / 26)
    elif area > 0.005:
        return int(base * 4.5 / 26)  
    elif area > 0.003:
        return int(base * 5 / 26)
    elif area > 0.002:
        return int(base * 4 / 26)
    elif area > 0.0015:
        return int(base * 3 / 26)
    elif area > 0.001:
        return int(base * 2.2 / 26)
    elif area > 0.0007:
        return int(base * 1.5 / 26)
    elif area > 0.0005:
        return int(base * 1.1 / 26)
    elif area > 0.0003:
        return int(base * 0.8 / 26)
    elif area > 0.00015:
        return int(base * 0.6 / 26)
    elif area > 0.00007:
        return int(base * 0.45 / 26)
    else:
        return int(base * 0.3 / 26)
    

def piramide(
        df,                             # DataFrame de entrada (primera columna: etiquetas, segunda columna: valores numéricos)
        nombre=None,                    # Nombre base para archivos de salida (str o None)
        area_min=0.001,                 # Área mínima para mostrar texto en el rectángulo (float, típicamente entre 0 y 0.01)
        tipo_letra='Montserrat',        # Tipo de letra para todo el texto en la gráfica (str, ejemplo: 'Montserrat', 'Arial')
        tam_letra_etiqueta=26,          # Tamaño de letra para las etiquetas (int)
        tam_letra_valor=26,             # Tamaño de letra para los valores numéricos (int)
        tam_letra_porcentaje=26,        # Tamaño de letra para los porcentajes (int)
        paleta_colores=None,            # Lista de colores para los rectángulos (list de str HEX, ejemplo: ['#10302C', ...] o None para usar la paleta por defecto)
        porce_parentesis=False,         # Mostrar porcentaje entre paréntesis junto al valor (bool: True/False)
        ancho_fig=12,                   # Ancho de la figura en pulgadas (int o float)
        alto_fig=10,                    # Alto de la figura en pulgadas (int o float)
        color_borde_rec="white",        # Color del borde de los rectángulos (str HEX, ejemplo: 'white', '#000000')
        ancho_borde_rec=1,              # Grosor del borde de los rectángulos (int o float)
        ajusta_sep_valor=0.18,          # Separación vertical entre etiqueta y valor (float, proporcional al alto del rectángulo)
        ajusta_tam_letra=1.0,           # Multiplicador para ajustar el tamaño de letra automáticamente (float, ejemplo: 1.0 para normal, <1 para reducir)
        ajusta_posY_texto=0.5,          # Posición vertical del texto dentro del rectángulo (float entre 0 y 1, 0.5 es centrado)
        ajusta_tam_letra_rec=None,      # Lista de tuplas (índice, tamaño) para ajustar manualmente el tamaño de letra por rectángulo (list o None)
        ajusta_tam_letra_rec_valor=None, # Lista de tuplas (índice, tamaño) para ajustar manualmente el tamaño de letra del valor por rectángulo (list o None)
        ajusta_tam_letra_rec_porce=None, # Lista de tuplas (índice, tamaño) para ajustar manualmente el tamaño de letra del porcentaje por rectángulo (list o None)
        mostrar_fig=True,               # Mostrar la figura al terminar (bool: True/False)
        guardar_fig=True,               # Guardar la figura al terminar (bool: True/False)
        ):

    # Configuración de fuentes y colores
    font_config = {
        'family': tipo_letra,
        'etiquetas': {'size': tam_letra_etiqueta, 'weight': 'bold', 'color': '#ffffff'},
        'valor': {'size': tam_letra_valor, 'weight': 'bold', 'color': '#ffffff'},
        'porcentaje': {'size': tam_letra_porcentaje, 'weight': 'medium', 'color': '#ffffff'}
    }

   # Configuración para que el texto en SVG sea editable.
    plt.rcParams['svg.fonttype'] = 'none'
    # Carga de fuentes personalizadas desde la carpeta de fuentes.
    font_dirs = [Path("../0_fonts")]
    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)
    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)
    plt.rc('font', family=tipo_letra)  # Aplica la fuente a toda la gráfica

    # Asegurar que todos los valores sean numéricos tipo float
    df.iloc[:, 1] = pd.to_numeric(
        df.iloc[:, 1], errors='coerce'
    ).fillna(0).astype(float)

    # Ordenar y calcular porcentaje
    # Para pirámide (base abajo), ordenamos descendente (mayor a menor)
    # y dibujamos desde abajo (y=0) hacia arriba.
    df = df.sort_values(by=df.columns[1], ascending=False).copy()
    total_nacional = df.iloc[:, 1].sum()
    df['Porcentaje'] = (df.iloc[:, 1] / total_nacional * 100).round(1)

    # --- Colores por paleta_colores ---
    n = len(df)
    if paleta_colores is None:
        paleta_colores = ['#10302C', '#4C6A67', '#9B2247', '#9D792A', '#D5B162', '#767676']
    colores = list(paleta_colores[:n])  # Usa solo los colores dados, sin repetir
    if len(colores) < n:
        # Si faltan colores, agrega aleatorios
        for _ in range(n - len(colores)):
            color_rand = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            colores.append(color_rand)

    # Configurar la figura
    plt.rc('font', family=font_config['family'])
    fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig), dpi=300)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.axis('off')  # <-- Oculta los ejes y los números

    # Configuración de la pirámide
    n = len(df)
    
    # Cálculos para pirámide de área proporcional (Sliced Triangle)
    # 1. Valores ordenados de menor a mayor (Top a Bottom para cálculo de altura)
    # df está ordenado de mayor a menor.
    values = df.iloc[:, 1].values
    values_reversed = values[::-1] # Menor a mayor
    
    # 2. Acumulado
    cum_values = values_reversed.cumsum()
    total_val = cum_values[-1]
    
    # 3. Alturas normalizadas desde el ápice (0 a 1)
    # h ~ sqrt(Area)
    norm_heights_from_apex = (cum_values / total_val) ** 0.5
    
    # Insertar 0 al inicio (el ápice)
    norm_heights_from_apex = [0.0] + list(norm_heights_from_apex)
    
    # 4. Escalar a la altura total deseada
    # Usaremos n como altura total para mantener escala similar
    H_total = n
    y_boundaries_from_apex = [h * H_total for h in norm_heights_from_apex]
    
    # 5. Convertir a coordenadas de plot (Base en 0, Ápice en H_total)
    # y_plot = H_total - y_from_apex
    y_boundaries_plot = [H_total - y for y in y_boundaries_from_apex]
    # Esto nos da una lista desde n (Top) hasta 0 (Base).
    
    # Definir ancho base
    # El usuario usaba xlim -0.55 a 0.55 -> Ancho 1.1
    W_base = 1.1
    
    ax.set_xlim(-W_base/2 * 1.1, W_base/2 * 1.1) # Un poco de margen
    ax.set_ylim(0, H_total)
    
    for i, (index, row) in enumerate(df.iterrows()):
        # i=0 es el mayor (Base).
        # Necesitamos el segmento i desde abajo.
        # y_boundaries_plot está ordenado de arriba a abajo.
        # El segmento i (desde abajo) corresponde a los índices -(i+1) y -(i+2) en y_boundaries_plot?
        # i=0 (Base): indices -2 y -1. (n-1 y n).
        # i=1: indices -3 y -2.
        # General: indices -(i+2) y -(i+1).
        
        idx_top = -(i + 2)
        idx_bottom = -(i + 1)
        
        y_top = y_boundaries_plot[len(y_boundaries_plot) + idx_top]
        y_bottom = y_boundaries_plot[len(y_boundaries_plot) + idx_bottom]
        
        # Calcular anchos
        # w = W_base * (dist_from_apex / H_total)
        # dist_from_apex = H_total - y_plot
        
        w_top = W_base * ((H_total - y_top) / H_total)
        w_bottom = W_base * ((H_total - y_bottom) / H_total)
        
        # Coordenadas del polígono (Trapecio)
        # (x, y)
        poly_coords = [
            (-w_bottom / 2, y_bottom),
            (w_bottom / 2, y_bottom),
            (w_top / 2, y_top),
            (-w_top / 2, y_top)
        ]
        
        color = colores[i]
        
        poly = Polygon(poly_coords, facecolor=color, edgecolor=color_borde_rec, linewidth=ancho_borde_rec)
        ax.add_patch(poly)

        # Área relativa para el cálculo del tamaño de fuente
        # En treemap area es fracción del total (0-1). Aquí usamos val/total.
        val = row.iloc[1]
        area = val / total_nacional

        if area > area_min:
            entidad = row.iloc[0]
            entidad_mod = entidad

            # Ajuste de tamaño de fuente siempre proporcional al área
            fontsize_et = calcular_fontsize(area, tam_letra_etiqueta, ajusta_tam_letra)
            fontsize_val = calcular_fontsize(area, tam_letra_valor, ajusta_tam_letra)
            fontsize_pct = calcular_fontsize(area, tam_letra_porcentaje, ajusta_tam_letra)

            # Coordenadas para texto (centrado en la barra)
            # x_text = 0 (centro)
            # y_text = y
            
            color_texto = get_text_color_for_bg(color)

            # Ancho promedio del trapecio para el texto
            dx = (w_top + w_bottom) / 2
            dy = y_top - y_bottom
            y = y_bottom # Base del segmento actual

            max_text_width = dx * 0.92
            max_valor_width = dx * 0.92
            
            # 1. Primer wrap y ajuste de tamaño
            entidad_mod_wrapped = wrap_text(entidad_mod, ax, fig, max_text_width, fontsize_et, font_config['etiquetas']['weight'])
            fontsize_et_ajustado = ajustar_fontsize(ax, fig, entidad_mod_wrapped, max_text_width, fontsize_et, font_config['etiquetas']['weight'])

            # --- Determinar si se debe separar el valor y el porcentaje ---
            override_pct_size = None
            if ajusta_tam_letra_rec_porce is not None:
                for idx, tam in ajusta_tam_letra_rec_porce:
                    if idx == i:
                        override_pct_size = tam
                        break
            
            should_split = (not porce_parentesis) or (override_pct_size is not None)

            if not should_split:
                if porce_parentesis:
                    valor_y_porcentaje = f"{int(row.iloc[1]):,} ({row['Porcentaje']}%)"
                else:
                    valor_y_porcentaje = f"{int(row.iloc[1]):,}\n{row['Porcentaje']}%"
                
                valor_y_porcentaje_wrapped = wrap_text(valor_y_porcentaje, ax, fig, max_valor_width, fontsize_val, font_config['valor']['weight'])
                fontsize_val_ajustado = ajustar_fontsize(ax, fig, valor_y_porcentaje_wrapped, max_valor_width, fontsize_val, font_config['valor']['weight'])

                # 2. Usa el tamaño más pequeño para ambos textos
                fontsize_final_et = min(fontsize_et_ajustado, fontsize_val_ajustado)
                fontsize_final_val = min(fontsize_et_ajustado, fontsize_val_ajustado)

                # --- Ajuste manual de tamaño de letra por rectángulo ---
                if ajusta_tam_letra_rec is not None:
                    for idx, tam in ajusta_tam_letra_rec:
                        if idx == i:
                            fontsize_final_et = tam
                            fontsize_final_val = tam

                # --- Ajuste manual de tamaño de letra del valor por rectángulo ---
                if ajusta_tam_letra_rec_valor is not None:
                    for idx, tam in ajusta_tam_letra_rec_valor:
                        if idx == i:
                            fontsize_final_val = tam

                # 3. Vuelve a aplicar wrap_text con el tamaño final
                entidad_mod_wrapped_final = wrap_text(entidad_mod, ax, fig, max_text_width, fontsize_final_et, font_config['etiquetas']['weight'])
                valor_y_porcentaje_wrapped_final = wrap_text(valor_y_porcentaje, ax, fig, max_valor_width, fontsize_final_val, font_config['valor']['weight'])

                # Dibuja la etiqueta
                text_obj = ax.text(
                    0, # Centrado en X
                    y + dy * ajusta_posY_texto, # Ajuste vertical desde la base del segmento
                    entidad_mod_wrapped_final,
                    ha='center',
                    va='center',
                    fontsize=fontsize_final_et,
                    fontweight=font_config['etiquetas']['weight'],
                    color=color_texto,
                    zorder=10,
                )

                # Calcula la posición real de la parte inferior del texto de la etiqueta
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                bbox = text_obj.get_window_extent(renderer=renderer)
                inv = ax.transData.inverted()
                bbox_data = inv.transform(bbox)
                etiqueta_bottom = bbox_data[0][1]  # y mínimo (parte inferior del texto)

                # Calcula la posición del valor justo debajo de la última línea de la etiqueta
                y_valor = etiqueta_bottom - dy * ajusta_sep_valor

                # Dibuja el valor y porcentaje debajo de la etiqueta
                ax.text(
                    0,
                    y_valor,
                    valor_y_porcentaje_wrapped_final,
                    ha='center',
                    va='top',
                    fontsize=fontsize_final_val,
                    fontweight=font_config['valor']['weight'],
                    color=color_texto,
                    zorder=10,
                )
            else:
                # --- Lógica separada (nueva) ---
                valor_text = f"{int(row.iloc[1]):,}"
                if porce_parentesis:
                    porce_text = f"({row['Porcentaje']}%)"
                else:
                    porce_text = f"{row['Porcentaje']}%"

                valor_wrapped = wrap_text(valor_text, ax, fig, max_valor_width, fontsize_val, font_config['valor']['weight'])
                fontsize_val_ajustado = ajustar_fontsize(ax, fig, valor_wrapped, max_valor_width, fontsize_val, font_config['valor']['weight'])

                porce_wrapped = wrap_text(porce_text, ax, fig, max_valor_width, fontsize_pct, font_config['porcentaje']['weight'])
                fontsize_pct_ajustado = ajustar_fontsize(ax, fig, porce_wrapped, max_valor_width, fontsize_pct, font_config['porcentaje']['weight'])

                # 2. Usa el tamaño más pequeño como base
                min_fontsize = min(fontsize_et_ajustado, fontsize_val_ajustado, fontsize_pct_ajustado)
                fontsize_final_et = min_fontsize
                fontsize_final_val = min_fontsize
                fontsize_final_pct = min_fontsize

                # --- Ajuste manual de tamaño de letra por rectángulo ---
                if ajusta_tam_letra_rec is not None:
                    for idx, tam in ajusta_tam_letra_rec:
                        if idx == i:
                            fontsize_final_et = tam
                            fontsize_final_val = tam
                            fontsize_final_pct = tam

                # --- Ajuste manual de tamaño de letra del valor por rectángulo ---
                if ajusta_tam_letra_rec_valor is not None:
                    for idx, tam in ajusta_tam_letra_rec_valor:
                        if idx == i:
                            fontsize_final_val = tam
                
                # --- Ajuste manual de tamaño de letra del porcentaje por rectángulo ---
                if override_pct_size is not None:
                    fontsize_final_pct = override_pct_size

                # 3. Vuelve a aplicar wrap_text con el tamaño final
                entidad_mod_wrapped_final = wrap_text(entidad_mod, ax, fig, max_text_width, fontsize_final_et, font_config['etiquetas']['weight'])
                valor_wrapped_final = wrap_text(valor_text, ax, fig, max_valor_width, fontsize_final_val, font_config['valor']['weight'])
                porce_wrapped_final = wrap_text(porce_text, ax, fig, max_valor_width, fontsize_final_pct, font_config['porcentaje']['weight'])

                # Dibuja la etiqueta
                text_obj = ax.text(
                    0,
                    y + dy * ajusta_posY_texto,
                    entidad_mod_wrapped_final,
                    ha='center',
                    va='center',
                    fontsize=fontsize_final_et,
                    fontweight=font_config['etiquetas']['weight'],
                    color=color_texto,
                    zorder=10,
                )

                # Calcula posición etiqueta
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                bbox = text_obj.get_window_extent(renderer=renderer)
                inv = ax.transData.inverted()
                bbox_data = inv.transform(bbox)
                etiqueta_bottom = bbox_data[0][1]

                y_valor = etiqueta_bottom - dy * ajusta_sep_valor

                # Dibuja valor
                text_val_obj = ax.text(
                    0,
                    y_valor,
                    valor_wrapped_final,
                    ha='center',
                    va='top',
                    fontsize=fontsize_final_val,
                    fontweight=font_config['valor']['weight'],
                    color=color_texto,
                    zorder=10,
                )

                # Calcula posición valor
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                bbox_val = text_val_obj.get_window_extent(renderer=renderer)
                inv = ax.transData.inverted()
                bbox_val_data = inv.transform(bbox_val)
                valor_bottom = bbox_val_data[0][1]

                # Dibuja porcentaje
                ax.text(
                    0,
                    valor_bottom,
                    porce_wrapped_final,
                    ha='center',
                    va='top',
                    fontsize=fontsize_final_pct,
                    fontweight=font_config['porcentaje']['weight'],
                    color=color_texto,
                    zorder=10,
                )

    plt.tight_layout()

    mostrar_guardar_figura(
        fig=fig,
        ax=ax,
        nombre_df=nombre or "piramide",
        guardar_fig=guardar_fig,         # <-- Usa el argumento aquí
        mostrar_fig=mostrar_fig,         # <-- Usa el argumento aquí
        limpiar_svg_con_scour=limpiar_svg_con_scour
    )