from flask import Flask, render_template, request, url_for, redirect, flash, session, jsonify
from flask_mysqldb import MySQL
import pyotp
import qrcode
import os
from datetime import datetime
import os
from werkzeug.utils import secure_filename

from datetime import time

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
        # Comprobar columna 'estado' si existe
        try:
            cur.execute("SELECT estado FROM usuarios WHERE nombre_usuario=%s", (nombre_usuario,))
            estado = cur.fetchone()
            if estado and estado[0] == 'pendiente':
                flash('Tu cuenta está pendiente de aprobación por un administrador. Espera confirmación.')
                return redirect(url_for('index'))
        except Exception:
            # Si no existe columna 'estado', mantenemos la compatibilidad con 'rol' == 'pendiente'
            if resultado[1] == 'pendiente':
                flash('Tu cuenta está pendiente de aprobación por un administrador. Espera confirmación.')
                return redirect(url_for('index'))
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

        # Salas para el SVG y tabla
        cur.execute("""
            SELECT s.*, 
                   e.nombre_equipo, 
                   p.nombre_completo,
                   m.nombre AS medico_nombre
            FROM salas_quirofano s
            LEFT JOIN equipos_medicos e ON s.equipo_id = e.id
            LEFT JOIN pacientes p ON s.paciente_id = p.id
            LEFT JOIN medicos m ON e.medico_id = m.id
        """)
        salas = cur.fetchall()

        # Pacientes pendientes (en quirófano, estado pendiente)
        cur.execute("""
            SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin, s.id as sala_id
            FROM pacientes p
            JOIN salas_quirofano s ON p.id = s.paciente_id
            WHERE p.estado_atencion = 'pendiente'
        """)
        pacientes_pendientes = cur.fetchall()

        # Pacientes atendidos (estado atendido)
        cur.execute("""
            SELECT p.id, p.nombre_completo, s.hora_inicio, s.hora_fin, s.id as sala_id
            FROM pacientes p
            JOIN salas_quirofano s ON p.id = s.paciente_id
            WHERE p.estado_atencion = 'atendido'
        """)
        pacientes_atendidos = cur.fetchall()

        # Reservas pendientes (futuras)
        cur.execute("""
            SELECT r.*, p.nombre_completo, e.nombre_equipo
            FROM reservas r
            LEFT JOIN pacientes p ON r.paciente_id = p.id
            LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
            WHERE r.estado = 'pendiente'
        """)
        reservas_pendientes = cur.fetchall()

        # Equipos médicos disponibles
        cur.execute("SELECT id, nombre_equipo FROM equipos_medicos")
        equipos = cur.fetchall()

        return render_template('dashboard.html',
                               salas=salas,
                               pacientes_pendientes=pacientes_pendientes,
                               pacientes_atendidos=pacientes_atendidos,
                               reservas_pendientes=reservas_pendientes,
                               equipos=equipos)
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
        # Nuevo flujo: los usuarios se registran como 'usuario' pero con estado 'pendiente'
        rol = 'usuario'
        estado = 'pendiente'
        secreto = pyotp.random_base32()
        # Generar QR para Google Authenticator
        otp_uri = pyotp.totp.TOTP(secreto).provisioning_uri(name=nombre_usuario, issuer_name="HUC")

        # Crear carpeta específica para el usuario
        qr_dir = os.path.join('static', 'qr', nombre_usuario)
        os.makedirs(qr_dir, exist_ok=True)

        # Guardar el QR dentro de esa carpeta
        img = qrcode.make(otp_uri)
        img.save(os.path.join(qr_dir, f"{nombre_usuario}_qr.png"))

                # Crear cursor antes del try
        cur = mysql.connection.cursor()
        try:
            # Intentar insertar con columna 'estado' (si existe)
            try:
                cur.execute(
                    "INSERT INTO usuarios (nombre_usuario, contraseña, rol, `2AF`, estado) VALUES (%s, %s, %s, %s, %s)",
                    (nombre_usuario, contraseña, rol, secreto, estado)
                )
            except Exception:
                # Si la columna 'estado' no existe (esquema antiguo), insertar sin ella
                cur.execute(
                    "INSERT INTO usuarios (nombre_usuario, contraseña, rol, `2AF`) VALUES (%s, %s, %s, %s)",
                    (nombre_usuario, contraseña, rol, secreto)
                )
            mysql.connection.commit()
            flash('Registro exitoso. Escanee el QR con Google Authenticator.')
            return render_template('show_qr.html', gmail=nombre_usuario)
        except Exception as e:
            print("Error en registro:", e)
            flash('Error: El usuario ya existe o los datos son inválidos.')
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/usuarios')
def usuarios():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    cur = mysql.connection.cursor()
    cur.execute("SELECT nombre_usuario, rol, `2AF`, estado FROM usuarios")
    usuarios = cur.fetchall()
    print("Usuarios encontrados:", usuarios)  # 👈 imprime en consola para verificar



