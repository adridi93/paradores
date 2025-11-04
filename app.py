import streamlit as st
import re
from time import sleep
import datetime

# --- Importaciones de Selenium ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# --- Opciones de Chrome (¡ROBUSTAS!) ---
# Usamos una función para configurar las opciones
def get_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
    chrome_options.add_argument('--blink-settings=imagesEnabled=false')
    return chrome_options

# --- FUNCIÓN PRINCIPAL DEL SCRAPER ---
# Acepta las variables y los objetos de Streamlit para reportar el progreso
def find_paradores(fecha_entrada, fecha_salida, codigo_promo, progress_bar, status_text):
    
    resultados_disponibles = []
    PRIMER_PARADOR = 1
    ULTIMO_PARADOR = 90 # Puedes bajarlo a 5 para pruebas rápidas
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=get_chrome_options())
    except Exception as e:
        st.error(f"Error al iniciar el navegador (WebDriver): {e}")
        st.error("Asegúrate de que Google Chrome está instalado en tu sistema si ejecutas localmente.")
        return []

    wait = WebDriverWait(driver, 6) 
    cookie_wait = WebDriverWait(driver, 3) 

    for num in range(PRIMER_PARADOR, ULTIMO_PARADOR + 1):
        codigo_parador = str(num).zfill(3)
        url = f"https://paradores.es/es/reservas/parador/{codigo_parador}/{fecha_entrada}/{fecha_salida}"
        
        # --- Reportar Progreso a Streamlit ---
        progress_percentage = num / ULTIMO_PARADOR
        progress_bar.progress(progress_percentage)
        
        try:
            driver.get(url) 

            # Capturamos el nombre del Parador
            nombre_parador = f"Parador {codigo_parador}"
            try:
                label_nombre = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "label[data-drupal-selector='edit-title']")))
                nombre_parador = label_nombre.text.strip()
                status_text.text(f"({num}/{ULTIMO_PARADOR}) Comprobando: {nombre_parador}...")
            except TimeoutException:
                status_text.text(f"({num}/{ULTIMO_PARADOR}) Comprobando: Parador {codigo_parador}...")

            # PASO 0: Rechazar cookies
            try:
                cookie_button = cookie_wait.until(EC.element_to_be_clickable((By.ID, "hs-eu-decline-button")))
                cookie_button.click()
            except TimeoutException:
                pass # No hay banner

            # PASO 1: Página de promo
            if codigo_promo:
                try:
                    input_promo = wait.until(EC.element_to_be_clickable((By.NAME, "promocod")))
                    input_promo.clear()
                    input_promo.send_keys(codigo_promo)
                except TimeoutException:
                    continue # Error en promo, saltar

            # 1b. Pulsamos "RESERVAR"
            try:
                boton_reservar = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "js-booking-next")))
                driver.execute_script("arguments[0].click();", boton_reservar)
            except TimeoutException:
                continue # No se puede continuar

            # PASO 2: Página de Login
            try:
                boton_continuar = wait.until(EC.element_to_be_clickable((By.ID, "edit-next"))) 
                boton_continuar.click()
            except TimeoutException:
                continue 

            # PASO 3: Página de Disponibilidad
            try:
                # 3a. Buscamos si está COMPLETO
                wait.until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(),'No hay disponibilidad') or contains(text(),'Completo')]")))
                # (No hacemos nada, solo pasamos al siguiente)
            
            except TimeoutException:
                # 3b. Si NO está completo, buscamos las habitaciones (¡éxito!)
                try:
                    wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "booking-container-rooms-top")))
                    
                    habitaciones = driver.find_elements(By.CLASS_NAME, "booking-container-rooms-top")
                    precio_mas_bajo = float('inf') 
                    
                    for habitacion in habitaciones:
                        try:
                            precio_elem = habitacion.find_element(By.CLASS_NAME, "price")
                            precio_str = precio_elem.text.strip()
                            precio_limpio = precio_str.replace(' €', '').replace('.', '').replace(',', '.')
                            precio_num = float(precio_limpio)
                            
                            if precio_num < precio_mas_bajo:
                                precio_mas_bajo = precio_num
                        except (NoSuchElementException, ValueError):
                            pass # Error al leer precio de una habitación
                    
                    if precio_mas_bajo != float('inf'):
                        resultados_disponibles.append({
                            'nombre': nombre_parador,
                            'codigo': codigo_parador,
                            'precio_min': precio_mas_bajo,
                            'url': url
                        })
                except TimeoutException:
                    pass # Página desconocida

        except Exception as e:
            st.warning(f"Error grave en {nombre_parador}: {e}") # Reportar error en la UI

    driver.quit()
    
    # Ordenamos y devolvemos los resultados
    return sorted(resultados_disponibles, key=lambda x: x['precio_min'])

# =============================================================================
# --- INTERFAZ DE STREAMLIT ---
# =============================================================================

st.set_page_config(page_title="Buscador Paradores", layout="wide")
st.title("🔎 Buscador de Ofertas en Paradores")

# --- Formulario de entrada ---
with st.form(key="search_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        # Usamos fechas de 2025 como ejemplo
        default_in = datetime.date(2025, 11, 9)
        default_out = datetime.date(2025, 11, 10)
        
        fecha_e_obj = st.date_input("Fecha de Entrada", value=default_in)
        fecha_s_obj = st.date_input("Fecha de Salida", value=default_out)
    
    with col2:
        promo = st.text_input("Código Promocional (opcional)", value="OFERTA2025")
        
    submit_button = st.form_submit_button(label="🚀 ¡Buscar disponibilidad!")

# --- Lógica de ejecución ---
if submit_button:
    if fecha_e_obj >= fecha_s_obj:
        st.error("Error: La fecha de salida debe ser posterior a la de entrada.")
    else:
        # Formateamos las fechas al formato DD-MM-YYYY que necesita el script
        FECHA_ENTRADA_STR = fecha_e_obj.strftime("%d-%m-%Y")
        FECHA_SALIDA_STR = fecha_s_obj.strftime("%d-%m-%Y")

        st.info("Iniciando búsqueda... Esto puede tardar varios minutos (15-20 min). ¡Ten paciencia!")
        
        # Creamos los elementos para la barra de progreso y el texto de estado
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("Conectando y rechazando cookies..."):
            # Ejecutamos la función principal
            resultados_ordenados = find_paradores(
                FECHA_ENTRADA_STR, 
                FECHA_SALIDA_STR, 
                promo, 
                progress_bar, 
                status_text
            )
        
        # --- Mostrar resultados ---
        status_text.success("¡Búsqueda finalizada!")
        progress_bar.empty()
        st.balloons()

        if not resultados_ordenados:
            st.warning("No se encontraron Paradores disponibles con esos criterios.")
        else:
            st.subheader(f"🏆 {len(resultados_ordenados)} Paradores encontrados (ordenados por precio):")
            
            for parador in resultados_ordenados:
                precio_formateado = f"{parador['precio_min']:.2f} €"
                
                # Usamos markdown para el formato y el enlace
                st.markdown(f"""
                <div style="border: 1px solid #ddd; border-radius: 5px; padding: 10px; margin-bottom: 10px;">
                    <span style="font-size: 1.2em; font-weight: bold;">{parador['nombre']} ({parador['codigo']})</span><br>
                    <strong>Precio desde: <span style="color: green; font-size: 1.1em;">{precio_formateado}</span></strong><br>
                    <a href="{parador['url']}" target="_blank">Ver enlace de reserva</a>
                </div>
                """, unsafe_allow_html=True)
