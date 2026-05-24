from flask import Flask, render_template, request, redirect, url_for, flash
import pyodbc
import hashlib
import hashlib
import os
from flask import session 

app = Flask(__name__)
app.secret_key = "clave_super_secreta_grupo4"

# ---------------------------------------------------
# CONEXIÓN SQL SERVER
# ---------------------------------------------------
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=MSI;"
    "DATABASE=RetailBI;"
    "Trusted_Connection=yes;"
)

# ---------------------------------------------------
# FUNCIÓN CONEXIÓN
# ---------------------------------------------------
def conectar_db():
    return pyodbc.connect(CONN_STR)


# ---------------------------------------------------
# Auditoria de seccion
# ---------------------------------------------------
def registrar_sesion(usuario_id, nombre_usuario, evento):

    conn = conectar_db()
    cursor = conn.cursor()

    ip = request.remote_addr

    cursor.execute("""
        INSERT INTO sec.AuditoriaSesion
        (
            UsuarioID,
            NombreUsuario,
            Evento,
            DireccionIP
        )
        VALUES (?, ?, ?, ?)
    """, (
        usuario_id,
        nombre_usuario,
        evento,
        ip
    ))

    conn.commit()
    conn.close()

# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------
@app.route('/')
def index(): 
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():

    username = request.form['username']
    password = request.form['password']

    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT UsuarioID, PasswordHash, Salt
        FROM sec.Usuario
        WHERE NombreUsuario = ?
    """, (username,))

    usuario = cursor.fetchone()

    conn.close()

    if usuario:

        usuario_id = usuario[0]
        password_hash_db = usuario[1]
        salt_db = usuario[2]

        # Generar hash
        password_hash_input = hashlib.sha256(
            salt_db + password.encode("utf-8")
        ).digest()

        # LOGIN CORRECTO
        if password_hash_input == password_hash_db:

            session["usuario"] = username
            session["usuario_id"] = usuario_id

            # AUDITORÍA
            registrar_sesion(
                usuario_id,
                username,
                "LOGIN_OK"
            )

            return redirect(url_for('dashboard'))

    # LOGIN FALLIDO
    registrar_sesion(
        None,
        username,
        "LOGIN_FAIL"
    )

    flash("Usuario o contraseña incorrectos")

    return redirect(url_for('index'))

# ---------------------------------------------------
# DASHBOARD
# ---------------------------------------------------
@app.route("/dashboard")
def dashboard():

    conn = conectar_db()
    cursor = conn.cursor()
    usuario_actual = session.get("usuario")

    # =========================
    # TARJETAS SUPERIORES
    # =========================

    # Total cargas
    cursor.execute("""
        SELECT COUNT(*) 
        FROM sec.HistorialCarga
    """)
    total_cargas = cursor.fetchone()[0]

    # Cargas exitosas
    cursor.execute("""
        SELECT COUNT(*) 
        FROM sec.HistorialCarga
        WHERE Estado = 'COMPLETA'
    """)
    cargas_exitosas = cursor.fetchone()[0]

    # Cargas fallidas
    cursor.execute("""
        SELECT COUNT(*) 
        FROM sec.HistorialCarga
        WHERE Estado = 'FALLIDA'
    """)
    cargas_fallidas = cursor.fetchone()[0]

    # En proceso
    cursor.execute("""
        SELECT COUNT(*) 
        FROM sec.HistorialCarga
        WHERE Estado = 'EN_PROCESO'
    """)
    cargas_proceso = cursor.fetchone()[0]

    # Total registros procesados
    cursor.execute("""
        SELECT ISNULL(SUM(RegistrosLeidos),0)
        FROM sec.HistorialCarga
    """)
    registros_totales = cursor.fetchone()[0]

    # =========================
    # ÚLTIMAS 5 CARGAS
    # =========================

    cursor.execute("""
        SELECT TOP 5
            hc.CargaID,
            u.NombreUsuario,
            hc.NombreArchivo,
            hc.RegistrosLeidos,
            hc.Estado,
            hc.FechaInicio
        FROM sec.HistorialCarga hc
        INNER JOIN sec.Usuario u
            ON hc.UsuarioID = u.UsuarioID
        ORDER BY hc.FechaInicio DESC
    """)

    ultimas_cargas = cursor.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",

        total_cargas=total_cargas,
        cargas_exitosas=cargas_exitosas,
        cargas_fallidas=cargas_fallidas,
        cargas_proceso=cargas_proceso,
        registros_totales=registros_totales,

        ultimas_cargas=ultimas_cargas,
         usuario_actual=usuario_actual
    )

@app.route('/historial')
def historial():

    if 'usuario' not in session:
        return redirect(url_for('login'))

    conexion = conectar_db()
    cursor = conexion.cursor()

    # =========================
    # PAGINACIÓN
    # =========================
    pagina = request.args.get('pagina', 1, type=int)

    registros_por_pagina = 10

    offset = (pagina - 1) * registros_por_pagina

    # =========================
    # FILTROS
    # =========================
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    usuario = request.args.get('usuario', '')
    estado = request.args.get('estado', '')
    archivo = request.args.get('archivo', '')

    where = []
    parametros = []

    if fecha_inicio:
        where.append("CAST(c.FechaInicio AS DATE) >= ?")
        parametros.append(fecha_inicio)

    if fecha_fin:
        where.append("CAST(c.FechaInicio AS DATE) <= ?")
        parametros.append(fecha_fin)

    if usuario:
        where.append("c.UsuarioID = ?")
        parametros.append(usuario)

    if estado:
        where.append("c.Estado = ?")
        parametros.append(estado)

    if archivo:
        where.append("c.NombreArchivo LIKE ?")
        parametros.append(f"%{archivo}%")

    where_sql = ""

    if where:
        where_sql = "WHERE " + " AND ".join(where)

    # =========================
    # TOTAL REGISTROS
    # =========================
    consulta_total = f"""
        SELECT COUNT(*)
        FROM sec.HistorialCarga c
        {where_sql}
    """

    cursor.execute(consulta_total, parametros)

    total_registros = cursor.fetchone()[0]

    total_paginas = (
        total_registros + registros_por_pagina - 1
    ) // registros_por_pagina

    # =========================
    # CONSULTA PRINCIPAL
    # =========================
    consulta = f"""
        SELECT
            c.CargaID,
            c.FechaInicio,
            u.NombreUsuario,
            c.NombreArchivo,
            c.RegistrosLeidos,
            c.RegistrosOK,
            c.RegistrosError,
            c.DuracionSeg,
            c.Estado
        FROM sec.HistorialCarga c

        INNER JOIN sec.Usuario u
            ON c.UsuarioID = u.UsuarioID

        {where_sql}

        ORDER BY c.FechaInicio DESC

        OFFSET ? ROWS
        FETCH NEXT ? ROWS ONLY
    """

    parametros_paginacion = parametros + [
        offset,
        registros_por_pagina
    ]

    cursor.execute(consulta, parametros_paginacion)

    columnas = [col[0] for col in cursor.description]

    historial = [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]

    # =========================
    # USUARIOS
    # =========================
    cursor.execute("""
        SELECT UsuarioID, NombreUsuario
        FROM sec.Usuario
        ORDER BY NombreUsuario
    """)

    columnas_usuario = [col[0] for col in cursor.description]

    usuarios = [
        dict(zip(columnas_usuario, fila))
        for fila in cursor.fetchall()
    ]

    conexion.close()

    return render_template(
        'historial_de_cargas.html',

        historial=historial,
        usuarios=usuarios,

        pagina=pagina,
        total_paginas=total_paginas,
        total_registros=total_registros,

        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        usuario=usuario,
        estado=estado,
        archivo=archivo,
        registros_por_pagina=registros_por_pagina,

        usuario_actual=session['usuario']
    )

# ---------------------------------------------------
# CARGAR ARCHIVO
# ---------------------------------------------------
@app.route('/cargar')
def cargar():
    usuario_actual = session.get("usuario")
    return render_template('cargar_archivo.html')
    
@app.route('/errores')
def errores():

    usuario_actual = session.get("usuario")

    conn = conectar_db()
    cursor = conn.cursor()

    # ==========================================
    # OBTENER TODOS LOS ARCHIVOS/CARGAS
    # ==========================================
    cursor.execute("""
        SELECT
            CargaID,
            NombreArchivo
        FROM sec.HistorialCarga
        ORDER BY FechaInicio DESC
    """)

    archivos = cursor.fetchall()

    # ==========================================
    # PARÁMETROS
    # ==========================================
    carga_id = request.args.get("carga_id", type=int)
    tipo_error = request.args.get("tipo_error")

    # PAGINACIÓN
    pagina = request.args.get("pagina", 1, type=int)

    por_pagina = 50
    offset = (pagina - 1) * por_pagina

    # VARIABLES
    errores_lista = []
    info_carga = None
    total_errores = 0
    total_paginas = 1

    # ==========================================
    # SI SELECCIONÓ UNA CARGA
    # ==========================================
    if carga_id is not None:

        # ==========================================
        # INFORMACIÓN DE LA CARGA
        # ==========================================
        cursor.execute("""
            SELECT
                h.CargaID,
                h.NombreArchivo,
                h.FechaInicio,
                u.NombreUsuario
            FROM sec.HistorialCarga h
            INNER JOIN sec.Usuario u
                ON h.UsuarioID = u.UsuarioID
            WHERE h.CargaID = ?
        """, (carga_id,))

        info_carga = cursor.fetchone()

        # ==========================================
        # FILTROS SQL
        # ==========================================
        where_query = "WHERE CargaID = ?"
        parametros = [carga_id]

        if tipo_error:

            where_query += " AND TipoError = ?"
            parametros.append(tipo_error)

        # ==========================================
        # TOTAL ERRORES
        # ==========================================
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM sec.AuditoriaError
            {where_query}
        """, parametros)

        total_errores = cursor.fetchone()[0]

        # ==========================================
        # TOTAL PÁGINAS
        # ==========================================
        total_paginas = (
            total_errores + por_pagina - 1
        ) // por_pagina

        # ==========================================
        # CONSULTAR ERRORES PAGINADOS
        # ==========================================
        cursor.execute(f"""
            SELECT
                NumeroLinea,
                TipoError,
                Campo,
                ValorOriginal,
                Descripcion
            FROM sec.AuditoriaError
            {where_query}
            ORDER BY ErrorID
            OFFSET {offset} ROWS
            FETCH NEXT {por_pagina} ROWS ONLY
        """, parametros)

        errores_lista = cursor.fetchall()

    conn.close()

    return render_template(
        "detalle_de_errores.html",
        usuario_actual=usuario_actual,
        archivos=archivos,
        errores_lista=errores_lista,
        info_carga=info_carga,
        total_errores=total_errores,
        total_paginas=total_paginas,
        pagina=pagina,
        carga_id=carga_id
    )