@app.route('/pending_users')
def pending_users():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT nombre_usuario, rol, `2AF`, estado FROM usuarios")
    pendientes = cur.fetchall()
    return render_template('pendientes.html', pendientes=pendientes)



@app.route('/approve_user/<username>', methods=['POST'])
def approve_user(username):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    rol = request.form.get('rol', 'usuario')  # por defecto usuario
    cur = mysql.connection.cursor()

    try:
        cur.execute("UPDATE usuarios SET estado='aprobado', rol=%s WHERE nombre_usuario=%s", (rol, username))
    except Exception:
        cur.execute("UPDATE usuarios SET rol=%s WHERE nombre_usuario=%s", (rol, username))

    mysql.connection.commit()
    flash(f'Usuario {username} aprobado como {rol}.')
    return redirect(url_for('pending_users'))


@app.route('/reject_user/<username>')
def reject_user(username):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM usuarios WHERE nombre_usuario=%s", (username,))
    mysql.connection.commit()
    flash(f'Usuario {username} rechazado y eliminado.')
    return redirect(url_for('pending_users'))

@app.route('/change_password/<username>', methods=['GET', 'POST'])
def change_password(username):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nueva = request.form.get('nueva_contraseña')
        cur = mysql.connection.cursor()
        cur.execute("UPDATE usuarios SET contraseña=%s WHERE nombre_usuario=%s", (nueva, username))
        mysql.connection.commit()
        flash(f'Contraseña actualizada para {username}.')
        return redirect(url_for('usuarios'))
    return render_template('cambiar_contraseña.html', username=username)

@app.route('/change_role/<username>', methods=['POST'])
def change_role(username):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    nuevo_rol = request.form.get('rol')
    cur = mysql.connection.cursor()
    cur.execute("UPDATE usuarios SET rol=%s WHERE nombre_usuario=%s", (nuevo_rol, username))
    mysql.connection.commit()
    flash(f'Rol actualizado para {username}.')
    return redirect(url_for('usuarios'))




# ------------------- SALAS DE QUIROFANO -------------------


@app.route('/salas')
def salas():
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()

    # Salas quirófano con equipo, paciente y médico
    cur.execute("""
        SELECT s.id, s.estado, s.hora_inicio, s.hora_fin,
               e.nombre_equipo, p.nombre_completo, m.nombre
        FROM salas_quirofano s
        LEFT JOIN equipos_medicos e ON s.equipo_id = e.id
        LEFT JOIN pacientes p ON s.paciente_id = p.id
        LEFT JOIN medicos m ON e.medico_id = m.id
    """)
    salas = cur.fetchall()

    # Equipos médicos disponibles (no asignados a ninguna sala)
    cur.execute("""
        SELECT id, nombre_equipo
        FROM equipos_medicos
        WHERE id NOT IN (
            SELECT equipo_id FROM salas_quirofano
            WHERE equipo_id IS NOT NULL
        )
    """)
    equipos_disponibles = cur.fetchall()

    # Pacientes disponibles (no asignados a ninguna sala)
    cur.execute("""
        SELECT id, nombre_completo, cedula, edad, motivo_cirugia
        FROM pacientes
        WHERE id NOT IN (
            SELECT paciente_id FROM salas_quirofano
            WHERE paciente_id IS NOT NULL
        )
        AND estado_atencion = 'pendiente'
    """)
    pacientes_disponibles = cur.fetchall()

    return render_template('salas.html',
                           salas=salas,
                           equipos_disponibles=equipos_disponibles,
                           pacientes_disponibles=pacientes_disponibles)


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

        # Actualiza la sala
        cur.execute("""
            UPDATE salas_quirofano
            SET equipo_id=%s, paciente_id=%s, hora_inicio=%s, hora_fin=%s, estado='libre'
            WHERE id=%s
        """, (equipo_id, paciente_id, hora_inicio, hora_fin, id))

        # Actualiza el paciente con equipo y estado
        if paciente_id and equipo_id:
            cur.execute("""
                UPDATE pacientes
                SET estado_atencion='pendiente', equipo_id=%s
                WHERE id=%s
            """, (equipo_id, paciente_id))

        mysql.connection.commit()
        flash('Quirófano actualizado correctamente')
        return redirect(url_for('salas'))

    # Obtener quirófano actual
    cur.execute("SELECT * FROM salas_quirofano WHERE id=%s", (id,))
    sala = cur.fetchone()

    # Calcular nombre del quirófano
    cur.execute("SELECT id FROM salas_quirofano ORDER BY id")
    todas_salas = [row[0] for row in cur.fetchall()]
    nombres = ['f','g','h','i','j','a','b','c','d','E']
    try:
        idx = todas_salas.index(id)
        nombre_quirofano = nombres[idx].upper()
    except Exception:
        nombre_quirofano = f"Q{id}"

    # Equipos médicos disponibles
    cur.execute("""
        SELECT id, nombre_equipo
        FROM equipos_medicos
        WHERE id NOT IN (
            SELECT equipo_id FROM salas_quirofano
            WHERE equipo_id IS NOT NULL AND id != %s
        )
    """, (id,))
    equipos_disponibles = cur.fetchall()

    # Pacientes disponibles (con cédula)
    cur.execute("""
        SELECT id, nombre_completo, cedula, edad, motivo_cirugia
        FROM pacientes
        WHERE id NOT IN (
            SELECT paciente_id FROM salas_quirofano
            WHERE paciente_id IS NOT NULL AND id != %s
        )
    """, (id,))
    pacientes_disponibles = cur.fetchall()

    return render_template(
        'editar_sala.html',
        sala=sala,
        equipos_disponibles=equipos_disponibles,
        pacientes_disponibles=pacientes_disponibles,
        nombre_quirofano=nombre_quirofano
    )

