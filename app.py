import calendar
from datetime import datetime, date
import io
import sqlite3
import json
from fpdf import FPDF
import pandas as pd
import streamlit as st

# Intentar importar librerías para Gemini Vision
try:
    import google.generativeai as genai
    from PIL import Image
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# --- CONFIGURACIÓN DE LA BASE DE DATOS (CON TIMEOUT PARA EVITAR BLOQUEOS) ---
conn = sqlite3.connect(
    "escuela.db", timeout=30.0, check_same_thread=False
)
cursor = conn.cursor()

# Crear tablas base si no existen
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        rol TEXT
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS grupos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        username TEXT
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS alumnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_lista INTEGER,
        nombre TEXT,
        sexo TEXT,
        turno TEXT,
        estatus TEXT DEFAULT 'Activo',
        fecha_alta TEXT,
        fecha_baja TEXT,
        grupo_id INTEGER,
        FOREIGN KEY(grupo_id) REFERENCES grupos(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS asistencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        fecha TEXT,
        estado TEXT,
        FOREIGN KEY(alumno_id) REFERENCES alumnos(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS calificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        periodo TEXT,
        calificacion REAL,
        FOREIGN KEY(alumno_id) REFERENCES alumnos(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS bitacora (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        fecha TEXT,
        incidencia TEXT,
        FOREIGN KEY(alumno_id) REFERENCES alumnos(id)
    )
"""
)

# Tablas para actividades, ponderaciones y fechas de periodos
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS actividades_eval (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER,
        periodo TEXT,
        nombre TEXT,
        tipo TEXT,
        fecha TEXT,
        FOREIGN KEY(grupo_id) REFERENCES grupos(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS calificaciones_det (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alumno_id INTEGER,
        actividad_id INTEGER,
        calificacion REAL,
        FOREIGN KEY(alumno_id) REFERENCES alumnos(id),
        FOREIGN KEY(actividad_id) REFERENCES actividades_eval(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS ponderaciones_cat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER,
        periodo TEXT,
        pct_tareas REAL DEFAULT 20.0,
        pct_actividades REAL DEFAULT 20.0,
        pct_proyectos REAL DEFAULT 40.0,
        pct_asistencia REAL DEFAULT 20.0,
        FOREIGN KEY(grupo_id) REFERENCES grupos(id)
    )
"""
)

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS config_fechas_periodos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        periodo TEXT,
        fecha_inicio TEXT,
        fecha_fin TEXT,
        UNIQUE(username, periodo)
    )
"""
)
conn.commit()

# --- MIGRACIÓN AUTOMÁTICA PARA TABLAS EXISTENTES ---
cursor.execute("PRAGMA table_info(ponderaciones_cat)")
cols_pc = [info[1] for info in cursor.fetchall()]
if "pct_asistencia" not in cols_pc:
    cursor.execute("ALTER TABLE ponderaciones_cat ADD COLUMN pct_asistencia REAL DEFAULT 20.0")
    conn.commit()

cursor.execute("PRAGMA table_info(actividades_eval)")
cols_ae = [info[1] for info in cursor.fetchall()]
if "tipo" not in cols_ae:
    cursor.execute("ALTER TABLE actividades_eval ADD COLUMN tipo TEXT")
    conn.commit()
if "fecha" not in cols_ae:
    cursor.execute(
        "ALTER TABLE actividades_eval ADD COLUMN fecha TEXT DEFAULT '2026-01-01'"
    )
    conn.commit()

cursor.execute("PRAGMA table_info(grupos)")
cols_g = [info[1] for info in cursor.fetchall()]
if "username" not in cols_g:
    cursor.execute("ALTER TABLE grupos ADD COLUMN username TEXT")
    conn.commit()

cursor.execute("PRAGMA table_info(alumnos)")
cols_a = [info[1] for info in cursor.fetchall()]
if "numero_lista" not in cols_a:
    cursor.execute("ALTER TABLE alumnos ADD COLUMN numero_lista INTEGER")
if "sexo" not in cols_a:
    cursor.execute("ALTER TABLE alumnos ADD COLUMN sexo TEXT")
if "turno" not in cols_a:
    cursor.execute("ALTER TABLE alumnos ADD COLUMN turno TEXT")
if "estatus" not in cols_a:
    cursor.execute(
        "ALTER TABLE alumnos ADD COLUMN estatus TEXT DEFAULT 'Activo'"
    )
if "fecha_alta" not in cols_a:
    cursor.execute("ALTER TABLE alumnos ADD COLUMN fecha_alta TEXT")
if "fecha_baja" not in cols_a:
    cursor.execute("ALTER TABLE alumnos ADD COLUMN fecha_baja TEXT")
conn.commit()

# Crear usuario Administrador por defecto si no existe
cursor.execute(
    "SELECT COUNT(*) FROM usuarios WHERE username = 'MOyervides'"
)
if cursor.fetchone()[0] == 0:
    cursor.execute(
        "INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
        ("MOyervides", "2993", "Administrador"),
    )
    conn.commit()


# --- CLASE PARA GENERAR PDFS ---
class PDF(FPDF):

    def header(self):
        self.set_font("helvetica", "B", 12)
        self.cell(0, 10, "SISTEMA DE GESTIÓN ESCOLAR - REPORTE OFICIAL", 0, 1, "C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(
            0,
            10,
            f"Página {self.page_no()} | Elaborado por: Ing. Martin Alonso Oyervides - Copyright",
            0,
            0,
            "C",
        )


# --- CONFIGURACIÓN DE LA INTERFAZ ---
st.set_page_config(
    page_title="Sistema de Gestión Escolar", page_icon="📚", layout="wide"
)

# --- SISTEMA DE LOGIN ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

if not st.session_state.logged_in:
    st.markdown(
        "<h2 style='text-align: center;'>🔐 Acceso al Sistema Escolar</h2>",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            user_input = st.text_input("Usuario").strip()
            pass_input = st.text_input("Contraseña", type="password").strip()
            submit_login = st.form_submit_button("Ingresar al Sistema")

            if submit_login:
                with st.spinner("Validando credenciales..."):
                    cursor.execute(
                        "SELECT rol FROM usuarios WHERE username = ? AND password = ?",
                        (user_input, pass_input),
                    )
                    user_record = cursor.fetchone()
                    if user_record:
                        st.session_state.logged_in = True
                        st.session_state.username = user_input
                        st.session_state.role = user_record[0]
                        st.success("¡Bienvenido! Entrando al sistema...")
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
    st.stop()


# --- APLICACIÓN PRINCIPAL ---
st.title("📚 Sistema Integral de Evaluación y Asistencia")
st.sidebar.title("Menú Principal")

menu_options = [
    "🏠 Inicio",
    "👥 Mis Grupos y Alumnos",
    "📂 Plantillas de Otros Docentes",
    "✅ Asistencia",
    "📊 Evaluaciones",
    "📝 Bitácora",
    "📄 Reportes y PDFs",
]

if st.session_state.role == "Administrador":
    menu_options.append("🔑 Gestión de Usuarios")

menu = st.sidebar.radio("Navegación", menu_options)

# Panel de sesión en la barra lateral
st.sidebar.markdown("---")
st.sidebar.write(
    f"👤 **Usuario:** {st.session_state.username} (`{st.session_state.role}`)"
)
if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style='text-align: center;'><small>Elaborado por:<br><b>Ing. Martin Alonso Oyervides</b><br>© Copyright</small></div>",
    unsafe_allow_html=True,
)

current_user = st.session_state.username

# --- 1. INICIO ---
if menu == "🏠 Inicio":
    st.subheader(f"¡Bienvenido, Profesor(a) {current_user}!")
    st.write(
        "Este es tu espacio de trabajo privado. Gestiona tus propios grupos, listas, estatus de alumnos, asistencias y calificaciones."
    )

    c1, c2, c3 = st.columns(3)
    total_grupos = pd.read_sql(
        "SELECT COUNT(*) FROM grupos WHERE username = ?",
        conn,
        params=(current_user,),
    ).iloc[0, 0]
    total_alumnos = pd.read_sql(
        """
        SELECT COUNT(a.id) FROM alumnos a 
        JOIN grupos g ON a.grupo_id = g.id 
        WHERE g.username = ? AND a.estatus = 'Activo'
    """,
        conn,
        params=(current_user,),
    ).iloc[0, 0]

    c1.metric("Mis Grupos", total_grupos)
    c2.metric("Alumnos Activos", total_alumnos)
    c3.metric("Estado del Sistema", "Activo 🟢")

# --- 2. MIS GRUPOS Y ALUMNOS ---
elif menu == "👥 Mis Grupos y Alumnos":
    st.subheader("Gestión de Mis Grupos y Alumnos")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📁 Crear Nuevo Grupo")
        nuevo_grupo = st.text_input(
            "Nombre del Grupo (ej. 1°A, 2°B)"
        ).strip()
        if st.button("Guardar Grupo"):
            if nuevo_grupo:
                with st.spinner("Creando y guardando grupo..."):
                    try:
                        cursor.execute(
                            "INSERT INTO grupos (nombre, username) VALUES (?, ?)",
                            (nuevo_grupo, current_user),
                        )
                        conn.commit()
                        st.success(f"¡Grupo {nuevo_grupo} creado con éxito!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(
                            "Ya tienes un grupo registrado con ese nombre."
                        )
            else:
                st.warning("Escribe un nombre válido.")

    with col2:
        st.markdown("### 👤 Registrar Alumno Manual")
        grupos_df = pd.read_sql(
            "SELECT * FROM grupos WHERE username = ?",
            conn,
            params=(current_user,),
        )
        if not grupos_df.empty:
            grupo_dict = dict(zip(grupos_df["nombre"], grupos_df["id"]))
            grupo_sel = st.selectbox(
                "Selecciona tu Grupo", list(grupo_dict.keys()), key="ind_grupo"
            )

            num_lista = st.number_input(
                "Número de Lista", min_value=1, step=1, value=1
            )
            nombre_alumno = st.text_input(
                "Nombre Completo (Apellidos y Nombre)"
            ).strip()
            sexo_al = st.selectbox("Sexo (Género)", ["M", "F"])
            turno_al = st.selectbox("Turno", ["Matutino", "Vespertino"])
            estatus_al = st.selectbox("Estatus", ["Activo", "Baja"])
            fecha_alta_al = st.date_input(
                "Fecha de Alta", datetime.today()
            ).strftime("%Y-%m-%d")

            fecha_baja_al = None
            if estatus_al == "Baja":
                fecha_baja_al = st.date_input(
                    "Fecha de Baja", datetime.today()
                ).strftime("%Y-%m-%d")

            if st.button("Inscribir Alumno"):
                if nombre_alumno:
                    with st.spinner("Registrando alumno en la base de datos..."):
                        cursor.execute(
                            "SELECT id FROM alumnos WHERE grupo_id = ? AND (numero_lista = ? OR nombre = ?)",
                            (grupo_dict[grupo_sel], num_lista, nombre_alumno),
                        )
                        if cursor.fetchone():
                            st.error(
                                "Ya existe un alumno con ese número de lista o nombre en este grupo."
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO alumnos (numero_lista, nombre, sexo, turno, estatus, fecha_alta, fecha_baja, grupo_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    num_lista,
                                    nombre_alumno,
                                    sexo_al,
                                    turno_al,
                                    estatus_al,
                                    fecha_alta_al,
                                    fecha_baja_al,
                                    grupo_dict[grupo_sel],
                                ),
                            )
                            conn.commit()
                            st.success(
                                f"Alumno {nombre_alumno} registrado con éxito."
                            )
                            st.rerun()
                else:
                    st.warning("Ingresa el nombre del alumno.")
        else:
            st.info("Primero crea al menos un grupo.")

    # --- INYECCIÓN MASIVA CON PLANTILLA ---
    st.markdown("---")
    st.markdown("### 📥 Inyección Masiva (Plantilla Oficial con Estatus)")

    plantilla_df = pd.DataFrame(
        {
            "Número de lista": [1, 2],
            "Nombre del alumno": [
                "Pérez Gómez Juan",
                "López Martínez María",
            ],
            "Sexo": ["M", "F"],
            "Turno": ["Matutino", "Matutino"],
            "Estatus": ["Activo", "Activo"],
        }
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        plantilla_df.to_excel(writer, index=False, sheet_name="Alumnos")
    excel_template_bytes = output.getvalue()

    st.download_button(
        label="⬇️ Descargar Plantilla Oficial de Excel (Con Estatus)",
        data=excel_template_bytes,
        file_name="Plantilla_Oficial_Alumnos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if not grupos_df.empty:
        g_excel = st.selectbox(
            "Selecciona tu grupo destino",
            list(grupo_dict.keys()),
            key="excel_grupo",
        )
        archivo_subido = st.file_uploader(
            "Sube tu archivo Excel llenado con la plantilla",
            type=["xlsx", "csv"],
        )

        if archivo_subido is not None:
            try:
                if archivo_subido.name.endswith(".csv"):
                    df_temp = pd.read_csv(archivo_subido)
                else:
                    df_temp = pd.read_excel(archivo_subido)

                df_temp.columns = df_temp.columns.astype(str).str.strip()
                st.write("Vista previa de los datos detectados:")
                st.dataframe(df_temp.head(5), use_container_width=True)

                if st.button("🚀 Importar Alumnos a mi Grupo"):
                    with st.spinner(
                        "Importando y procesando listado masivo..."
                    ):
                        contador = 0
                        hoy_str = datetime.today().strftime("%Y-%m-%d")
                        for _, row in df_temp.iterrows():
                            try:
                                n_lista = int(row.get("Número de lista", 1))
                            except:
                                n_lista = 1
                            nombre_limpio = str(
                                row.get("Nombre del alumno", "")
                            ).strip()
                            sexo_val = str(row.get("Sexo", "M")).strip()
                            turno_val = str(row.get("Turno", "Matutino")).strip()
                            estatus_val = str(
                                row.get("Estatus", "Activo")
                            ).strip()
                            if estatus_val not in ["Activo", "Baja"]:
                                estatus_val = "Activo"

                            fecha_alta_val = hoy_str
                            fecha_baja_val = (
                                hoy_str if estatus_val == "Baja" else None
                            )

                            if (
                                nombre_limpio
                                and nombre_limpio.lower() != "nan"
                                and "pérez gómez" not in nombre_limpio.lower()
                            ):
                                cursor.execute(
                                    "SELECT id FROM alumnos WHERE grupo_id = ? AND (numero_lista = ? OR nombre = ?)",
                                    (
                                        grupo_dict[g_excel],
                                        n_lista,
                                        nombre_limpio,
                                    ),
                                )
                                if not cursor.fetchone():
                                    cursor.execute(
                                        "INSERT INTO alumnos (numero_lista, nombre, sexo, turno, estatus, fecha_alta, fecha_baja, grupo_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                        (
                                            n_lista,
                                            nombre_limpio,
                                            sexo_val,
                                            turno_val,
                                            estatus_val,
                                            fecha_alta_val,
                                            fecha_baja_val,
                                            grupo_dict[g_excel],
                                        ),
                                    )
                                    contador += 1
                        conn.commit()
                        st.success(
                            f"¡Se han importado {contador} alumnos a tu grupo {g_excel}!"
                        )
                        st.rerun()
            except Exception as e:
                st.error(f"Error al procesar el archivo: {e}")
    else:
        st.info("Crea tus grupos primero.")

    st.markdown("---")
    st.markdown("### 📋 Mis Alumnos Registrados y Estatus")
    if not grupos_df.empty:
        g_ver = st.selectbox(
            "Filtrar por grupo", list(grupo_dict.keys()), key="ver_grupo"
        )
        
        # Opciones de búsqueda y ordenamiento visual añadidas
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            busqueda_al = st.text_input("🔍 Buscar alumno por nombre:", "", key="search_alumnos_mis_grupos")
        with col_f2:
            orden_al = st.selectbox("Ordenar vista por:", ["Número de lista (Por defecto)", "Nombre (Alfabético A-Z)"], key="sort_alumnos_mis_grupos")

        alumnos_grupo = pd.read_sql(
            f"""
            SELECT a.id, a.numero_lista AS 'N° Lista', a.nombre AS 'Nombre del Alumno', a.sexo AS 'Género', a.turno AS 'Turno', a.estatus AS 'Estatus', a.fecha_alta AS 'Fecha Alta', a.fecha_baja AS 'Fecha Baja'
            FROM alumnos a 
            JOIN grupos g ON a.grupo_id = g.id 
            WHERE g.username = '{current_user}' AND g.nombre = '{g_ver}' 
        """,
            conn,
        )
        if not alumnos_grupo.empty:
            df_mostrar = alumnos_grupo.drop(columns=["id"]).copy()
            if busqueda_al:
                df_mostrar = df_mostrar[df_mostrar["Nombre del Alumno"].str.contains(busqueda_al, case=False, na=False)]
            if "Nombre" in orden_al:
                df_mostrar = df_mostrar.sort_values(by="Nombre del Alumno", ascending=True)
            else:
                df_mostrar = df_mostrar.sort_values(by="N° Lista", ascending=True)

            st.dataframe(df_mostrar, use_container_width=True)

            st.markdown("#### ⚙️ Modificar Estatus de Alumno (Baja / Activar)")
            alumnos_dict = {}
            for _, r in alumnos_grupo.iterrows():
                alumnos_dict[
                    f"[{r['N° Lista']}] {r['Nombre del Alumno']} - Actual: {r['Estatus']}"
                ] = r["id"]

            al_cambio = st.selectbox(
                "Selecciona al alumno a modificar", list(alumnos_dict.keys())
            )
            id_al_sel = alumnos_dict[al_cambio]

            nuevo_estatus = st.radio(
                "Nuevo Estatus", ["Activo", "Baja"], horizontal=True
            )
            f_cambio = st.date_input(
                "Fecha del cambio (Alta/Baja)", datetime.today()
            ).strftime("%Y-%m-%d")

            if st.button("Actualizar Estatus del Alumno"):
                with st.spinner("Actualizando estatus..."):
                    if nuevo_estatus == "Baja":
                        cursor.execute(
                            "UPDATE alumnos SET estatus = ?, fecha_baja = ? WHERE id = ?",
                            (nuevo_estatus, f_cambio, id_al_sel),
                        )
                    else:
                        cursor.execute(
                            "UPDATE alumnos SET estatus = ?, fecha_baja = NULL, fecha_alta = ? WHERE id = ?",
                            (nuevo_estatus, f_cambio, id_al_sel),
                        )
                    conn.commit()
                    st.success("¡Estatus actualizado correctamente!")
                    st.rerun()
        else:
            st.info("No hay alumnos registrados en este grupo.")

# --- 3. PLANTILLAS DE OTROS DOCENTES ---
elif menu == "📂 Plantillas de Otros Docentes":
    st.subheader(
        "📂 Repositorio de Grupos y Plantillas de Otros Docentes (Solo Lectura / Exportación)"
    )
    st.write(
        "Aquí puedes consultar los grupos creados por otros profesores. Puedes revisarlos y clonarlos a tu cuenta si te sirven como base."
    )

    otros_grupos = pd.read_sql(
        "SELECT id, nombre, username FROM grupos WHERE username != ?",
        conn,
        params=(current_user,),
    )

    if not otros_grupos.empty:
        otros_grupos["etiqueta"] = (
            otros_grupos["nombre"] + " (Docente: " + otros_grupos["username"] + ")"
        )
        grupo_elegido = st.selectbox(
            "Selecciona un grupo para revisar su contenido",
            otros_grupos["etiqueta"],
        )

        id_grupo_sel = otros_grupos[
            otros_grupos["etiqueta"] == grupo_elegido
        ]["id"].values[0]
        nombre_original = otros_grupos[
            otros_grupos["etiqueta"] == grupo_elegido
        ]["nombre"].values[0]
        profe_original = otros_grupos[
            otros_grupos["etiqueta"] == grupo_elegido
        ]["username"].values[0]

        alumnos_externos = pd.read_sql(
            """
            SELECT numero_lista AS 'N° Lista', nombre AS 'Nombre del Alumno', sexo AS 'Género', turno AS 'Turno', estatus AS 'Estatus'
            FROM alumnos WHERE grupo_id = ? ORDER BY numero_lista ASC
        """,
            conn,
            params=(id_grupo_sel,),
        )

        st.markdown(
            f"**Revisando grupo:** `{nombre_original}` del docente `{profe_original}`"
        )
        st.dataframe(alumnos_externos, use_container_width=True)

        st.markdown("---")
        st.markdown(
            "### 🔄 Importar / Clonar este grupo a mi cuenta personal"
        )
        # MODIFICACIÓN DE HOY: Se quita el sufijo forzoso "(Copia)" para clonar con el nombre original limpio
        nuevo_nombre_clon = st.text_input(
            "Nombre que tendrá este grupo en tu cuenta:",
            value=nombre_original,
        )

        if st.button("📥 Clonar este grupo con sus alumnos a mis grupos"):
            with st.spinner("Clonando grupo y alumnos..."):
                try:
                    cursor.execute(
                        "INSERT INTO grupos (nombre, username) VALUES (?, ?)",
                        (nuevo_nombre_clon, current_user),
                    )
                    nuevo_grupo_id = cursor.lastrowid

                    hoy_str = datetime.today().strftime("%Y-%m-%d")
                    for _, row in alumnos_externos.iterrows():
                        cursor.execute(
                            "INSERT INTO alumnos (numero_lista, nombre, sexo, turno, estatus, fecha_alta, grupo_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                row["N° Lista"],
                                row["Nombre del Alumno"],
                                row["Género"],
                                row["Turno"],
                                row["Estatus"],
                                hoy_str,
                                nuevo_grupo_id,
                            ),
                        )
                    conn.commit()
                    st.success(
                        f"¡Grupo clonado con éxito como '{nuevo_nombre_clon}' con todos sus alumnos! Ya aparece en 'Mis Grupos y Alumnos'."
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(
                        "Ya tienes un grupo con ese nombre en tu cuenta. Elige otro nombre."
                    )
    else:
        st.info(
            "No hay grupos de otros docentes disponibles en este momento para consultar."
        )

# --- 4. ASISTENCIA (CON MATRIZ MANUAL Y ESCANEO CON GEMINI AI) ---
elif menu == "✅ Asistencia":
    st.subheader("Control de Asistencia y Escaneo Inteligente con IA")
    
    grupos_df = pd.read_sql(
        "SELECT * FROM grupos WHERE username = ?",
        conn,
        params=(current_user,),
    )

    if not grupos_df.empty:
        grupo_dict = dict(zip(grupos_df["nombre"], grupos_df["id"]))

        tab_manual, tab_ia = st.tabs(["📝 Matriz Manual Mensual", "📸 Escanear Lista Física con IA (Gemini)"])

        # --- PESTAÑA 1: MATRIZ MANUAL ---
        with tab_manual:
            st.write("Selecciona el grupo, año y mes. Los días inician vacíos para registrar únicamente lo necesario.")
            c_asis1, c_asis2, c_asis3 = st.columns(3)
            with c_asis1:
                g_asis = st.selectbox(
                    "Selecciona tu grupo", list(grupo_dict.keys()), key="asis_grupo"
                )
            with c_asis2:
                anio_sel = st.selectbox(
                    "Año", [2025, 2026, 2027, 2028], index=1, key="asis_anio"
                )
            with c_asis3:
                meses_dict = {
                    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4,
                    "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8,
                    "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
                }
                mes_nombre = st.selectbox(
                    "Mes", list(meses_dict.keys()), index=10, key="asis_mes"
                )
                mes_sel = meses_dict[mes_nombre]

            num_dias = calendar.monthrange(anio_sel, mes_sel)[1]

            alumnos_df = pd.read_sql(
                """
                SELECT id, numero_lista AS 'N° Lista', nombre AS 'Nombre del Alumno', sexo AS 'Género', estatus AS 'Estatus'
                FROM alumnos 
                WHERE grupo_id = ? AND estatus = 'Activo' 
                ORDER BY numero_lista ASC
            """,
                conn,
                params=(grupo_dict[g_asis],),
            )

            if not alumnos_df.empty:
                inicio_mes = f"{anio_sel}-{mes_sel:02d}-01"
                fin_mes = f"{anio_sel}-{mes_sel:02d}-{num_dias:02d}"

                asist_registradas = pd.read_sql(
                    """
                    SELECT a.id AS alumno_id, ast.fecha, ast.estado
                    FROM alumnos a
                    JOIN asistencia ast ON a.id = ast.alumno_id
                    WHERE a.grupo_id = ? AND ast.fecha BETWEEN ? AND ?
                """,
                    conn,
                    params=(grupo_dict[g_asis], inicio_mes, fin_mes),
                )

                asis_dict = {}
                if not asist_registradas.empty:
                    for _, r in asist_registradas.iterrows():
                        asis_dict[(r["alumno_id"], r["fecha"])] = r["estado"]

                matriz_df = alumnos_df.copy()

                for d in range(1, num_dias + 1):
                    fecha_str = f"{anio_sel}-{mes_sel:02d}-{d:02d}"
                    col_name = f"{d:02d}"
                    valores_col = []
                    for _, al in alumnos_df.iterrows():
                        key = (al["id"], fecha_str)
                        valores_col.append(asis_dict.get(key, ""))
                    matriz_df[col_name] = valores_col

                column_config = {
                    "id": None,
                    "N° Lista": st.column_config.NumberColumn("N°", disabled=True, width="small"),
                    "Nombre del Alumno": st.column_config.TextColumn("Nombre del Alumno", disabled=True, width="large"),
                    "Género": st.column_config.TextColumn("Género", disabled=True, width="small"),
                    "Estatus": st.column_config.TextColumn("Estatus", disabled=True, width="small"),
                }

                opciones_estado = ["", "Presente", "Falta", "Retardo", "Justificado"]
                for d in range(1, num_dias + 1):
                    col_name = f"{d:02d}"
                    column_config[col_name] = st.column_config.SelectboxColumn(
                        label=col_name,
                        options=opciones_estado,
                        required=False,
                        width="small",
                    )

                with st.form("form_matriz_asistencia"):
                    df_editado = st.data_editor(
                        matriz_df,
                        column_config=column_config,
                        hide_index=True,
                        use_container_width=True,
                        key="editor_asistencia_mes",
                    )

                    submitted_asis = st.form_submit_button("💾 Guardar Asistencia del Mes")
                    if submitted_asis:
                        with st.spinner("Guardando asistencia en la base de datos..."):
                            for _, row in df_editado.iterrows():
                                al_id = row["id"]
                                for d in range(1, num_dias + 1):
                                    fecha_str = f"{anio_sel}-{mes_sel:02d}-{d:02d}"
                                    col_name = f"{d:02d}"
                                    nuevo_estado = row[col_name]

                                    cursor.execute(
                                        "DELETE FROM asistencia WHERE alumno_id = ? AND fecha = ?",
                                        (al_id, fecha_str),
                                    )
                                    if nuevo_estado and str(nuevo_estado).strip() != "":
                                        cursor.execute(
                                            "INSERT INTO asistencia (alumno_id, fecha, estado) VALUES (?, ?, ?)",
                                            (al_id, fecha_str, nuevo_estado),
                                        )
                            conn.commit()
                            st.success("¡Asistencia mensual guardada con éxito!")
                            st.rerun()
            else:
                st.warning("Este grupo no tiene alumnos activos.")

        # --- PESTAÑA 2: ESCANEO CON GEMINI AI ---
        with tab_ia:
            st.markdown("### 🤖 Escanear Lista Física con Gemini AI")
            st.write("Sube una foto de tu lista física o libreta de asistencia. La Inteligencia Artificial leerá los datos y los registrará automáticamente.")

            if not GEMINI_AVAILABLE:
                st.error("⚠️ Las librerías de Gemini no están instaladas. Ejecute en su terminal: `pip install google-generativeai pillow`")
            else:
                gemini_api_key = st.text_input("🔑 Ingrese su Clave de API de Gemini", type="password").strip()
                
                g_ia = st.selectbox("Selecciona tu grupo destino", list(grupo_dict.keys()), key="grupo_ia")
                fecha_ia = st.date_input("Fecha a registrar en el sistema", value=date.today())

                foto_subida = st.file_uploader("Sube la foto de la lista física (PNG, JPG)", type=["png", "jpg", "jpeg"])

                if foto_subida is not None:
                    st.image(foto_subida, caption="Vista previa de la lista física", use_container_width=True)

                    if st.button("🚀 Analizar con Gemini AI y Extraer Asistencia"):
                        if not gemini_api_key:
                            st.warning("⚠️ Por favor ingrese su Clave de API de Gemini.")
                        else:
                            with st.spinner("🤖 Analizando imagen y cruzando con la lista de alumnos..."):
                                try:
                                    genai.configure(api_key=gemini_api_key)
                                    model = genai.GenerativeModel('gemini-1.5-flash')
                                    
                                    alumnos_grupo_ia = pd.read_sql(
                                        "SELECT id, numero_lista, nombre FROM alumnos WHERE grupo_id = ? AND estatus = 'Activo' ORDER BY numero_lista ASC",
                                        conn,
                                        params=(grupo_dict[g_ia],)
                                    )
                                    
                                    nombres_registrados = alumnos_grupo_ia['nombre'].tolist()
                                    
                                    img = Image.open(foto_subida)
                                    
                                    prompt = f"""
                                    Eres un asistente escolar experto. Analiza esta imagen de una lista de asistencia física.
                                    Los alumnos oficiales de este grupo son exactamente: {nombres_registrados}.
                                    Identifica el estado de asistencia de cada alumno visible en la foto.
                                    Los únicos estados válidos son: 'Presente', 'Falta', 'Retardo', 'Justificado'.
                                    Devuelve estrictamente un JSON válido con una lista de objetos que tengan exactamente las llaves: "nombre" y "estado".
                                    Ejemplo: [{{"nombre": "Pérez Gómez Juan", "estado": "Presente"}}]
                                    No agregues explicaciones ni formato markdown de código adicional, solo el texto JSON puro.
                                    """
                                    
                                    response = model.generate_content([prompt, img])
                                    texto_resp = response.text.strip()
                                    if texto_resp.startswith("```json"):
                                        texto_resp = texto_resp[7:]
                                    if texto_resp.endswith("```"):
                                        texto_resp = texto_resp[:-3]
                                    
                                    datos_ia = json.loads(texto_resp.strip())
                                    st.session_state['datos_ia_extraidos'] = datos_ia
                                    st.success("¡Imagen analizada con éxito por Gemini! Revisa los resultados abajo.")
                                except Exception as e:
                                    st.error(f"Error al procesar la imagen con Gemini: {e}")

                if 'datos_ia_extraidos' in st.session_state and st.session_state['datos_ia_extraidos']:
                    st.markdown("#### 📋 Resultados Extraídos por la IA (Verificación)")
                    df_ia_preview = pd.DataFrame(st.session_state['datos_ia_extraidos'])
                    st.dataframe(df_ia_preview, use_container_width=True)

                    if st.button("💾 Guardar Asistencia Extraída en la Base de Datos"):
                        with st.spinner("Guardando en la base de datos..."):
                            fecha_str_ia = fecha_ia.strftime("%Y-%m-%d")
                            alumnos_grupo_ia = pd.read_sql(
                                "SELECT id, nombre FROM alumnos WHERE grupo_id = ?",
                                conn,
                                params=(grupo_dict[g_ia],)
                            )
                            nombre_a_id = dict(zip(alumnos_grupo_ia['nombre'], alumnos_grupo_ia['id']))

                            contador_guardados = 0
                            for item in st.session_state['datos_ia_extraidos']:
                                nom = item.get('nombre')
                                est = item.get('estado')
                                if nom in nombre_a_id and est in ['Presente', 'Falta', 'Retardo', 'Justificado']:
                                    al_id = nombre_a_id[nom]
                                    cursor.execute(
                                        "DELETE FROM asistencia WHERE alumno_id = ? AND fecha = ?",
                                        (al_id, fecha_str_ia)
                                    )
                                    cursor.execute(
                                        "INSERT INTO asistencia (alumno_id, fecha, estado) VALUES (?, ?, ?)",
                                        (al_id, fecha_str_ia, est)
                                    )
                                    contador_guardados += 1
                            conn.commit()
                            st.success(f"¡Se han registrado {contador_guardados} asistencias correctamente con la IA!")
                            del st.session_state['datos_ia_extraidos']
                            st.rerun()
    else:
        st.info("Crea grupos y alumnos primero en tu sección.")

# --- 5. EVALUACIONES (CON CONFIGURACIÓN DE FECHAS, PONDERACIÓN Y ASISTENCIA) ---
elif menu == "📊 Evaluaciones":
    st.subheader(
        "📊 Sistema de Evaluaciones, Fechas, Ponderación y Asistencia"
    )
    st.write(
        "Configura las fechas del trimestre, los porcentajes de ponderación (incluyendo asistencia), crea actividades y evalúa."
    )

    grupos_df = pd.read_sql(
        "SELECT * FROM grupos WHERE username = ?",
        conn,
        params=(current_user,),
    )

    if not grupos_df.empty:
        grupo_dict = dict(zip(grupos_df["nombre"], grupos_df["id"]))

        c_eval1, c_eval2 = st.columns(2)
        with c_eval1:
            g_eval = st.selectbox(
                "Selecciona tu grupo", list(grupo_dict.keys()), key="g_eval"
            )
        with c_eval2:
            periodo_eval = st.selectbox(
                "Periodo / Trimestre",
                ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
                key="periodo_eval",
            )

        id_g_eval = grupo_dict[g_eval]

        tab_fechas_pond, tab_acts, tab_matriz, tab_rep = st.tabs(
            [
                "⚙️ 1. Fechas y Ponderación",
                "📝 2. Gestionar Actividades",
                "📊 3. Matriz de Calificaciones",
                "📈 4. Promedios y Reporte PDF",
            ]
        )

        with tab_fechas_pond:
            st.markdown(
                "### 🗓️ Configurar Fechas de Inicio y Fin del Periodo"
            )
            st.write(
                f"Establezca el rango de fechas en el que se aplicarán las actividades y se evaluará la asistencia de `{periodo_eval}`."
            )

            cursor.execute(
                "SELECT fecha_inicio, fecha_fin FROM config_fechas_periodos WHERE username = ? AND periodo = ?",
                (current_user, periodo_eval),
            )
            fechas_db = cursor.fetchone()
            
            hoy = date.today()
            def_ini = datetime.strptime(fechas_db[0], "%Y-%m-%d").date() if fechas_db else hoy
            def_fin = datetime.strptime(fechas_db[1], "%Y-%m-%d").date() if fechas_db else hoy

            with st.form("form_fechas_periodo"):
                cf1, cf2 = st.columns(2)
                with cf1:
                    f_inicio_trim = st.date_input(
                        "Fecha de Inicio del Periodo", value=def_ini
                    )
                with cf2:
                    f_fin_trim = st.date_input(
                        "Fecha de Fin del Periodo", value=def_fin
                    )

                if st.form_submit_button("Guardar Fechas del Trimestre"):
                    cursor.execute(
                        "DELETE FROM config_fechas_periodos WHERE username = ? AND periodo = ?",
                        (current_user, periodo_eval),
                    )
                    cursor.execute(
                        "INSERT INTO config_fechas_periodos (username, periodo, fecha_inicio, fecha_fin) VALUES (?, ?, ?, ?)",
                        (
                            current_user,
                            periodo_eval,
                            f_inicio_trim.strftime("%Y-%m-%d"),
                            f_fin_trim.strftime("%Y-%m-%d"),
                        ),
                    )
                    conn.commit()
                    st.success("¡Fechas del trimestre guardadas con éxito!")

            st.markdown("---")
            st.markdown("### ⚖️ Definir Ponderación Porcentual (Incluyendo Asistencia)")
            st.write(
                "La suma total de los porcentajes de Tareas, Actividades, Proyectos y Asistencia debe dar el 100%."
            )

            cursor.execute(
                "SELECT pct_tareas, pct_actividades, pct_proyectos, pct_asistencia FROM ponderaciones_cat WHERE grupo_id = ? AND periodo = ?",
                (id_g_eval, periodo_eval),
            )
            pond_actual = cursor.fetchone()
            if pond_actual:
                def_t, def_a, def_p, def_asist = pond_actual
            else:
                def_t, def_a, def_p, def_asist = 20.0, 20.0, 40.0, 20.0

            with st.form("form_ponderacion"):
                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                with col_p1:
                    pct_t = st.number_input(
                        "Tareas (%)", 0.0, 100.0, float(def_t), 1.0
                    )
                with col_p2:
                    pct_a = st.number_input(
                        "Actividades (%)", 0.0, 100.0, float(def_a), 1.0
                    )
                with col_p3:
                    pct_p = st.number_input(
                        "Proyectos (%)",
                        0.0,
                        100.0,
                        float(def_p),
                        1.0,
                    )
                with col_p4:
                    pct_asist = st.number_input(
                        "Asistencia (%)",
                        0.0,
                        100.0,
                        float(def_asist),
                        1.0,
                    )

                suma_pct = pct_t + pct_a + pct_p + pct_asist
                st.info(f"📌 **Suma total de ponderación:** {suma_pct:.1f}%")

                if st.form_submit_button("Guardar Ponderaciones"):
                    if abs(suma_pct - 100.0) > 0.01:
                        st.warning(
                            "⚠️ Advertencia: La suma de los porcentajes no es 100% (es"
                            f" {suma_pct:.1f}%). Aun así se guardará, pero se"
                            " recomienda que sume exactamente 100%."
                        )

                    cursor.execute(
                        "DELETE FROM ponderaciones_cat WHERE grupo_id = ? AND periodo = ?",
                        (id_g_eval, periodo_eval),
                    )
                    cursor.execute(
                        "INSERT INTO ponderaciones_cat (grupo_id, periodo, pct_tareas, pct_actividades, pct_proyectos, pct_asistencia) VALUES (?, ?, ?, ?, ?, ?)",
                        (id_g_eval, periodo_eval, pct_t, pct_a, pct_p, pct_asist),
                    )
                    conn.commit()
                    st.success("¡Ponderaciones guardadas con éxito!")

        with tab_acts:
            st.markdown("### 📝 Crear Actividades, Tareas y Proyectos con Fecha")
            st.write(
                f"Agrega las actividades para `{periodo_eval}` indicando su fecha de aplicación."
            )

            cursor.execute(
                "SELECT fecha_inicio, fecha_fin FROM config_fechas_periodos WHERE username = ? AND periodo = ?",
                (current_user, periodo_eval),
            )
            r_fechas = cursor.fetchone()
            if r_fechas:
                st.info(f"📅 Rango configurado para este periodo: **{r_fechas[0]}** al **{r_fechas[1]}**")
            else:
                st.warning("⚠️ No ha configurado las fechas de este periodo en la pestaña '1. Fechas y Ponderación'.")

            with st.form("form_crear_actividad"):
                c_act1, c_act2 = st.columns(2)
                with c_act1:
                    nombre_act = st.text_input(
                        "Nombre de la Actividad / Tarea / Proyecto"
                    ).strip()
                with c_act2:
                    tipo_act = st.selectbox(
                        "Categoría",
                        ["Tarea", "Actividad", "Proyecto-Experimento"],
                    )

                fecha_act = st.date_input(
                    "Fecha de la Actividad / Tarea", value=date.today()
                )

                btn_crear_act = st.form_submit_button("➕ Agregar Actividad")

                if btn_crear_act:
                    if nombre_act:
                        fecha_str = fecha_act.strftime("%Y-%m-%d")
                        
                        if r_fechas:
                            if fecha_str < r_fechas[0] or fecha_str > r_fechas[1]:
                                st.warning("⚠️ Nota: La fecha seleccionada está fuera del rango configurado para el trimestre, pero se registrará de igual forma.")

                        with st.spinner("Registrando actividad..."):
                            cursor.execute(
                                "INSERT INTO actividades_eval (grupo_id, periodo, nombre, tipo, fecha) VALUES (?, ?, ?, ?, ?)",
                                (
                                    id_g_eval,
                                    periodo_eval,
                                    nombre_act,
                                    tipo_act,
                                    fecha_str,
                                ),
                            )
                            conn.commit()
                            st.success(
                                f"¡Actividad '{nombre_act}' creada con éxito!"
                            )
                            st.rerun()
                    else:
                        st.warning("Escribe un nombre para la actividad.")

            st.markdown("---")
            st.markdown("#### Actividades Registradas en este Periodo")
            acts_df = pd.read_sql(
                """
                SELECT id, nombre AS 'Nombre de Actividad', tipo AS 'Categoría', fecha AS 'Fecha'
                FROM actividades_eval
                WHERE grupo_id = ? AND periodo = ?
                ORDER BY fecha ASC
            """,
                conn,
                params=(id_g_eval, periodo_eval),
            )

            if not acts_df.empty:
                st.dataframe(
                    acts_df.drop(columns=["id"]), use_container_width=True
                )

                act_dict = {
                    f"[{r['Fecha']}] [{r['Categoría']}] {r['Nombre de Actividad']}": r["id"]
                    for _, r in acts_df.iterrows()
                }
                act_a_borrar = st.selectbox(
                    "Selecciona una actividad para eliminar si te equivocaste",
                    list(act_dict.keys()),
                )
                if st.button("🗑️ Eliminar Actividad Seleccionada"):
                    with st.spinner("Eliminando actividad y sus notas..."):
                        id_act_del = act_dict[act_a_borrar]
                        cursor.execute(
                            "DELETE FROM calificaciones_det WHERE actividad_id = ?",
                            (id_act_del,),
                        )
                        cursor.execute(
                            "DELETE FROM actividades_eval WHERE id = ?",
                            (id_act_del,),
                        )
                        conn.commit()
                        st.success("Actividad eliminada correctamente.")
                        st.rerun()
            else:
                st.info(
                    "No hay actividades registradas aún. Crea al menos una arriba."
                )

        with tab_matriz:
            st.markdown("### 📊 Matriz de Captura de Calificaciones (0 a 10)")
            st.write(
                "Desliza hacia la derecha para ver todas las actividades creadas"
                " y captura las notas directamente."
            )

            alumnos_df = pd.read_sql(
                """
                SELECT id, numero_lista AS 'N° Lista', nombre AS 'Nombre del Alumno', sexo AS 'Género', estatus AS 'Estatus'
                FROM alumnos 
                WHERE grupo_id = ? AND estatus = 'Activo' 
                ORDER BY numero_lista ASC
            """,
                conn,
                params=(id_g_eval,),
            )

            acts_df = pd.read_sql(
                """
                SELECT id, nombre, tipo, fecha
                FROM actividades_eval
                WHERE grupo_id = ? AND periodo = ?
                ORDER BY fecha ASC
            """,
                conn,
                params=(id_g_eval, periodo_eval),
            )

            if not alumnos_df.empty and not acts_df.empty:
                califs_registradas = pd.read_sql(
                    """
                    SELECT alumno_id, actividad_id, calificacion
                    FROM calificaciones_det
                """,
                    conn,
                )

                calif_dict = {}
                if not califs_registradas.empty:
                    for _, r in califs_registradas.iterrows():
                        calif_dict[(r["alumno_id"], r["actividad_id"])] = r[
                            "calificacion"
                        ]

                matriz_calif_df = alumnos_df.copy()
                act_col_mapping = {}

                for _, act in acts_df.iterrows():
                    col_label = f"[{act['tipo'][:3].upper()}] {act['nombre']} ({act['fecha']})"
                    act_col_mapping[col_label] = act["id"]
                    valores_nota = []
                    for _, al in alumnos_df.iterrows():
                        key = (al["id"], act["id"])
                        valores_nota.append(
                            float(calif_dict.get(key, 6.0))
                        )
                    matriz_calif_df[col_label] = valores_nota

                column_config = {
                    "id": None,
                    "N° Lista": st.column_config.NumberColumn(
                        "N°", disabled=True, width="small"
                    ),
                    "Nombre del Alumno": st.column_config.TextColumn(
                        "Nombre del Alumno", disabled=True, width="large"
                    ),
                    "Género": st.column_config.TextColumn(
                        "Género", disabled=True, width="small"
                    ),
                    "Estatus": st.column_config.TextColumn(
                        "Estatus", disabled=True, width="small"
                    ),
                }

                for col_label in act_col_mapping.keys():
                    column_config[col_label] = (
                        st.column_config.NumberColumn(
                            col_label,
                            min_value=0.0,
                            max_value=10.0,
                            step=0.1,
                            format="%.1f",
                        )
                    )

                with st.form("form_matriz_calificaciones"):
                    df_calif_editado = st.data_editor(
                        matriz_calif_df,
                        column_config=column_config,
                        hide_index=True,
                        use_container_width=True,
                        key="editor_matriz_calificaciones",
                    )

                    sub_calif = st.form_submit_button(
                        "💾 Guardar Calificaciones de la Matriz"
                    )
                    if sub_calif:
                        with st.spinner(
                            "Guardando calificaciones en la base de datos..."
                        ):
                            for _, row in df_calif_editado.iterrows():
                                al_id = row["id"]
                                for col_label, act_id in act_col_mapping.items():
                                    nota_val = float(row[col_label])
                                    cursor.execute(
                                        "DELETE FROM calificaciones_det WHERE alumno_id = ? AND actividad_id = ?",
                                        (al_id, act_id),
                                    )
                                    cursor.execute(
                                        "INSERT INTO calificaciones_det (alumno_id, actividad_id, calificacion) VALUES (?, ?, ?)",
                                        (al_id, act_id, nota_val),
                                    )
                            conn.commit()
                            st.success(
                                "¡Calificaciones guardadas con éxito!"
                            )
                            st.rerun()
            else:
                if alumnos_df.empty:
                    st.warning("Este grupo no tiene alumnos activos.")
                if acts_df.empty:
                    st.info(
                        "Primero crea al menos una actividad en la pestaña '2."
                        " Gestionar Actividades'."
                    )

        with tab_rep:
            st.markdown(
                "### 📈 Promedios Ponderados (Actividades + Asistencia) y Reporte Oficial"
            )
            st.write(
                "El sistema calcula el promedio ponderado tomando en cuenta las notas de tareas, actividades, proyectos y el porcentaje de asistencia dentro del rango de fechas del trimestre."
            )

            cursor.execute(
                "SELECT pct_tareas, pct_actividades, pct_proyectos, pct_asistencia FROM ponderaciones_cat WHERE grupo_id = ? AND periodo = ?",
                (id_g_eval, periodo_eval),
            )
            pond_row = cursor.fetchone()
            p_t, p_a, p_p, p_asist = (
                (pond_row[0], pond_row[1], pond_row[2], pond_row[3])
                if pond_row
                else (20.0, 20.0, 40.0, 20.0)
            )

            cursor.execute(
                "SELECT fecha_inicio, fecha_fin FROM config_fechas_periodos WHERE username = ? AND periodo = ?",
                (current_user, periodo_eval),
            )
            f_row = cursor.fetchone()
            f_ini = f_row[0] if f_row else '2026-01-01'
            f_fin = f_row[1] if f_row else '2026-12-31'

            alumnos_df = pd.read_sql(
                """
                SELECT id, numero_lista AS 'N°', nombre AS 'Alumno'
                FROM alumnos 
                WHERE grupo_id = ? AND estatus = 'Activo' 
                ORDER BY numero_lista ASC
            """,
                conn,
                params=(id_g_eval,),
            )

            if not alumnos_df.empty:
                califs_df = pd.read_sql(
                    """
                    SELECT cd.alumno_id, cd.actividad_id, cd.calificacion, ae.tipo
                    FROM calificaciones_det cd
                    JOIN actividades_eval ae ON cd.actividad_id = ae.id
                    WHERE ae.grupo_id = ? AND ae.periodo = ?
                """,
                    conn,
                    params=(id_g_eval, periodo_eval),
                )

                asist_df = pd.read_sql(
                    """
                    SELECT ast.alumno_id, ast.estado
                    FROM asistencia ast
                    JOIN alumnos a ON ast.alumno_id = a.id
                    WHERE a.grupo_id = ? AND ast.fecha BETWEEN ? AND ?
                """,
                    conn,
                    params=(id_g_eval, f_ini, f_fin),
                )

                resultados = []
                for _, al in alumnos_df.iterrows():
                    al_id = al["id"]
                    
                    if not califs_df.empty and "tipo" in califs_df.columns:
                        sub_df = califs_df[califs_df["alumno_id"] == al_id]
                        t_vals = sub_df[sub_df["tipo"] == "Tarea"]["calificacion"] if "tipo" in sub_df.columns else pd.Series(dtype=float)
                        a_vals = sub_df[sub_df["tipo"] == "Actividad"]["calificacion"] if "tipo" in sub_df.columns else pd.Series(dtype=float)
                        p_vals = sub_df[sub_df["tipo"] == "Proyecto-Experimento"]["calificacion"] if "tipo" in sub_df.columns else pd.Series(dtype=float)
                    else:
                        t_vals = pd.Series(dtype=float)
                        a_vals = pd.Series(dtype=float)
                        p_vals = pd.Series(dtype=float)

                    prom_t = t_vals.mean() if not t_vals.empty else 0.0
                    prom_a = a_vals.mean() if not a_vals.empty else 0.0
                    prom_p = p_vals.mean() if not p_vals.empty else 0.0

                    al_asist = asist_df[asist_df["alumno_id"] == al_id] if not asist_df.empty else pd.DataFrame()
                    if not al_asist.empty:
                        puntos_map = {'Presente': 10.0, 'Justificado': 10.0, 'Retardo': 8.0, 'Falta': 0.0}
                        puntos_total = al_asist['estado'].map(puntos_map).sum()
                        prom_asist = puntos_total / len(al_asist)
                    else:
                        prom_asist = 10.0

                    suma_pesos = 0.0
                    nota_final = 0.0

                    if not t_vals.empty or p_t > 0:
                        nota_final += prom_t * (p_t / 100.0)
                        suma_pesos += p_t
                    if not a_vals.empty or p_a > 0:
                        nota_final += prom_a * (p_a / 100.0)
                        suma_pesos += p_a
                    if not p_vals.empty or p_p > 0:
                        nota_final += prom_p * (p_p / 100.0)
                        suma_pesos += p_p
                    if p_asist > 0:
                        nota_final += prom_asist * (p_asist / 100.0)
                        suma_pesos += p_asist

                    if suma_pesos > 0:
                        nota_final = nota_final * (100.0 / suma_pesos)
                    else:
                        nota_final = 0.0

                    resultados.append(
                        {
                            "N°": al["N°"],
                            "Alumno": al["Alumno"],
                            "Tareas": round(prom_t, 1),
                            "Actividades": round(prom_a, 1),
                            "Proyectos": round(prom_p, 1),
                            "Asistencia": round(prom_asist, 1),
                            "Calif. Final": round(nota_final, 1),
                        }
                    )

                resumen_final_df = pd.DataFrame(resultados)
                st.dataframe(resumen_final_df, use_container_width=True)

                promedio_general_grupo = resumen_final_df[
                    "Calif. Final"
                ].mean()
                st.info(
                    f"📌 **Promedio ponderado general del grupo:**"
                    f" {promedio_general_grupo:.2f} | 📅 Rango de asistencias evaluado: {f_ini} al {f_fin}"
                )

                st.markdown("---")
                if st.button("📄 Generar Reporte Oficial en PDF"):
                    with st.spinner("Generando PDF de evaluaciones..."):
                        pdf = PDF()
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 10)
                        pdf.cell(
                            0,
                            8,
                            f"Reporte de Evaluaciones Ponderadas - Grupo: {g_eval}"
                            f" ({periodo_eval})",
                            0,
                            1,
                            "L",
                        )
                        pdf.ln(5)
                        pdf.set_fill_color(200, 220, 255)
                        pdf.cell(10, 8, "N°", 1, 0, "C", True)
                        pdf.cell(75, 8, "Alumno", 1, 0, "L", True)
                        pdf.cell(20, 8, "Tare.", 1, 0, "C", True)
                        pdf.cell(20, 8, "Activ.", 1, 0, "C", True)
                        pdf.cell(20, 8, "Asist.", 1, 0, "C", True)
                        pdf.cell(35, 8, "Final", 1, 1, "C", True)

                        pdf.set_font("helvetica", "", 9)
                        for _, row in resumen_final_df.iterrows():
                            pdf.cell(10, 8, str(row["N°"]), 1, 0, "C")
                            pdf.cell(75, 8, str(row["Alumno"]), 1, 0, "L")
                            pdf.cell(
                                20, 8, str(row["Tareas"]), 1, 0, "C"
                            )
                            pdf.cell(
                                20,
                                8,
                                str(row["Actividades"]),
                                1,
                                0,
                                "C",
                            )
                            pdf.cell(
                                20,
                                8,
                                str(row["Asistencia"]),
                                1,
                                0,
                                "C",
                            )
                            pdf.cell(
                                35,
                                8,
                                str(row["Calif. Final"]),
                                1,
                                1,
                                "C",
                            )

                        pdf_bytes = pdf.output(dest="S").encode("latin1")
                    st.download_button(
                        label="⬇️ Descargar Reporte en PDF",
                        data=pdf_bytes,
                        file_name=f"Evaluaciones_{g_eval}_{periodo_eval}.pdf",
                        mime="application/pdf",
                    )
            else:
                st.info("Crea alumnos en el grupo primero.")
    else:
        st.info("Crea grupos y alumnos primero.")

# --- 6. BITÁCORA ---
elif menu == "📝 Bitácora":
    st.subheader("Registro de Incidencias y Observaciones")
    grupos_df = pd.read_sql(
        "SELECT * FROM grupos WHERE username = ?",
        conn,
        params=(current_user,),
    )

    if not grupos_df.empty:
        grupo_dict = dict(zip(grupos_df["nombre"], grupos_df["id"]))
        g_bit = st.selectbox(
            "Selecciona tu grupo", list(grupo_dict.keys()), key="g_bit"
        )

        alumnos_df = pd.read_sql(
            "SELECT id, numero_lista, nombre FROM alumnos WHERE grupo_id = ? ORDER BY numero_lista ASC",
            conn,
            params=(grupo_dict[g_bit],),
        )

        if not alumnos_df.empty:
            alumnos_dict = {
                f"[{r['numero_lista']}] {r['nombre']}": r["id"]
                for _, r in alumnos_df.iterrows()
            }
            al_sel = st.selectbox(
                "Seleccionar alumno", list(alumnos_dict.keys())
            )
            fecha_bit = datetime.today().strftime("%Y-%m-%d")
            incidencia = st.text_area(
                "Descripción de la incidencia u observación"
            )

            if st.button("Guardar en Bitácora"):
                if incidencia.strip():
                    with st.spinner("Guardando en bitácora..."):
                        cursor.execute(
                            "INSERT INTO bitacora (alumno_id, fecha, incidencia) VALUES (?, ?, ?)",
                            (alumnos_dict[al_sel], fecha_bit, incidencia),
                        )
                        conn.commit()
                        st.success("Incidencia registrada correctamente.")
                else:
                    st.warning("Escribe una descripción.")

            st.markdown("---")
            st.markdown("### Historial del Alumno")
            historial_df = pd.read_sql(
                f"""
                SELECT fecha AS Fecha, incidencia AS Incidencia 
                FROM bitacora 
                WHERE alumno_id = {alumnos_dict[al_sel]}
                ORDER BY fecha DESC
            """,
                conn,
            )
            if not historial_df.empty:
                st.dataframe(historial_df, use_container_width=True)
            else:
                st.info("Sin registros en la bitácora para este alumno.")
        else:
            st.warning("Este grupo no tiene alumnos.")
    else:
        st.info("Crea grupos y alumnos primero.")

# --- 7. REPORTES Y PDFS ---
elif menu == "📄 Reportes y PDFs":
    st.subheader("Generación y Exportación de Reportes en PDF")
    tipo_reporte = st.selectbox(
        "Selecciona el tipo de reporte",
        [
            "Calificaciones por Grupo",
            "Asistencia por Grupo y Fecha",
            "Bitácora de Incidencias por Alumno",
        ],
    )
    grupos_df = pd.read_sql(
        "SELECT * FROM grupos WHERE username = ?",
        conn,
        params=(current_user,),
    )

    if not grupos_df.empty:
        grupo_dict = dict(zip(grupos_df["nombre"], grupos_df["id"]))

        if tipo_reporte == "Calificaciones por Grupo":
            g_rep = st.selectbox("Grupo", list(grupo_dict.keys()), key="rep_g1")
            p_rep = st.selectbox(
                "Periodo",
                ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
                key="rep_p1",
            )
            df_rep = pd.read_sql(
                f"""
                SELECT a.numero_lista AS 'N°', a.nombre AS Alumno, c.calificacion AS Calificación
                FROM alumnos a
                JOIN calificaciones c ON a.id = c.alumno_id
                WHERE a.grupo_id = {grupo_dict[g_rep]} AND c.periodo = '{p_rep}' AND a.estatus = 'Activo'
                ORDER BY a.numero_lista ASC
            """,
                conn,
            )
            st.dataframe(df_rep, use_container_width=True)

            if not df_rep.empty:
                if st.button("📄 Generar PDF de Calificaciones"):
                    with st.spinner("Generando documento PDF..."):
                        pdf = PDF()
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 10)
                        pdf.cell(
                            0,
                            8,
                            f"Reporte de Calificaciones - Grupo: {g_rep} ({p_rep})",
                            0,
                            1,
                            "L",
                        )
                        pdf.ln(5)
                        pdf.set_fill_color(200, 220, 255)
                        pdf.cell(15, 8, "N°", 1, 0, "C", True)
                        pdf.cell(125, 8, "Alumno", 1, 0, "L", True)
                        pdf.cell(40, 8, "Calificación", 1, 1, "C", True)

                        pdf.set_font("helvetica", "", 10)
                        for _, row in df_rep.iterrows():
                            pdf.cell(15, 8, str(row["N°"]), 1, 0, "C")
                            pdf.cell(125, 8, str(row["Alumno"]), 1, 0, "L")
                            pdf.cell(40, 8, str(row["Calificación"]), 1, 1, "C")

                        pdf_bytes = pdf.output(dest="S").encode("latin1")
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Calificaciones_{g_rep}_{p_rep}.pdf",
                        mime="application/pdf",
                    )
            else:
                st.info("No hay datos para generar este PDF.")

        elif tipo_reporte == "Asistencia por Grupo y Fecha":
            g_rep = st.selectbox("Grupo", list(grupo_dict.keys()), key="rep_g2")
            f_rep = st.date_input(
                "Fecha del reporte", datetime.today()
            ).strftime("%Y-%m-%d")
            df_rep = pd.read_sql(
                f"""
                SELECT a.numero_lista AS 'N°', a.nombre AS Alumno, ast.estado AS Estado
                FROM alumnos a
                JOIN asistencia ast ON a.id = ast.alumno_id
                WHERE a.grupo_id = {grupo_dict[g_rep]} AND ast.fecha = '{f_rep}' AND a.estatus = 'Activo'
                ORDER BY a.numero_lista ASC
            """,
                conn,
            )
            st.dataframe(df_rep, use_container_width=True)

            if not df_rep.empty:
                if st.button("📄 Generar PDF de Asistencia"):
                    with st.spinner("Generando reporte de asistencia en PDF..."):
                        pdf = PDF()
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 10)
                        pdf.cell(
                            0,
                            8,
                            f"Reporte de Asistencia - Grupo: {g_rep} | Fecha: {f_rep}",
                            0,
                            1,
                            "L",
                        )
                        pdf.ln(5)
                        pdf.set_fill_color(200, 220, 255)
                        pdf.cell(15, 8, "N°", 1, 0, "C", True)
                        pdf.cell(125, 8, "Alumno", 1, 0, "L", True)
                        pdf.cell(40, 8, "Estado", 1, 1, "C", True)

                        pdf.set_font("helvetica", "", 10)
                        for _, row in df_rep.iterrows():
                            pdf.cell(15, 8, str(row["N°"]), 1, 0, "C")
                            pdf.cell(125, 8, str(row["Alumno"]), 1, 0, "L")
                            pdf.cell(40, 8, str(row["Estado"]), 1, 1, "C")

                        pdf_bytes = pdf.output(dest="S").encode("latin1")
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"Asistencia_{g_rep}_{f_rep}.pdf",
                        mime="application/pdf",
                    )
            else:
                st.info("No hay registros de asistencia para esta fecha.")

        elif tipo_reporte == "Bitácora de Incidencias por Alumno":
            g_rep = st.selectbox("Grupo", list(grupo_dict.keys()), key="rep_g3")
            alumnos_df = pd.read_sql(
                "SELECT id, numero_lista, nombre FROM alumnos WHERE grupo_id = ? ORDER BY numero_lista ASC",
                conn,
                params=(grupo_dict[g_rep],),
            )
            if not alumnos_df.empty:
                al_dict = {
                    f"[{r['numero_lista']}] {r['nombre']}": r["id"]
                    for _, r in alumnos_df.iterrows()
                }
                al_sel = st.selectbox("Alumno", list(al_dict.keys()))
                df_rep = pd.read_sql(
                    f"""
                    SELECT fecha AS Fecha, incidencia AS Incidencia
                    FROM bitacora
                    WHERE alumno_id = {al_dict[al_sel]}
                    ORDER BY fecha DESC
                """,
                    conn,
                )
                st.dataframe(df_rep, use_container_width=True)

                if not df_rep.empty:
                    if st.button("📄 Generar PDF de Bitácora"):
                        with st.spinner("Generando PDF de bitácora..."):
                            pdf = PDF()
                            pdf.add_page()
                            pdf.set_font("helvetica", "B", 10)
                            pdf.cell(
                                0,
                                8,
                                f"Bitácora de Incidencias - Alumno: {al_sel}",
                                0,
                                1,
                                "L",
                            )
                            pdf.ln(5)
                            pdf.set_fill_color(200, 220, 255)
                            pdf.cell(40, 8, "Fecha", 1, 0, "C", True)
                            pdf.cell(
                                140, 8, "Incidencia / Observación", 1, 1, "L", True
                            )

                            pdf.set_font("helvetica", "", 9)
                            for _, row in df_rep.iterrows():
                                pdf.cell(40, 8, str(row["Fecha"]), 1, 0, "C")
                                pdf.cell(140, 8, str(row["Incidencia"]), 1, 1, "L")

                            pdf_bytes = pdf.output(dest="S").encode("latin1")
                        st.download_button(
                            label="⬇️ Descargar PDF",
                            data=pdf_bytes,
                            file_name=f"Bitacora_{al_sel}.pdf",
                            mime="application/pdf",
                        )
                else:
                    st.info("Este alumno no tiene incidencias.")
            else:
                st.warning("Este grupo no tiene alumnos.")
    else:
        st.info("Crea tus grupos primero.")

# --- 8. GESTIÓN DE USUARIOS (SOLO ADMINISTRADOR) ---
elif (
    menu == "🔑 Gestión de Usuarios"
    and st.session_state.role == "Administrador"
):
    st.subheader("Panel de Administración de Usuarios")
    st.write(
        "Aquí puedes dar de alta nuevos profesores o colaboradores y asignarles sus contraseñas."
    )

    with st.form("nuevo_usuario_form"):
        nuevo_user = st.text_input("Nuevo Nombre de Usuario").strip()
        nuevo_pass = st.text_input("Contraseña", type="password").strip()
        nuevo_rol = st.selectbox("Rol del Usuario", ["Docente", "Administrador"])
        btn_crear_user = st.form_submit_button("Crear Nuevo Usuario")

        if btn_crear_user:
            if nuevo_user and nuevo_pass:
                with st.spinner("Registrando nuevo usuario..."):
                    try:
                        cursor.execute(
                            "INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)",
                            (nuevo_user, nuevo_pass, nuevo_rol),
                        )
                        conn.commit()
                        st.success(
                            f"¡Usuario '{nuevo_user}' creado exitosamente!"
                        )
                    except sqlite3.IntegrityError:
                        st.error("El nombre de usuario ya existe.")
            else:
                st.warning("Completa todos los campos.")

    st.markdown("---")
    st.markdown("### Usuarios Registrados en el Sistema")
    usuarios_df = pd.read_sql(
        "SELECT username AS 'Usuario', rol AS 'Rol' FROM usuarios", conn
    )
    st.dataframe(usuarios_df, use_container_width=True)
