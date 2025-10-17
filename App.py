from flask import Flask, render_template, request, url_for, redirect, flash, session, jsonify
from flask_mysqldb import MySQL
import pyotp
import qrcode
import os
from datetime import datetime

app = Flask(__name__)

# Configuración de la base de datos
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'quirofanohuc'
mysql = MySQL(app)
app.secret_key = 'mysecretkey'

# ------------------- LOGIN Y 2FA -------------------

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    nombre_usuario = request.form.get('gmail')
    contraseña = request.form.get('contraseña')
    cur = mysql.connection.cursor()
    cur.execute("SELECT contraseña, rol FROM usuarios WHERE nombre_usuario = %s", (nombre_usuario,))
    resultado = cur.fetchone()
    if resultado and resultado[0] == contraseña:
        # Usuario y contraseña correctos, guardar en sesión temporal
        session['gmail'] = nombre_usuario
        session['rol'] = resultado[1]  # <--- GUARDA EL ROL EN LA SESIÓN
        return render_template('login.html', gmail=nombre_usuario)
    else:
        flash('Usuario o contraseña incorrectos')
        return redirect(url_for('index'))

@app.route('/verificar_2fa', methods=['POST'])
def verificar_2fa():
    nombre_usuario = request.form.get('gmail')
    codigo = request.form.get('codigo')
    cur = mysql.connection.cursor()
    cur.execute("SELECT `2AF` FROM usuarios WHERE nombre_usuario = %s", (nombre_usuario,))
    resultado = cur.fetchone()
    if resultado:
        secreto = resultado[0]
        totp = pyotp.TOTP(secreto)
        # Agregar ventana de validación para códigos cercanos
        if totp.verify(codigo, valid_window=1):
            session['usuario_autenticado'] = nombre_usuario
            flash('Bienvenido, autenticación exitosa')
            return redirect(url_for('dashboard'))
        else:
            flash('Código 2FA incorrecto o expirado')
            return render_template('login.html', gmail=nombre_usuario)
    else:
        flash('Usuario no encontrado')
        return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'usuario_autenticado' in session:
        actualizar_quirofanos_mantenimiento()
        cur = mysql.connection.cursor()
        # Salas para el SVG
        cur.execute("""
            SELECT s.*, 
                   e.nombre_equipo, 
                   p.nombre_completo
            FROM salas_quirofano s
            LEFT JOIN equipos_medicos e ON s.equipo_id = e.id
            LEFT JOIN pacientes p ON s.paciente_id = p.id
        """)
        salas = cur.fetchall()
        # Pacientes pendientes (en quirófano, hora actual < hora_fin, estado pendiente)
        cur.execute("""
            SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin, s.id as sala_id
            FROM pacientes p
            JOIN salas_quirofano s ON p.id = s.paciente_id
            WHERE p.estado_atencion = 'pendiente'
        """)
        pacientes_pendientes = cur.fetchall()
        # Pacientes atendidos (hora actual >= hora_fin, estado pendiente)
        cur.execute("""
            SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin, s.id as sala_id
            FROM pacientes p
            JOIN salas_quirofano s ON p.id = s.paciente_id
            WHERE p.estado_atencion = 'atendido'
        """)
        pacientes_atendidos = cur.fetchall()
        return render_template('dashboard.html', salas=salas,
                               pacientes_pendientes=pacientes_pendientes,
                               pacientes_atendidos=pacientes_atendidos)
    else:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada')
    return redirect(url_for('index'))

# ------------------- REGISTRO -------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        contraseña = request.form.get('contraseña')
        rol = request.form.get('rol')
        secreto = pyotp.random_base32()
        # Generar QR para Google Authenticator
        otp_uri = pyotp.totp.TOTP(secreto).provisioning_uri(name=nombre_usuario, issuer_name="HUC")
        if not os.path.exists('static/qr'):
            os.makedirs('static/qr')
        img = qrcode.make(otp_uri)
        img.save(f"static/qr/{nombre_usuario}_qr.png")
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO usuarios (nombre_usuario, contraseña, rol, `2AF`) VALUES (%s, %s, %s, %s)",
                (nombre_usuario, contraseña, rol, secreto)
            )
            mysql.connection.commit()
            flash('Registro exitoso. Escanee el QR con Google Authenticator.')
            return render_template('show_qr.html', gmail=nombre_usuario)
        except Exception as e:
            flash('Error: El usuario ya existe o los datos son inválidos.')
            return redirect(url_for('register'))
    return render_template('register.html')