# ---------------------------------------------------
# LOGOUT
# ---------------------------------------------------
@app.route("/logout")
def logout():

    usuario = session.get("usuario")
    usuario_id = session.get("usuario_id")

    # Registrar logout
    if usuario:

        registrar_sesion(
            usuario_id,
            usuario,
            "LOGOUT"
        )

    # Limpiar sesión
    session.clear()

    return redirect(url_for("index"))

@app.route("/usuario")
def usuario():

    conexion = conectar_db()
    cursor = conexion.cursor()

    # FILTROS
    busqueda = request.args.get("buscar", "")
    rol = request.args.get("rol", "")

    consulta = """
        SELECT
            U.UsuarioID,
            U.NombreUsuario,
            U.NombreCompleto,
            U.Email,
            U.Rol,
            U.Activo,
            U.FechaCreacion,

            (
                SELECT TOP 1 A.Fecha
                FROM sec.AuditoriaSesion A
                WHERE A.UsuarioID = U.UsuarioID
                AND A.Evento = 'LOGIN_OK'
                ORDER BY A.Fecha DESC
            ) AS UltimoLogin

        FROM sec.Usuario U

        WHERE 1=1
    """

    parametros = []

    # BUSQUEDA
    if busqueda:

        consulta += """
            AND (
                U.NombreCompleto LIKE ?
                OR U.NombreUsuario LIKE ?
            )
        """

        parametros.extend([
            f"%{busqueda}%",
            f"%{busqueda}%"
        ])

    # FILTRO ROL
    if rol and rol != "Todos":

        consulta += " AND U.Rol = ? "
        parametros.append(rol)

    consulta += " ORDER BY U.UsuarioID DESC "

    cursor.execute(consulta, parametros)

    columnas = [col[0] for col in cursor.description]

    usuarios = [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]

    conexion.close()

    return render_template(
        "gestion_de_usuarios.html",
        usuarios=usuarios,
        busqueda=busqueda,
        rol_actual=rol
    )