# ------------------- MEDICOS -------------------

@app.route('/medico', methods=['GET'])
def medico():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Traer médicos junto con el nombre del equipo médico (si tiene)
    cur.execute("""
    SELECT m.id, m.nombre, m.cedula, m.especialidad, m.correo, m.telefono, em.nombre_equipo, m.foto, m.fecha_ingreso
    FROM medicos m
    LEFT JOIN equipos_medicos em ON m.id = em.medico_id
""")


    cur.execute("""
    SELECT m.id, m.nombre, m.cedula, m.especialidad, m.correo, m.telefono, em.nombre_equipo, m.foto, m.fecha_ingreso
    FROM medicos m
    LEFT JOIN equipos_medicos em ON m.id = em.medico_id
""")
    medicos_raw = cur.fetchall()

    medicos = []
    for m in medicos_raw:
        fecha_formateada = m[8].strftime('%d/%m/%Y') if m[8] else 'Sin fecha'
        medicos.append(m[:8] + (fecha_formateada,))


    # Traer enfermeros junto con el nombre del equipo médico (si tiene)
    cur.execute("""
    SELECT e.id, e.nombre, e.tipo, em.nombre_equipo, e.cedula, e.correo, e.telefono, e.foto, e.fecha_ingreso
    FROM enfermeros e
    LEFT JOIN equipo_enfermeros ee ON e.id = ee.enfermero_id
    LEFT JOIN equipos_medicos em ON ee.equipo_id = em.id
    """)
    enfermeros_raw = cur.fetchall()

    enfermeros = []
    for e in enfermeros_raw:
        fecha_formateada = e[8].strftime('%d/%m/%Y') if e[8] else 'Sin fecha'
        enfermeros.append(e[:8] + (fecha_formateada,))


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
        cur.execute("""SELECT e.id, e.nombre, e.tipo FROM equipo_enfermeros ee
               JOIN enfermeros e ON ee.enfermero_id = e.id
               WHERE ee.equipo_id = %s""", (equipo_id,))
        enfermeros_equipo = [{'id': enf[0], 'nombre': enf[1], 'tipo': enf[2]} for enf in cur.fetchall()]

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
    nombre = request.form['nombre']
    especialidad = request.form['especialidad']
    correo = request.form['correo']

    prefijo = request.form.get('prefijo_cedula')
    numero = request.form.get('numero_cedula')
    cedula = f"{prefijo}-{numero}" if prefijo and numero else None

    codigo = request.form.get('codigo_pais')
    telefono = request.form.get('numero_telefono')
    telefono_completo = f"{codigo}-{telefono}" if codigo and telefono else None

    foto = request.files.get('foto')
    nombre_foto = None

    if foto and foto.filename and foto.filename != '':
        nombre_normalizado = secure_filename(nombre.replace(" ", "_"))
        carpeta_medico = os.path.join('static/fotos_medicos', f"medico_{nombre_normalizado}_{cedula}")
        os.makedirs(carpeta_medico, exist_ok=True)

        nombre_archivo = secure_filename(foto.filename)
        ruta_foto = os.path.join(carpeta_medico, nombre_archivo)

        try:
            foto.save(ruta_foto)
            nombre_foto = f"medico_{nombre_normalizado}_{cedula}/{nombre_archivo}"
        except Exception as e:
            print(f"Error al guardar la imagen: {e}")
            flash('Hubo un problema al guardar la foto.')
            nombre_foto = None




    if not cedula:
        return "Error: Cédula incompleta", 400

    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO medicos (nombre, especialidad, telefono, cedula, correo, foto)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nombre, especialidad, telefono_completo, cedula, correo, nombre_foto))
    mysql.connection.commit()
    return redirect(url_for('medico'))