# ------------------- SALAS DE QUIROFANO -------------------


@app.route('/salas')
def salas():
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT s.id, s.estado, s.hora_inicio, s.hora_fin,
               e.nombre_equipo, p.nombre_completo, m.nombre
        FROM salas_quirofano s
        LEFT JOIN equipos_medicos e ON s.equipo_id = e.id
        LEFT JOIN pacientes p ON s.paciente_id = p.id
        LEFT JOIN medicos m ON e.medico_id = m.id
    """)
    salas = cur.fetchall()
    return render_template('salas.html', salas=salas)



@app.route('/editar_sala/<int:id>', methods=['GET', 'POST'])
def editar_sala(id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        equipo_id = request.form['equipo_id']
        paciente_id = request.form['paciente_id']
        hora_inicio = request.form['hora_inicio']
        hora_fin = request.form['hora_fin']
        # Actualiza la sala y la pone en 'libre'
        cur.execute(
            "UPDATE salas_quirofano SET equipo_id=%s, paciente_id=%s, hora_inicio=%s, hora_fin=%s, estado='libre' WHERE id=%s",
            (equipo_id, paciente_id, hora_inicio, hora_fin, id)
        )
        # Si hay paciente asignado, ponlo en pendiente
        if paciente_id:
            cur.execute("UPDATE pacientes SET estado_atencion='pendiente' WHERE id=%s", (paciente_id,))
        mysql.connection.commit()
        flash('Quirófano actualizado correctamente')
        return redirect(url_for('salas'))
    # Obtener quirófano actual
    cur.execute("SELECT * FROM salas_quirofano WHERE id=%s", (id,))
    sala = cur.fetchone()
    # Obtener todas las salas para calcular el índice
    cur.execute("SELECT id FROM salas_quirofano ORDER BY id")
    todas_salas = [row[0] for row in cur.fetchall()]
    nombres = ['f','g','h','i','j','a','b','c','d','E']
    try:
        idx = todas_salas.index(id)
        nombre_quirofano = nombres[idx].upper()
    except Exception:
        nombre_quirofano = f"Q{id}"
    # Equipos médicos no asignados a ningún quirófano
    cur.execute("""
        SELECT id, nombre_equipo FROM equipos_medicos
        WHERE id NOT IN (
            SELECT equipo_id FROM salas_quirofano
            WHERE equipo_id IS NOT NULL AND id != %s
        )
    """, (id,))
    equipos_disponibles = cur.fetchall()
    # Pacientes no asignados a ningún quirófano
    cur.execute("SELECT id, nombre_completo FROM pacientes WHERE id NOT IN (SELECT paciente_id FROM salas_quirofano WHERE paciente_id IS NOT NULL AND id != %s)", (id,))
    pacientes_disponibles = cur.fetchall()
    return render_template('editar_sala.html', sala=sala, equipos_disponibles=equipos_disponibles, pacientes_disponibles=pacientes_disponibles, nombre_quirofano=nombre_quirofano)

# ------------------- MEDICOS -------------------

@app.route('/medico', methods=['GET'])
def medico():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Traer médicos junto con el nombre del equipo médico (si tiene)
    cur.execute("""
        SELECT m.id, m.nombre, m.cedula, m.especialidad, m.correo, m.telefono, em.nombre_equipo
        FROM medicos m
        LEFT JOIN equipos_medicos em ON m.id = em.medico_id
    """)
    medicos = cur.fetchall()
    # Traer enfermeros junto con el nombre del equipo médico (si tiene)
    cur.execute("""
        SELECT e.id, e.nombre, e.tipo, em.nombre_equipo
        FROM enfermeros e
        LEFT JOIN equipo_enfermeros ee ON e.id = ee.enfermero_id
        LEFT JOIN equipos_medicos em ON ee.equipo_id = em.id
    """)
    enfermeros = cur.fetchall()
    # Equipos médicos con nombres de médico y enfermeros
    cur.execute("SELECT * FROM equipos_medicos")
    equipos_raw = cur.fetchall()
    equipos = []
    for eq in equipos_raw:
        equipo_id, medico_id, nombre_equipo = eq
        # Obtener nombre del médico encargado
        cur.execute("SELECT nombre FROM medicos WHERE id=%s", (medico_id,))
        medico_nombre = cur.fetchone()[0] if medico_id else 'Sin médico'
        # Obtener enfermeros del equipo
        cur.execute("""SELECT e.nombre, e.tipo FROM equipo_enfermeros ee
                       JOIN enfermeros e ON ee.enfermero_id = e.id
                       WHERE ee.equipo_id = %s""", (equipo_id,))
        enfermeros_equipo = [{'nombre': enf[0], 'tipo': enf[1]} for enf in cur.fetchall()]
        equipos.append({
            'id': equipo_id,
            'nombre_equipo': nombre_equipo,
            'medico_nombre': medico_nombre,
            'enfermeros': enfermeros_equipo
        })
    return render_template('medico.html', medicos=medicos, enfermeros=enfermeros, equipos=equipos)

# Agregar médico
@app.route('/add_medico', methods=['POST'])
def add_medico():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    nombre = request.form.get('nombre')
    cedula = request.form.get('cedula')
    especialidad = request.form.get('especialidad')
    correo = request.form.get('correo')
    telefono = request.form.get('telefono')
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO medicos (nombre, cedula, especialidad, correo, telefono) VALUES (%s, %s, %s, %s, %s)",
        (nombre, cedula, especialidad, correo, telefono)
    )
    mysql.connection.commit()
    flash('Médico agregado correctamente')
    return redirect(url_for('medico'))


# Eliminar médico (desasigna de todos los equipos antes de eliminar)
@app.route('/delete_medico/<int:id>')
def delete_medico(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Desasignar médico de todos los equipos (poniendo medico_id a NULL)
    cur.execute("UPDATE equipos_medicos SET medico_id = NULL WHERE medico_id = %s", (id,))
    # Eliminar médico
    cur.execute("DELETE FROM medicos WHERE id = %s", (id,))
    mysql.connection.commit()
    flash('Médico desasignado de todos los equipos y eliminado correctamente.')
    return redirect(url_for('medico'))

# Agregar enfermero
@app.route('/add_enfermero', methods=['POST'])
def add_enfermero():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    nombre = request.form.get('nombre')
    tipo = request.form.get('tipo')
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO enfermeros (nombre, tipo) VALUES (%s, %s)",
        (nombre, tipo)
    )
    mysql.connection.commit()
    flash('Enfermero agregado correctamente')
    return redirect(url_for('medico') + '#enfermeros')


# Eliminar enfermero (desasigna de todos los equipos antes de eliminar)
@app.route('/delete_enfermero/<int:id>')
def delete_enfermero(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Desasignar enfermero de todos los equipos
    cur.execute("DELETE FROM equipo_enfermeros WHERE enfermero_id = %s", (id,))
    # Eliminar enfermero
    cur.execute("DELETE FROM enfermeros WHERE id = %s", (id,))
    mysql.connection.commit()
    flash('Enfermero desasignado de todos los equipos y eliminado correctamente.')
    return redirect(url_for('medico') + '#enfermeros')

# Agregar equipo médico
@app.route('/add_equipo', methods=['POST'])
def add_equipo():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    nombre_equipo = request.form.get('nombre_equipo')
    medico_id = request.form.get('medico_id')
    enfermeros_ids = request.form.getlist('enfermeros_ids')
    cur = mysql.connection.cursor()
    cur.execute(
        "INSERT INTO equipos_medicos (medico_id, nombre_equipo) VALUES (%s, %s)",
        (medico_id, nombre_equipo)
    )
    equipo_id = cur.lastrowid
    for enf_id in enfermeros_ids:
        cur.execute(
            "INSERT INTO equipo_enfermeros (equipo_id, enfermero_id) VALUES (%s, %s)",
            (equipo_id, enf_id)
        )
    mysql.connection.commit()
    flash('Equipo médico agregado correctamente')
    return redirect(url_for('medico') + '#equipos')



# ------------------- PACIENTES -------------------

@app.route('/pacientes')
def pacientes():
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))

    page = request.args.get('page', default=1, type=int)
    per_page = 10
    nombre = request.args.get('nombre', '').strip()
    cedula = request.args.get('cedula', '').strip()

    cur = mysql.connection.cursor()

    # Construir consulta dinámica
    base_query = """
        SELECT p.id, p.nombre_completo, p.edad, p.fecha_nacimiento, p.tipo_sangre, p.motivo_cirugia, 
               e.nombre_equipo, p.cedula, p.telefono
        FROM pacientes p
        LEFT JOIN equipos_medicos e ON p.equipo_id = e.id
    """
    filters = []
    params = []

    if nombre:
        filters.append("p.nombre_completo LIKE %s")
        params.append(f"%{nombre}%")
    if cedula:
        filters.append("p.cedula LIKE %s")
        params.append(f"%{cedula}%")

    if filters:
        base_query += " WHERE " + " AND ".join(filters)

    cur.execute(base_query, params)
    all_pacientes = cur.fetchall()

    total_pacientes = len(all_pacientes)
    total_pages = (total_pacientes + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    pacientes_paginados = all_pacientes[start:end]

    return render_template(
        'pacientes.html',
        pacientes=pacientes_paginados,
        page=page,
        total_pages=total_pages,
        nombre=nombre,
        cedula=cedula
    )


# Agregar paciente
@app.route('/add_paciente', methods=['GET', 'POST'])
def add_paciente():
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))

    page = request.args.get('page', default=1, type=int)
    per_page = 10
    query = request.args.get('query', default='', type=str)

    cur = mysql.connection.cursor()

    if query:
        cur.execute("""
            SELECT p.id, p.nombre_completo, p.edad, p.fecha_nacimiento, p.tipo_sangre, p.motivo_cirugia, 
                   e.nombre_equipo, p.cedula, p.telefono
            FROM pacientes p
            LEFT JOIN equipos_medicos e ON p.equipo_id = e.id
            WHERE p.nombre_completo LIKE %s OR p.cedula LIKE %s
        """, (f"%{query}%", f"%{query}%"))
    else:
        cur.execute("""
            SELECT p.id, p.nombre_completo, p.edad, p.fecha_nacimiento, p.tipo_sangre, p.motivo_cirugia, 
                   e.nombre_equipo, p.cedula, p.telefono
            FROM pacientes p
            LEFT JOIN equipos_medicos e ON p.equipo_id = e.id
        """)

    all_pacientes = cur.fetchall()
    total_pacientes = len(all_pacientes)
    total_pages = (total_pacientes + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    pacientes_paginados = all_pacientes[start:end]

    return render_template(
        'pacientes.html',
        pacientes=pacientes_paginados,
        page=page,
        total_pages=total_pages,
        query=query  # opcional si quieres mantener el texto en el input
    )



# Editar paciente
@app.route('/editar_paciente/<int:id>', methods=['GET', 'POST'])
def editar_paciente(id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        # Obtener datos del formulario
        nombre_completo = request.form['nombre_completo']
        cedula = request.form['cedula']
        telefono = request.form['telefono']
        edad = request.form['edad']
        fecha_nacimiento = request.form['fecha_nacimiento']
        tipo_sangre = request.form['tipo_sangre']
        motivo_cirugia = request.form['motivo_cirugia']
        
        # Actualizar el paciente en la base de datos
        cur.execute("""
            UPDATE pacientes
            SET nombre_completo = %s, cedula = %s, telefono = %s, edad = %s, 
                fecha_nacimiento = %s, tipo_sangre = %s, motivo_cirugia = %s
            WHERE id = %s
        """, (nombre_completo, cedula, telefono, edad, fecha_nacimiento, tipo_sangre, motivo_cirugia, id))
        mysql.connection.commit()
        flash('Paciente actualizado exitosamente')
        return redirect(url_for('pacientes'))
    
    # Obtener los datos actuales del paciente
    cur.execute("SELECT * FROM pacientes WHERE id = %s", (id,))
    paciente = cur.fetchone()
    if not paciente:
        flash('Paciente no encontrado')
        return redirect(url_for('pacientes'))
    
    return render_template('editar_paciente.html', paciente=paciente)



#Eliminar Paciente

@app.route('/eliminar_paciente/<int:id>', methods=['POST'])
def eliminar_paciente(id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    try:
        # Eliminar el paciente de la base de datos
        cur.execute("DELETE FROM pacientes WHERE id = %s", (id,))
        mysql.connection.commit()
        flash('Paciente eliminado correctamente')
    except Exception as e:
        flash('Error al eliminar el paciente')
    return redirect(url_for('pacientes'))

# ------------------- HISTORIAL USO -------------------

@app.route('/historial')
def historial():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT h.id, h.sala_id, h.medico_id, h.fecha_uso, h.duracion, h.descripcion,
               m.nombre
        FROM historial_uso h
        LEFT JOIN medicos m ON h.medico_id = m.id
        ORDER BY h.fecha_uso DESC
    """)
    historial = cur.fetchall()
    # Para mostrar el nombre del quirófano, usa el mismo arreglo de nombres
    cur.execute("SELECT id FROM salas_quirofano ORDER BY id")
    todas_salas = [row[0] for row in cur.fetchall()]
    nombres = ['f','g','h','i','j','a','b','c','d','E']
    historial_data = []
    for h in historial:
        sala_id = h[1]
        try:
            idx = todas_salas.index(sala_id)
            nombre_quirofano = nombres[idx].upper()
        except Exception:
            nombre_quirofano = f"Q{sala_id}"
        historial_data.append({
            'id': h[0],
            'quirofano': nombre_quirofano,
            'medico': h[6] or 'Sin médico',
            'fecha_uso': h[3],
            'duracion': h[4],
            'descripcion': h[5]
        })
    return render_template('historial.html', historial=historial_data)

