import libsql_client
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Sistema de Gestión Escolar", page_icon="📚", layout="wide"
)

# --- ESTILOS CSS PERSONALIZADOS (Diseño de Tarjetas Modernas) ---
st.markdown(
    """
    <style>
    .card-menu {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #e5e7eb;
        margin-bottom: 15px;
        transition: transform 0.2s;
    }
    .card-menu:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
    }
    .card-title {
        font-size: 16px;
        font-weight: 600;
        color: #1f2937;
        margin-top: 10px;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# --- CONEXIÓN A LA BASE DE DATOS (TURSO EN LA NUBE) ---
def obtener_conexion():
  try:
    url = st.secrets["TURSO_DATABASE_URL"]
    token = st.secrets["TURSO_AUTH_TOKEN"]
    client = libsql_client.create_client(url=url, auth_token=token)
    return client
  except Exception as e:
    st.error(f"Error al conectar con la base de datos en la nube: {e}")
    return None


# --- FUNCIÓN CORREGIDA DE CLONACIÓN (Grupo + Alumnos sin sufijo) ---
def clonar_plantilla_grupo(client, grupo_origen_id, id_docente_actual):
  # 1. Obtener el nombre original del grupo (SIN agregar sufijos)
  res_grupo = client.execute(
      "SELECT name FROM grupos WHERE id = ?", [grupo_origen_id]
  )
  if not res_grupo.rows:
    return False
  nombre_original = res_grupo.rows[0]["name"]

  # 2. Crear el grupo en el espacio del docente actual
  cursor_nuevo = client.execute(
      "INSERT INTO grupos (name, teacher_id) VALUES (?, ?)",
      [nombre_original, id_docente_actual],
  )
  nuevo_grupo_id = cursor_nuevo.last_insert_rowid

  # 3. Copiar y reasignar TODOS los alumnos del grupo origen al nuevo grupo
  res_alumnos = client.execute(
      "SELECT * FROM alumnos WHERE grupo_id = ?", [grupo_origen_id]
  )
  for alumno in res_alumnos.rows:
    client.execute(
        """INSERT INTO alumnos (grupo_id, numero_lista, nombre, calificacion) 
               VALUES (?, ?, ?, ?)""",
        [
            nuevo_grupo_id,
            alumno["numero_lista"],
            alumno["nombre"],
            alumno.get("calificacion", 0),
        ],
    )
  return True


# --- GESTIÓN DE ESTADO DE NAVEGACIÓN ---
if "menu" not in st.session_state:
  st.session_state["menu"] = "Inicio"

# Simulación de sesión de docente activo (ajustable según tu sistema de usuarios)
if "docente_actual_id" not in st.session_state:
  st.session_state["docente_actual_id"] = 1  # ID de prueba

# --- BARRA LATERAL (Navegación rápida) ---
with st.sidebar:
  st.title("Navegación")
  if st.button("🏠 Inicio", use_container_width=True):
    st.session_state["menu"] = "Inicio"
  if st.button("📋 Evaluación", use_container_width=True):
    st.session_state["menu"] = "Evaluación"
  if st.button("👥 Asistencia", use_container_width=True):
    st.session_state["menu"] = "Asistencia"
  if st.button("📝 Bitácora", use_container_width=True):
    st.session_state["menu"] = "Bitácora"
  if st.button("📊 Reportes", use_container_width=True):
    st.session_state["menu"] = "Reportes"
  if st.button("⚙️ Configuración", use_container_width=True):
    st.session_state["menu"] = "Configuración"

  st.markdown("---")
  st.caption("Usuario Activo: Profe. Martín")

# --- VISTA: MENÚ PRINCIPAL (ESTÉTICA DE TARJETAS) ---
if st.session_state["menu"] == "Inicio":
  st.title("Menú Principal")
  st.markdown(
      "Bienvenido a tu espacio de gestión escolar en tiempo real. Selecciona"
      " una opción:"
  )
  st.markdown("---")

  # Fila 1 de Tarjetas
  col1, col2, col3 = st.columns(3)

  with col1:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">📋</h2>
            <div class="card-title">Evaluación</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Evaluación", use_container_width=True):
      st.session_state["menu"] = "Evaluación"
      st.rerun()

  with col2:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">👥</h2>
            <div class="card-title">Asistencia</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Asistencia", use_container_width=True):
      st.session_state["menu"] = "Asistencia"
      st.rerun()

  with col3:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">📝</h2>
            <div class="card-title">Bitácora</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Bitácora", use_container_width=True):
      st.session_state["menu"] = "Bitácora"
      st.rerun()

  # Fila 2 de Tarjetas
  col4, col5, col6 = st.columns(3)

  with col4:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">📊</h2>
            <div class="card-title">Reportes</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Reportes", use_container_width=True):
      st.session_state["menu"] = "Reportes"
      st.rerun()

  with col5:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">☁️</h2>
            <div class="card-title">Respaldo Cloud</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Respaldo", use_container_width=True):
      st.success("Conectado de forma permanente a Turso Cloud.")

  with col6:
    st.markdown(
        """
        <div class="card-menu">
            <h2 style="margin:0;">⚙️</h2>
            <div class="card-title">Configuración</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Abrir Configuración", use_container_width=True):
      st.session_state["menu"] = "Configuración"
      st.rerun()

# --- VISTA: EVALUACIÓN (CON FILTROS Y ORDENAMIENTO) ---
elif st.session_state["menu"] == "Evaluación":
  st.title("📋 Módulo de Evaluación y Listado")
  if st.button("⬅ Volver al Menú Principal"):
    st.session_state["menu"] = "Inicio"
    st.rerun()

  st.markdown("---")

  # Conexión y consulta de prueba
  client = obtener_conexion()
  if client:
    try:
      # Ejemplo cargando alumnos
      resultado = client.execute("SELECT * FROM alumnos")
      rows = resultado.rows

      if rows:
        df = pd.DataFrame(rows)

        # 1. Buscador rápido por nombre
        busqueda = st.text_input("🔍 Buscar alumno por nombre:", "")
        if busqueda:
          df_filtrado = df[
              df["nombre"].str.contains(busqueda, case=False, na=False)
          ]
        else:
          df_filtrado = df.copy()

        # 2. Controles de ordenamiento para la vista
        c1, c2 = st.columns(2)
        with c1:
          opcion_orden = st.selectbox(
              "Ordenar vista por:",
              [
                  "Número de lista (Por defecto)",
                  "Nombre (Alfabético A-Z)",
                  "Calificación",
              ],
          )
        with c2:
          tipo_orden = st.radio(
              "Dirección:", ["Ascendente", "Descendente"], horizontal=True
          )

        es_ascendente = True if tipo_orden == "Ascendente" else False

        if "Número de lista" in opcion_orden:
          df_filtrado = df_filtrado.sort_values(
              by="numero_lista", ascending=es_ascendente
          )
        elif "Nombre" in opcion_orden:
          df_filtrado = df_filtrado.sort_values(
              by="nombre", ascending=es_ascendente
          )
        elif "Calificación" in opcion_orden:
          df_filtrado = df_filtrado.sort_values(
              by="calificacion", ascending=es_ascendente
          )

        # 3. Mostrar tabla interactiva
        st.dataframe(df_filtrado, use_container_width=True)
        st.caption(
            f"Mostrando {len(df_filtrado)} de {len(df)} alumnos registrados."
        )

      else:
        st.info("No hay alumnos registrados en la base de datos todavía.")
    except Exception as e:
      st.warning(
          "Configura tus tablas en Turso o añade registros para visualizar la"
          f" información. (Detalle: {e})"
      )

# --- VISTAS RESTANTES (Estructura base) ---
elif st.session_state["menu"] == "Asistencia":
  st.title("👥 Control de Asistencia")
  if st.button("⬅ Volver al Menú Principal"):
    st.session_state["menu"] = "Inicio"
    st.rerun()

elif st.session_state["menu"] == "Bitácora":
  st.title("📝 Bitácora Escolar")
  if st.button("⬅ Volver al Menú Principal"):
    st.session_state["menu"] = "Inicio"
    st.rerun()

elif st.session_state["menu"] == "Reportes":
  st.title("📊 Generación de Reportes y PDFs")
  if st.button("⬅ Volver al Menú Principal"):
    st.session_state["menu"] = "Inicio"
    st.rerun()

elif st.session_state["menu"] == "Configuración":
  st.title("⚙️ Configuración del Sistema y Clones")
  if st.button("⬅ Volver al Menú Principal"):
    st.session_state["menu"] = "Inicio"
    st.rerun()
  st.write("Aquí puedes gestionar la clonación de grupos y espacios de trabajo.")