# Actualizar médico

@app.route('/update_medico/<int:id>', methods=['POST'])
def update_medico(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    nombre = request.form['nombre']
    especialidad = request.form['especialidad']
    correo = request.form['correo']
    telefono = request.form['telefono']
    cedula = request.form['cedula']

    foto = request.files.get('foto')
    nombre_foto = None

    if foto and foto.filename != '':
        # Crear carpeta personalizada con nombre y cédula
        nombre_normalizado = secure_filename(nombre.replace(" ", "_"))
        carpeta_medico = os.path.join('static/fotos_medicos', f"medico_{nombre_normalizado}_{cedula}")
        os.makedirs(carpeta_medico, exist_ok=True)

        nombre_archivo = secure_filename(foto.filename)
        ruta_foto = os.path.join(carpeta_medico, nombre_archivo)
        foto.save(ruta_foto)

        # Ruta relativa para guardar en la base de datos
        nombre_foto = f"medico_{nombre_normalizado}_{cedula}/{nombre_archivo}"


    cur = mysql.connection.cursor()
    if nombre_foto:
        cur.execute("""
            UPDATE medicos SET nombre=%s, especialidad=%s, correo=%s, telefono=%s, cedula=%s, foto=%s WHERE id=%s
        """, (nombre, especialidad, correo, telefono, cedula, nombre_foto, id))
    else:
        cur.execute("""
            UPDATE medicos SET nombre=%s, especialidad=%s, correo=%s, telefono=%s, cedula=%s WHERE id=%s
        """, (nombre, especialidad, correo, telefono, cedula, id))

    mysql.connection.commit()
    flash('Médico actualizado correctamente.')
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



# ----------------------Enfermeros----------------------
# Agregar enfermero
@app.route('/add_enfermero', methods=['POST'])
def add_enfermero():
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    nombre = request.form.get('nombre')
    tipo = request.form.get('tipo')
    cedula = request.form.get('prefijo_cedula') + '-' + request.form.get('numero_cedula')
    telefono = request.form.get('codigo_pais') + '-' + request.form.get('numero_telefono')
    correo = request.form.get('correo')

    foto = request.files.get('foto')
    nombre_foto = None

    if foto and foto.filename != '':
        carpeta = os.path.join('static/fotos_enfermeros', f"enfermero_{cedula}")
        os.makedirs(carpeta, exist_ok=True)
        nombre_foto = secure_filename(foto.filename)
        ruta_foto = os.path.join(carpeta, nombre_foto)
        foto.save(ruta_foto)
        nombre_foto = f"enfermero_{cedula}/{nombre_foto}"

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO enfermeros (nombre, tipo, cedula, correo, telefono, foto)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nombre, tipo, cedula, correo, telefono, nombre_foto))
    mysql.connection.commit()
    flash('Enfermero agregado correctamente')
    return redirect(url_for('medico') + '#enfermeros')