@app.route('/cancelar_paciente/<int:paciente_id>')
def cancelar_paciente(paciente_id):
    cur = mysql.connection.cursor()
    # Obtener datos para historial
    cur.execute("""
        SELECT s.id, s.equipo_id, s.hora_inicio, s.hora_fin
        FROM salas_quirofano s
        WHERE s.paciente_id = %s
    """, (paciente_id,))
    sala = cur.fetchone()
    sala_id, equipo_id, hora_inicio, hora_fin = sala if sala else (None, None, None, None)
    medico_id = None
    if equipo_id:
        cur.execute("SELECT medico_id FROM equipos_medicos WHERE id=%s", (equipo_id,))
        row = cur.fetchone()
        medico_id = row[0] if row else None
    duracion = None
    if hora_inicio and hora_fin:
        try:
            t1 = parse_hora(hora_inicio)
            t2 = parse_hora(hora_fin)
            duracion = str(t2 - t1)
        except Exception:
            duracion = ""
    # Registrar en historial
    cur.execute("""
        INSERT INTO historial_uso (sala_id, medico_id, fecha_uso, duracion, descripcion)
        VALUES (%s, %s, NOW(), %s, %s)
    """, (sala_id, medico_id, duracion, "Operación cancelada"))
    # Limpiar quirófano
    cur.execute("""
        UPDATE salas_quirofano
        SET paciente_id=NULL, equipo_id=NULL, hora_inicio=NULL, hora_fin=NULL, estado='libre'
        WHERE id=%s
    """, (sala_id,))
    # Actualizar paciente
    cur.execute("UPDATE pacientes SET estado_atencion='cancelado', resultado_final='Operación cancelada' WHERE id=%s", (paciente_id,))
    mysql.connection.commit()
    flash('Operación cancelada, quirófano liberado y paciente movido al historial')
    return redirect(url_for('dashboard'))