@app.route("/crear_usuario", methods=["POST"])
def crear_usuario():

    conexion = conectar_db()
    cursor = conexion.cursor()

    nombre_completo = request.form["nombre_completo"]
    usuario = request.form["usuario"]
    email = request.form["email"]
    rol = request.form["rol"]

    password = request.form["password"]
    confirmar = request.form["confirmar_password"]

    activo = 1 if request.form.get("activo") else 0

    # VALIDAR PASSWORD
    if password != confirmar:

        flash("Las contraseñas no coinciden", "error")
        return redirect("/usuario")

    # VALIDAR USUARIO EXISTENTE
    cursor.execute("""
        SELECT UsuarioID
        FROM sec.Usuario
        WHERE NombreUsuario = ?
    """, (usuario,))

    existe = cursor.fetchone()

    if existe:

        flash("El usuario ya existe", "error")
        return redirect("/usuario")

    # GENERAR SALT
    salt = os.urandom(32)

    # HASH SHA256
    password_hash = hashlib.sha256(
        salt + password.encode("utf-8")
    ).digest()

    # INSERTAR USUARIO
    cursor.execute("""
        INSERT INTO sec.Usuario (
            NombreUsuario,
            PasswordHash,
            Salt,
            NombreCompleto,
            Rol,
            Activo,
            Email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        usuario,
        password_hash,
        salt,
        nombre_completo,
        rol,
        activo,
        email
    ))

    conexion.commit()
    conexion.close()

    flash("Usuario creado correctamente", "success")

    return redirect("/usuario")

@app.route("/editar_usuario/<int:id>", methods=["POST"])
def editar_usuario(id):


    conexion = conectar_db()
    cursor = conexion.cursor()

    nombre = request.form["nombre_completo"]
    usuario = request.form["usuario"]
    email = request.form["email"]
    rol = request.form["rol"]

    activo = 1 if request.form.get("activo") else 0

    cursor.execute("""
        UPDATE sec.Usuario
        SET
            NombreCompleto = ?,
            NombreUsuario = ?,
            Email = ?,
            Rol = ?,
            Activo = ?
        WHERE UsuarioID = ?
    """, (
        nombre,
        usuario,
        email,
        rol,
        activo,
        id
    ))

    conexion.commit()
    conexion.close()

    return redirect("/usuario")

@app.route("/eliminar_usuario/<int:id>")
def eliminar_usuario(id):

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        DELETE FROM sec.Usuario
        WHERE UsuarioID = ?
    """, (id,))

    conexion.commit()
    conexion.close()

    return redirect("/usuario")
# ---------------------------------------------------
# EJECUTAR
# ---------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)