@app.route('/update_enfermero/<int:id>', methods=['POST'])
def update_enfermero(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    nombre = request.form['nombre']
    tipo = request.form['tipo']
    correo = request.form['correo']
    telefono = request.form['telefono']
    cedula = request.form['cedula']

    foto = request.files.get('foto')
    nombre_foto = None

    if foto and foto.filename and foto.filename != '':
        nombre_normalizado = secure_filename(nombre.replace(" ", "_"))
        carpeta = os.path.join('static/fotos_enfermeros', f"enfermero_{nombre_normalizado}_{cedula}")
        os.makedirs(carpeta, exist_ok=True)

        nombre_archivo = secure_filename(foto.filename)
        ruta_foto = os.path.join(carpeta, nombre_archivo)

        try:
            foto.save(ruta_foto)
            nombre_foto = f"enfermero_{nombre_normalizado}_{cedula}/{nombre_archivo}"
        except Exception as e:
            print(f"Error al guardar la imagen: {e}")
            flash('Hubo un problema al guardar la foto.')
            nombre_foto = None

    cur = mysql.connection.cursor()
    if nombre_foto:
        cur.execute("""
            UPDATE enfermeros SET nombre=%s, tipo=%s, correo=%s, telefono=%s, cedula=%s, foto=%s WHERE id=%s
        """, (nombre, tipo, correo, telefono, cedula, nombre_foto, id))
    else:
        cur.execute("""
            UPDATE enfermeros SET nombre=%s, tipo=%s, correo=%s, telefono=%s, cedula=%s WHERE id=%s
        """, (nombre, tipo, correo, telefono, cedula, id))

    mysql.connection.commit()
    flash('Enfermero actualizado correctamente.')
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



# ------Equipos Medicos ---------------
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


@app.route('/detalle_medico/<int:id>')
def detalle_medico(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()

    # Datos del médico
    cur.execute("""
        SELECT m.id, m.nombre, m.cedula, m.especialidad, m.correo, m.telefono, m.fecha_ingreso,
               em.nombre_equipo
        FROM medicos m
        LEFT JOIN equipos_medicos em ON m.id = em.medico_id
        WHERE m.id = %s
    """, (id,))
    medico = cur.fetchone()
    if not medico:
        flash('Médico no encontrado.')
        return redirect(url_for('medico'))

    # Enfermeros del equipo
    cur.execute("""
        SELECT e.nombre, e.tipo
        FROM equipo_enfermeros ee
        JOIN enfermeros e ON ee.enfermero_id = e.id
        WHERE ee.equipo_id = (
            SELECT id FROM equipos_medicos WHERE medico_id = %s
        )
    """, (id,))
    enfermeros = cur.fetchall()

    # Pacientes asignados (si tienes esa relación)
    cur.execute("""
        SELECT nombre_completo, cedula, motivo_cirugia
        FROM pacientes
        WHERE equipo_id = (
            SELECT id FROM equipos_medicos WHERE medico_id = %s
        )
    """, (id,))
    pacientes = cur.fetchall()

    return render_template('detalle_medico.html',
                           medico=medico,
                           enfermeros=enfermeros,
                           pacientes=pacientes)


@app.route('/editar_equipo/<int:equipo_id>', methods=['GET', 'POST'])
def editar_equipo(equipo_id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        nombre_equipo = request.form.get('nombre_equipo')
        medico_id = request.form.get('medico_id')
        enfermeros_ids = request.form.getlist('enfermeros_ids')

        cur.execute("UPDATE equipos_medicos SET nombre_equipo=%s, medico_id=%s WHERE id=%s",
                    (nombre_equipo, medico_id, equipo_id))
        cur.execute("DELETE FROM equipo_enfermeros WHERE equipo_id=%s", (equipo_id,))
        for enf_id in enfermeros_ids:
            cur.execute("INSERT INTO equipo_enfermeros (equipo_id, enfermero_id) VALUES (%s, %s)",
                        (equipo_id, enf_id))
        mysql.connection.commit()
        flash('Equipo actualizado correctamente.')
        return redirect(url_for('medico') + '#equipos')

    # GET: mostrar formulario con datos actuales
    cur.execute("SELECT nombre_equipo, medico_id FROM equipos_medicos WHERE id=%s", (equipo_id,))
    equipo = cur.fetchone()

    cur.execute("SELECT id, nombre FROM medicos")
    medicos = cur.fetchall()

    cur.execute("""
SELECT e.id, e.nombre, e.tipo, e.cedula, e.correo, e.telefono, e.foto, e.fecha_ingreso, em.nombre_equipo
FROM enfermeros e
LEFT JOIN equipo_enfermeros ee ON e.id = ee.enfermero_id
LEFT JOIN equipos_medicos em ON ee.equipo_id = em.id
""")
    enfermeros_raw = cur.fetchall()

    enfermeros = []
    for e in enfermeros_raw:
        enfermeros.append({
            'id': e[0],
            'nombre': e[1],
            'tipo': e[2],
            'cedula': e[3],
            'correo': e[4],
            'telefono': e[5],
            'foto': e[6],
            'fecha_ingreso': e[7].strftime('%d/%m/%Y') if e[7] else 'Sin fecha',
            'equipo_nombre': e[8]  # puede ser None si está libre
        })



    cur.execute("SELECT enfermero_id FROM equipo_enfermeros WHERE equipo_id=%s", (equipo_id,))
    enfermeros_asignados = [row[0] for row in cur.fetchall()]

    return render_template('editar_equipo.html',
                           equipo_id=equipo_id,
                           equipo=equipo,
                           medicos=medicos,
                           enfermeros=enfermeros,
                           enfermeros_asignados=enfermeros_asignados)


@app.route('/delete_equipo/<int:equipo_id>')
def delete_equipo(equipo_id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))

    cur = mysql.connection.cursor()

    # 🔁 Desvincular pacientes que usan este equipo
    cur.execute("UPDATE pacientes SET equipo_id = NULL WHERE equipo_id = %s", (equipo_id,))

    # 🔁 Eliminar relaciones con enfermeros
    cur.execute("DELETE FROM equipo_enfermeros WHERE equipo_id = %s", (equipo_id,))

    # ✅ Eliminar el equipo
    cur.execute("DELETE FROM equipos_medicos WHERE id = %s", (equipo_id,))

    mysql.connection.commit()
    flash('Equipo médico eliminado correctamente.')
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
           e.nombre_equipo, p.cedula, p.telefono, p.departamento
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


@app.route('/add_paciente', methods=['GET', 'POST'])
def add_paciente():
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        nombre_completo = request.form['nombre_completo']
        prefijo_cedula = request.form['prefijo_cedula']
        numero_cedula = request.form['numero_cedula']
        cedula = f"{prefijo_cedula}-{numero_cedula}"

        codigo_pais = request.form['codigo_pais']
        numero_telefono = request.form['numero_telefono']
        telefono = f"{codigo_pais} {numero_telefono}"

        edad = request.form['edad']
        fecha_nacimiento = request.form['fecha_nacimiento']
        tipo_sangre = request.form['tipo_sangre']
        motivo_cirugia = request.form['motivo_cirugia']
        departamento = request.form['departamento']

        cur.execute("""
            INSERT INTO pacientes (nombre_completo, cedula, telefono, edad, fecha_nacimiento, tipo_sangre, motivo_cirugia, departamento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (nombre_completo, cedula, telefono, edad, fecha_nacimiento, tipo_sangre, motivo_cirugia, departamento))
        mysql.connection.commit()
        flash('Paciente agregado exitosamente')
        return redirect(url_for('pacientes'))

    return render_template('add_paciente.html')



@app.route('/editar_paciente/<int:id>', methods=['GET', 'POST'])
def editar_paciente(id):
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        # Obtener datos del formulario
        nombre_completo = request.form['nombre_completo']
        prefijo_cedula = request.form['prefijo_cedula']
        numero_cedula = request.form['numero_cedula']
        cedula = f"{prefijo_cedula}-{numero_cedula}"

        codigo_pais = request.form['codigo_pais']
        numero_telefono = request.form['numero_telefono']
        telefono = f"{codigo_pais} {numero_telefono}"

        edad = request.form['edad']
        fecha_nacimiento = request.form['fecha_nacimiento']
        tipo_sangre = request.form['tipo_sangre']
        motivo_cirugia = request.form['motivo_cirugia']
        departamento = request.form['departamento']

        cur.execute("""
            UPDATE pacientes
            SET nombre_completo = %s, cedula = %s, telefono = %s, edad = %s, 
                fecha_nacimiento = %s, tipo_sangre = %s, motivo_cirugia = %s, departamento = %s
            WHERE id = %s
        """, (nombre_completo, cedula, telefono, edad, fecha_nacimiento, tipo_sangre, motivo_cirugia, departamento, id))

        mysql.connection.commit()
        flash('Paciente actualizado exitosamente')
        return redirect(url_for('pacientes'))
    
    # Obtener los datos actuales del paciente
    cur.execute("""
        SELECT id, nombre_completo, edad, fecha_nacimiento, tipo_sangre, motivo_cirugia,
               cedula, telefono, departamento
        FROM pacientes
        WHERE id = %s
    """, (id,))
    paciente = cur.fetchone()
    if not paciente:
        flash('Paciente no encontrado')
        return redirect(url_for('pacientes'))

    # ✅ Dividir cédula y teléfono para el formulario
    cedula_completa = paciente[6]  # Ejemplo: "V-12345678"
    prefijo_cedula, numero_cedula = cedula_completa.split('-')

    telefono_completo = paciente[7]  # Ejemplo: "0414 1234567"
    codigo_pais, numero_telefono = telefono_completo.split(' ', 1)

    return render_template('editar_paciente.html',
                           paciente=paciente,
                           prefijo_cedula=prefijo_cedula,
                           numero_cedula=numero_cedula,
                           codigo_pais=codigo_pais,
                           numero_telefono=numero_telefono)




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
    if 'usuario_autenticado' not in session:
        flash('Debes iniciar sesión primero')
        return redirect(url_for('index'))

    tipo = request.args.get('tipo', '')
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')

    cur = mysql.connection.cursor()
    query = "SELECT * FROM historial WHERE 1=1"
    params = []

    if tipo:
        query += " AND tipo = %s"
        params.append(tipo)
    if fecha_inicio and fecha_fin:
        query += " AND fecha BETWEEN %s AND %s"
        params.extend([fecha_inicio, fecha_fin])

    query += " ORDER BY fecha DESC"
    cur.execute(query, params)
    registros = cur.fetchall()

    return render_template('historial.html', registros=registros, tipo=tipo)


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


def format_date(d):
    """Formato seguro para fechas devueltas por la DB."""
    try:
        return d.strftime('%Y-%m-%d')
    except Exception:
        return str(d)


def format_time(t):
    """Formato seguro para horas/time devueltas por la DB."""
    try:
        return t.strftime('%H:%M')
    except Exception:
        return str(t)

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

# -------Reserva ----------------




@app.route('/reservar_sala', methods=['POST'])
def reservar_sala():
    sala_id = request.form.get('sala_id')
    fecha = request.form.get('fecha')
    hora_inicio = request.form.get('hora_inicio')
    hora_fin = request.form.get('hora_fin')
    paciente_id = request.form.get('paciente_id')
    equipo_id = request.form.get('equipo_id')

    cur = mysql.connection.cursor()

    # Validar solapamiento
    cur.execute("""
        SELECT COUNT(*) FROM reservas
        WHERE sala_id = %s AND fecha = %s
        AND (
            (hora_inicio < %s AND hora_fin > %s) OR
            (hora_inicio >= %s AND hora_inicio < %s) OR
            (hora_fin > %s AND hora_fin <= %s)
        )
    """, (sala_id, fecha, hora_fin, hora_inicio, hora_inicio, hora_fin, hora_inicio, hora_fin))

    conflictos = cur.fetchone()[0]
    if conflictos > 0:
        flash('Ya existe una reserva en ese quirófano en ese horario.')
        return redirect(url_for('salas'))  # ✅ Este return es importante

    # Validar que se haya seleccionado paciente y equipo
    if not paciente_id or not equipo_id:
        flash('Debes seleccionar un paciente y un equipo para la reserva.')
        return redirect(url_for('salas'))

    # Insertar nueva reserva
    cur.execute("""
        INSERT INTO reservas (sala_id, fecha, hora_inicio, hora_fin, paciente_id, equipo_id, estado)
        VALUES (%s, %s, %s, %s, %s, %s, 'pendiente')
    """, (sala_id, fecha, hora_inicio, hora_fin, paciente_id, equipo_id))
    mysql.connection.commit()

    flash('Reserva registrada correctamente.')
    # Mostrar la lista de reservas para que el usuario/admin vea la nueva reserva
    return redirect(url_for('reservas'))

@app.route('/detalle_reserva/<int:id>')
def detalle_reserva(id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.fecha, r.hora_inicio, r.hora_fin,
               p.nombre_completo, e.nombre_equipo
        FROM reservas r
        LEFT JOIN pacientes p ON r.paciente_id = p.id
        LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
        WHERE r.id = %s
    """, (id,))
    r = cur.fetchone()
    if r:
        # Serialización local y defensiva (no depender de helpers externos)
        def safe_date(x):
            try:
                return x.strftime('%Y-%m-%d')
            except Exception:
                return str(x)

        def safe_time(x):
            try:
                return x.strftime('%H:%M')
            except Exception:
                return str(x)

        return jsonify({
            "fecha": safe_date(r[0]),
            "inicio": safe_time(r[1]),
            "fin": safe_time(r[2]),
            "paciente": r[3] or 'Sin paciente',
            "equipo": r[4] or 'Sin equipo'
        })
    return jsonify({"error": "Reserva no encontrada"}), 404


@app.route('/editar_reserva/<int:id>', methods=['GET', 'POST'])
def editar_reserva(id):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        fecha = request.form.get('fecha')
        hora_inicio = request.form.get('hora_inicio')
        hora_fin = request.form.get('hora_fin')
        paciente_id = request.form.get('paciente_id')
        equipo_id = request.form.get('equipo_id')

        cur.execute("""
            UPDATE reservas
            SET fecha=%s, hora_inicio=%s, hora_fin=%s,
                paciente_id=%s, equipo_id=%s
            WHERE id=%s
        """, (fecha, hora_inicio, hora_fin, paciente_id, equipo_id, id))
        mysql.connection.commit()
        flash('Reserva actualizada correctamente.')
        return redirect(url_for('reservas'))

    cur.execute("""
        SELECT r.*, p.nombre_completo, e.nombre_equipo
        FROM reservas r
        LEFT JOIN pacientes p ON r.paciente_id = p.id
        LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
        WHERE r.id = %s
    """, (id,))
    reserva = cur.fetchone()
    return render_template('editar_reserva.html', reserva=reserva)



@app.route('/eliminar_reserva/<int:id>', methods=['POST'])
def eliminar_reserva(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM reservas WHERE id = %s", (id,))
    mysql.connection.commit()
    return '', 204

@app.route('/reservas')
def reservas():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.id, r.sala_id, r.fecha, r.hora_inicio, r.hora_fin,
               r.estado, p.nombre_completo, e.nombre_equipo
        FROM reservas r
        LEFT JOIN pacientes p ON r.paciente_id = p.id
        LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
        WHERE r.estado = 'pendiente'
        ORDER BY r.fecha, r.hora_inicio
    """)
    rows = cur.fetchall()
    # Normalizar tipos (fechas/horas -> strings) para que la plantilla y FullCalendar reciban valores predecibles
    reservas_pendientes = []
    for r in rows:
        fecha = r[2].strftime('%Y-%m-%d') if hasattr(r[2], 'strftime') else str(r[2])
        inicio = r[3].strftime('%H:%M') if hasattr(r[3], 'strftime') else str(r[3])
        fin = r[4].strftime('%H:%M') if hasattr(r[4], 'strftime') else str(r[4])
        reservas_pendientes.append((r[0], r[1], fecha, inicio, fin, r[5], r[6] or '', r[7] or ''))

    return render_template('reservas.html', reservas_pendientes=reservas_pendientes)
@app.route('/fechas_con_reservas')
def fechas_con_reservas():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DISTINCT fecha FROM reservas
        WHERE estado = 'pendiente'
    """)
    fechas = cur.fetchall()
    return jsonify([f[0].strftime('%Y-%m-%d') for f in fechas])


@app.route('/reservas_por_fecha/<fecha>')
def reservas_por_fecha(fecha):
    cur = mysql.connection.cursor()
    cur.execute("""
    SELECT r.id, r.sala_id, r.fecha, r.hora_inicio, r.hora_fin,
           r.estado, p.nombre_completo, e.nombre_equipo
    FROM reservas r
    LEFT JOIN pacientes p ON r.paciente_id = p.id
    LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
    WHERE r.estado = 'pendiente' AND r.fecha = %s
    ORDER BY r.hora_inicio
""", (fecha,))

    reservas = cur.fetchall()

    nombres_quirofanos = ['F','G','H','I','J','A','B','C','D','E']

    def time_to_str(t):
        return t.strftime('%H:%M') if isinstance(t, time) else str(t)

    return jsonify([
        {
            "id": r[0],
            "sala": nombres_quirofanos[r[1] - 6],
            "fecha": str(r[2]),
            "inicio": time_to_str(r[3]),
            "fin": time_to_str(r[4]),
            "estado": r[5],
            "paciente": r[6],
            "equipo": r[7]
        } for r in reservas
    ])



@app.route('/reservas_por_fecha/todas')
def reservas_todas():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.id, r.sala_id, r.fecha, r.hora_inicio, r.hora_fin,
               r.estado, p.nombre_completo, e.nombre_equipo
        FROM reservas r
        LEFT JOIN pacientes p ON r.paciente_id = p.id
        LEFT JOIN equipos_medicos e ON r.equipo_id = e.id
        WHERE r.estado = 'pendiente'
        ORDER BY r.fecha, r.hora_inicio
    """)
    reservas = cur.fetchall()

    nombres_quirofanos = ['F','G','H','I','J','A','B','C','D','E']

    def time_to_str(t):
        return t.strftime('%H:%M') if hasattr(t, 'strftime') else str(t)

    return jsonify([
        {
            "id": r[0],
            "sala": nombres_quirofanos[r[1] - 6],
            "fecha": str(r[2]),
            "inicio": time_to_str(r[3]),
            "fin": time_to_str(r[4]),
            "estado": r[5],
            "paciente": r[6],
            "equipo": r[7]
        } for r in reservas
    ])



@app.route('/eventos_resumen')
def eventos_resumen():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.id, r.fecha, p.nombre_completo
        FROM reservas r
        LEFT JOIN pacientes p ON r.paciente_id = p.id
        WHERE r.estado = 'pendiente'
    """)
    eventos = cur.fetchall()
    return jsonify([
        {
            "id": r[0],
            "title": r[2] or "Sin paciente",
            "start": r[1].strftime('%Y-%m-%d'),
            "backgroundColor": "#0d6efd"
        } for r in eventos
    ])



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=50000)