@app.route('/marcar_atendido/<int:paciente_id>')
def marcar_atendido(paciente_id):
    cur = mysql.connection.cursor()
    # Cambia estado del paciente y quirófano
    cur.execute("UPDATE pacientes SET estado_atencion='atendido' WHERE id=%s", (paciente_id,))
    cur.execute("UPDATE salas_quirofano SET estado='en uso' WHERE paciente_id=%s", (paciente_id,))
    mysql.connection.commit()
    flash('Paciente aceptado y quirófano en uso')
    return redirect(url_for('dashboard'))

@app.route('/validar_paciente/<int:paciente_id>', methods=['POST'])
def validar_paciente(paciente_id):
    resultado = request.form['resultado_final']
    cur = mysql.connection.cursor()
    # Obtener datos para historial
    cur.execute("""
        SELECT s.id, s.equipo_id, s.hora_inicio, s.hora_fin
        FROM salas_quirofano s
        WHERE s.paciente_id = %s
    """, (paciente_id,))
    sala = cur.fetchone()
    sala_id, equipo_id, hora_inicio, hora_fin = sala if sala else (None, None, None, None)
    medico_id = None
    if equipo_id:
        cur.execute("SELECT medico_id FROM equipos_medicos WHERE id=%s", (equipo_id,))
        row = cur.fetchone()
        medico_id = row[0] if row else None
    duracion = None
    if hora_inicio and hora_fin:
        try:
            t1 = parse_hora(hora_inicio)
            t2 = parse_hora(hora_fin)
            duracion = str(t2 - t1)
        except Exception:
            duracion = "00:00:00"  # Valor predeterminado si falla el cálculo
    else:
        duracion = "00:00:00"  # Valor predeterminado si no hay horas

    # Registrar en historial
    cur.execute("""
        INSERT INTO historial_uso (sala_id, medico_id, fecha_uso, duracion, descripcion)
        VALUES (%s, %s, NOW(), %s, %s)
    """, (sala_id, medico_id, duracion, resultado))
    # SOLO cambia el estado a mantenimiento, NO limpies los datos
    cur.execute("""
        UPDATE salas_quirofano
        SET estado='mantenimiento'
        WHERE id=%s
    """, (sala_id,))
    # Actualizar paciente
    cur.execute("UPDATE pacientes SET estado_atencion='validado', resultado_final=%s WHERE id=%s", (resultado, paciente_id))
    mysql.connection.commit()
    flash('Paciente validado, quirófano en mantenimiento y movido al historial')
    return redirect(url_for('dashboard'))

@app.route('/dashboard_data')
def dashboard_data():
    actualizar_quirofanos_mantenimiento()
    cur = mysql.connection.cursor()
    # Pacientes pendientes
    cur.execute("""
        SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin
        FROM pacientes p
        JOIN salas_quirofano s ON p.id = s.paciente_id
        WHERE p.estado_atencion = 'pendiente'
    """)
    pendientes = cur.fetchall()
    # Pacientes atendidos
    cur.execute("""
        SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin
        FROM pacientes p
        JOIN salas_quirofano s ON p.id = s.paciente_id
        WHERE p.estado_atencion = 'atendido'
    """)
    atendidos = cur.fetchall()
    # Estados de quirófanos
    cur.execute("SELECT id, estado FROM salas_quirofano")
    salas = cur.fetchall()

    # Convertir timedelta a string si es necesario
    def serialize_timedelta(obj):
        if isinstance(obj, datetime.timedelta):
            return str(obj)
        return obj

    return jsonify({
        'pendientes': [[serialize_timedelta(item) for item in row] for row in pendientes],
        'atendidos': [[serialize_timedelta(item) for item in row] for row in atendidos],
        'salas': salas
    })

@app.route('/modificar_hora/<int:sala_id>', methods=['GET', 'POST'])
def modificar_hora(sala_id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        nueva_hora_fin = request.form['hora_fin']
        # Obtener la hora_fin anterior
        cur.execute("SELECT hora_fin FROM salas_quirofano WHERE id=%s", (sala_id,))
        vieja_hora_fin = cur.fetchone()[0]
        # Actualizar la hora_fin de la sala actual
        cur.execute("UPDATE salas_quirofano SET hora_fin=%s WHERE id=%s", (nueva_hora_fin, sala_id))
        # Calcular diferencia
        t_vieja = parse_hora(vieja_hora_fin)
        t_nueva = parse_hora(nueva_hora_fin)
        diferencia = t_nueva - t_vieja
        # Actualizar horas de los pacientes pendientes en ese quirófano
        cur.execute("""
            SELECT id, hora_inicio, hora_fin FROM salas_quirofano
            WHERE id != %s AND equipo_id = (SELECT equipo_id FROM salas_quirofano WHERE id=%s) AND hora_inicio > %s
            ORDER BY hora_inicio
        """, (sala_id, sala_id, vieja_hora_fin))
        for s in cur.fetchall():
            nueva_inicio = (parse_hora(s[1]) + diferencia).time()
            nueva_fin = (parse_hora(s[2]) + diferencia).time()
            cur.execute("UPDATE salas_quirofano SET hora_inicio=%s, hora_fin=%s WHERE id=%s", (nueva_inicio, nueva_fin, s[0]))
        mysql.connection.commit()
        flash('Hora de fin modificada y horarios de pacientes pendientes actualizados.')
        return redirect(url_for('dashboard'))
    # GET: mostrar formulario simple
    cur.execute("SELECT hora_fin FROM salas_quirofano WHERE id=%s", (sala_id,))
    hora_fin = cur.fetchone()[0]
    return render_template('modificar_hora.html', sala_id=sala_id, hora_fin=hora_fin)

def parse_hora(hora_str):
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(hora_str), fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de hora no válido: {hora_str}")

def actualizar_quirofanos_mantenimiento():
    cur = mysql.connection.cursor()
    from datetime import datetime
    # Selecciona quirófanos en uso cuya hora_fin ya pasó
    cur.execute("""
        SELECT id, hora_fin FROM salas_quirofano
        WHERE estado='en uso' AND hora_fin IS NOT NULL
    """)
    ahora = datetime.now().time()
    for sala_id, hora_fin in cur.fetchall():
        try:
            fin = parse_hora(hora_fin).time()
            if ahora >= fin:
                cur.execute("UPDATE salas_quirofano SET estado='mantenimiento' WHERE id=%s", (sala_id,))
        except Exception:
            continue
    mysql.connection.commit()

@app.route('/liberar_quirofano/<int:sala_id>')
def liberar_quirofano(sala_id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE salas_quirofano
        SET paciente_id=NULL, equipo_id=NULL, hora_inicio=NULL, hora_fin=NULL, estado='libre'
        WHERE id=%s
    """, (sala_id,))
    mysql.connection.commit()
    flash('Quirófano liberado y listo para usar')
    return redirect(url_for('dashboard'))

@app.route('/editar_equipo/<int:equipo_id>', methods=['GET', 'POST'])
def editar_equipo(equipo_id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Obtener datos del equipo
    cur.execute("SELECT * FROM equipos_medicos WHERE id = %s", (equipo_id,))
    equipo = cur.fetchone()
    # Obtener todos los médicos
    cur.execute("SELECT id, nombre FROM medicos")
    medicos = cur.fetchall()
    # Obtener todos los enfermeros
    cur.execute("SELECT id, nombre, tipo FROM enfermeros")
    enfermeros = cur.fetchall()
    # Enfermeros asignados a este equipo
    cur.execute("SELECT enfermero_id FROM equipo_enfermeros WHERE equipo_id = %s", (equipo_id,))
    enfermeros_asignados = [row[0] for row in cur.fetchall()]

    if request.method == 'POST':
        # Actualizar médico encargado
        medico_id = request.form.get('medico_id')
        cur.execute("UPDATE equipos_medicos SET medico_id = %s WHERE id = %s", (medico_id, equipo_id))
        # Actualizar enfermeros asignados
        nuevos_enfermeros = request.form.getlist('enfermeros_ids')
        # Eliminar todos los enfermeros actuales
        cur.execute("DELETE FROM equipo_enfermeros WHERE equipo_id = %s", (equipo_id,))
        # Insertar los nuevos
        for enf_id in nuevos_enfermeros:
            cur.execute("INSERT INTO equipo_enfermeros (equipo_id, enfermero_id) VALUES (%s, %s)", (equipo_id, enf_id))
        mysql.connection.commit()
        flash('Equipo médico actualizado correctamente.')
        return redirect(url_for('medico') + '#equipos')

    return render_template('editar_equipo.html',
                           equipo=equipo,
                           medicos=medicos,
                           enfermeros=enfermeros,
                           enfermeros_asignados=enfermeros_asignados)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=50000)