from flask import Flask, render_template, request, url_for, redirect, flash, session, jsonify, send_file
from flask_mysqldb import MySQL
import pyotp
import qrcode
import os
from datetime import datetime
import os
from werkzeug.utils import secure_filename

from datetime import time
from io import BytesIO
import pandas as pd

# reportlab para generar PDF sencillo
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import hashlib
import reportlab.pdfbase.pdfdoc as pdfdoc

app = Flask(__name__)

# Compatibility shim: some Python/Windows builds expose hashlib.openssl_md5
# which doesn't accept the keyword argument `usedforsecurity` that
# reportlab sometimes passes. Provide a wrapper that ignores that kwarg
# and falls back to hashlib.md5 to avoid TypeError during PDF generation.
try:
    if hasattr(hashlib, 'openssl_md5'):
        _orig_openssl_md5 = getattr(hashlib, 'openssl_md5')
        def _openssl_md5_compat(data=b'', *args, **kwargs):
            kwargs.pop('usedforsecurity', None)
            try:
                return _orig_openssl_md5(data)
            except Exception:
                return hashlib.md5(data)
        setattr(hashlib, 'openssl_md5', _openssl_md5_compat)
    else:
        # create attribute so reportlab calls succeed
        def _openssl_md5_compat(data=b'', *args, **kwargs):
            kwargs.pop('usedforsecurity', None)
            return hashlib.md5(data)
        setattr(hashlib, 'openssl_md5', _openssl_md5_compat)
except Exception:
    pass

# Additionally patch common ReportLab utils namespace so calls that pass
# usedforsecurity do not fail. Some reportlab versions call md5 via
# reportlab.lib.utils.openssl_md5 or reportlab.lib.utils.md5.
try:
    import reportlab.lib.utils as rl_utils
    def _rl_md5_compat(data=b'', *args, **kwargs):
        kwargs.pop('usedforsecurity', None)
        try:
            return hashlib.md5(data)
        except Exception:
            return hashlib.md5(data)
    # assign compatibility functions into reportlab utils namespace
    setattr(rl_utils, 'openssl_md5', _rl_md5_compat)
    setattr(rl_utils, 'md5', _rl_md5_compat)
except Exception:
    # if reportlab not installed at import time, ignore; we also patch in-place in export
    pass

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
            try:
                registrar_historial('usuario', f'Registro de usuario {nombre_usuario}', usuario=nombre_usuario)
            except Exception:
                pass
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
    try:
        registrar_historial('usuario', f'Usuario {username} aprobado como {rol}', usuario=session.get('nombre_usuario') or 'admin')
    except Exception:
        pass
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
    try:
        registrar_historial('usuario', f'Usuario {username} rechazado y eliminado', usuario=session.get('nombre_usuario') or 'admin')
    except Exception:
        pass
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
        try:
            registrar_historial('usuario', f'Contraseña cambiada para {username}', usuario=session.get('nombre_usuario') or 'admin')
        except Exception:
            pass
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
    try:
        registrar_historial('usuario', f'Rol cambiado a {nuevo_rol} para {username}', usuario=session.get('nombre_usuario') or 'admin')
    except Exception:
        pass
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
    # Registrar en historial: creación de médico
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        medico_id = cursor.lastrowid
        registrar_historial('medico_create', f'Médico creado id={medico_id} nombre={nombre}', usuario=usuario, medico_id=medico_id)
    except Exception:
        pass
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
    # Registrar en historial: actualización de médico
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('medico_update', f'Médico actualizado id={id} nombre={nombre}', usuario=usuario, medico_id=id)
    except Exception:
        pass
    flash('Médico actualizado correctamente.')
    return redirect(url_for('medico'))



# Eliminar médico (desasigna de todos los equipos antes de eliminar)
@app.route('/delete_medico/<int:id>')
def delete_medico(id):
    if session.get('rol') != 'administrador':
        flash('Acceso solo para administradores.')
        return redirect(url_for('dashboard'))
    cur = mysql.connection.cursor()
    # Primero obtener el nombre del médico (para dejar rastro legible en el historial)
    cur.execute("SELECT nombre FROM medicos WHERE id = %s", (id,))
    row = cur.fetchone()
    nombre_medico = row[0] if row else None

    # Desasignar médico de todos los equipos (poniendo medico_id a NULL)
    cur.execute("UPDATE equipos_medicos SET medico_id = NULL WHERE medico_id = %s", (id,))

    # Antes de borrar el médico, limpiar referencias en historial_uso para evitar
    # violaciones de integridad referencial. Conservamos la descripción y añadimos
    # un sufijo que deja constancia del nombre/ID borrado.
    try:
        note = f' (medico eliminado id={id}' + (f' nombre={nombre_medico}' if nombre_medico else '') + ')'
        # Concatenar nota a la descripción y poner medico_id a NULL
        cur.execute(
            """
            UPDATE historial_uso
            SET descripcion = CONCAT(COALESCE(descripcion, ''), %s), medico_id = NULL
            WHERE medico_id = %s
            """,
            (note, id)
        )
    except Exception as e:
        # Si falla actualizar el historial, no detener la eliminación; imprimimos para depuración
        print('Advertencia: no se pudo actualizar historial_uso antes de borrar médico:', e)

    # Ahora sí eliminar al médico
    cur.execute("DELETE FROM medicos WHERE id = %s", (id,))
    mysql.connection.commit()

    # Registrar en historial: eliminación de médico (registramos en historial_uso la acción)
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('medico_delete', f'Médico eliminado id={id} nombre={nombre_medico or "(desconocido)"}', usuario=usuario)
    except Exception:
        pass

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
    # Registrar en historial: creación de enfermero
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        enfermero_id = cur.lastrowid
        registrar_historial('enfermero_create', f'Enfermero creado id={enfermero_id} nombre={nombre}', usuario=usuario)
    except Exception:
        pass
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
    # Registrar en historial: actualización de enfermero
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('enfermero_update', f'Enfermero actualizado id={id} nombre={nombre}', usuario=usuario)
    except Exception:
        pass
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
    # Registrar en historial: eliminación de enfermero
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('enfermero_delete', f'Enfermero eliminado id={id}', usuario=usuario)
    except Exception:
        pass
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
    # Registrar en historial: creación de equipo médico
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('equipo_create', f'Equipo creado id={equipo_id} nombre={nombre_equipo} medico_id={medico_id}', usuario=usuario)
    except Exception:
        pass
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
        # Registrar en historial: edición de equipo
        try:
            usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
            registrar_historial('equipo_update', f'Equipo actualizado id={equipo_id} nombre={nombre_equipo}', usuario=usuario)
        except Exception:
            pass
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
    # Registrar en historial: eliminación de equipo
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        registrar_historial('equipo_delete', f'Equipo eliminado id={equipo_id}', usuario=usuario)
    except Exception:
        pass
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
        # Registrar en historial: creación de paciente
        try:
            usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
            paciente_id = cur.lastrowid
            registrar_historial('paciente_create', f'Paciente creado id={paciente_id} nombre={nombre_completo}', usuario=usuario)
        except Exception:
            pass
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
        # Registrar en historial: actualización de paciente
        try:
            usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
            registrar_historial('paciente_update', f'Paciente actualizado id={id} nombre={nombre_completo}', usuario=usuario)
        except Exception:
            pass
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
        # Obtener nombre para registro (si existe) y eliminar el paciente
        cur.execute("SELECT nombre_completo FROM pacientes WHERE id = %s", (id,))
        row = cur.fetchone()
        nombre_paciente = row[0] if row else None
        cur.execute("DELETE FROM pacientes WHERE id = %s", (id,))
        mysql.connection.commit()
        # Registrar en historial: eliminación de paciente
        try:
            usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
            registrar_historial('paciente_delete', f'Paciente eliminado id={id} nombre={nombre_paciente or "(desconocido)"}', usuario=usuario)
        except Exception:
            pass
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

    # Filtros desde la UI
    tipo = request.args.get('tipo', '')
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')
    q = request.args.get('q', '').strip()
    usuario_filter = request.args.get('usuario', '').strip()

    # Columnas seleccionadas por el usuario (comma-separated)
    # Support multiple 'cols' parameters (checkboxes) or a single comma-separated value
    cols_list = request.args.getlist('cols')
    cols_param = ''
    if cols_list:
        cols_param = ','.join(cols_list)
    else:
        cols_param = request.args.get('cols', '')
    registros, all_cols = fetch_historial(tipo, fecha_inicio, fecha_fin, q=q, usuario_filter=usuario_filter)

    # Determine which columns to show: if user provided a selection, use it; otherwise pick sensible defaults
    if cols_param:
        selected = [c for c in cols_param.split(',') if c in all_cols]
    else:
        # sensible default ordering
        preferred = ['fecha', 'tipo', 'entidad_nombre', 'accion', 'descripcion', 'usuario', 'medico_nombre', 'sala_id', 'duracion']
        selected = [c for c in preferred if c in all_cols]
        # if preferred is empty, show all
        if not selected:
            selected = all_cols

    return render_template('historial.html', registros=registros, tipo=tipo, columns=all_cols, selected_columns=selected, filters={'inicio': fecha_inicio, 'fin': fecha_fin, 'q': q, 'usuario': usuario_filter})


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


def registrar_historial(tipo, descripcion, usuario=None, sala_id=None, medico_id=None, duracion=None):
    """Inserta un registro en la tabla `historial_uso`.
    Nota: la tabla existente en el proyecto tiene columnas (sala_id, medico_id, fecha_uso, duracion, descripcion).
    Para no modificar el esquema, concatenamos tipo/usuario dentro de la descripción.
    """
    try:
        cur = mysql.connection.cursor()
        usuario_str = f" usuario={usuario}" if usuario else ""
        full_desc = f"[{tipo}] {descripcion}{usuario_str}"
        # Ensure duracion is never NULL to satisfy DB NOT NULL constraint
        duracion_val = duracion if duracion is not None else ''
        cur.execute(
            """
            INSERT INTO historial_uso (sala_id, medico_id, fecha_uso, duracion, descripcion)
            VALUES (%s, %s, NOW(), %s, %s)
            """,
            (sala_id, medico_id, duracion_val, full_desc),
        )
        mysql.connection.commit()
    except Exception as e:
        # No detener la aplicación por fallos en el logging; imprimimos para depuración
        print("Error registrando historial:", e)


def _serialize_value(v):
    """Serialize DB values to friendly strings for templates/exports."""
    if v is None:
        return ''
    try:
        # datetime or date or time
        if hasattr(v, 'year') and hasattr(v, 'month') and hasattr(v, 'day'):
            # it's a date or datetime
            if hasattr(v, 'hour'):
                return v.strftime('%Y-%m-%d %H:%M')
            return v.strftime('%Y-%m-%d')
        if hasattr(v, 'hour') and hasattr(v, 'minute'):
            return v.strftime('%H:%M')
    except Exception:
        pass
    try:
        return str(v)
    except Exception:
        return ''


def fetch_historial(tipo='', fecha_inicio='', fecha_fin='', q='', usuario_filter=''):
    """Retorna filas y columnas uniendo `historial` y `historial_uso`.
    Normaliza y enriquece columnas: id, tipo, entidad_id, entidad_nombre, accion, descripcion, usuario, fecha, sala_id, medico_id, medico_nombre, duracion
    Acepta filtros: tipo, fecha_inicio, fecha_fin, q (texto búsqueda), usuario_filter
    Devuelve: (rows_as_list_of_dicts, cols_list)
    """
    cur = mysql.connection.cursor()
    # SELECT para historial general con joins a tablas para obtener nombres
    sel1 = (
        "SELECT h.id, h.tipo, h.entidad_id, "
        "COALESCE(p.nombre_completo, m.nombre, en.nombre, CONCAT('Sala ', h.entidad_id)) AS entidad_nombre, "
        "h.accion, h.descripcion, h.usuario, h.fecha, NULL AS sala_id, NULL AS medico_id, NULL AS medico_nombre, NULL AS duracion "
        "FROM historial h "
        "LEFT JOIN pacientes p ON h.tipo='paciente' AND h.entidad_id = p.id "
        "LEFT JOIN medicos m ON h.tipo='medico' AND h.entidad_id = m.id "
        "LEFT JOIN enfermeros en ON h.tipo='enfermero' AND h.entidad_id = en.id "
        "WHERE 1=1"
    )
    params1 = []

    # SELECT para historial_uso con joins a medicos y salas
    sel2 = (
        "SELECT u.id, 'uso' AS tipo, u.sala_id AS entidad_id, "
        "COALESCE(CONCAT('Sala ', u.sala_id), s.id) AS entidad_nombre, "
        "NULL AS accion, u.descripcion, '' AS usuario, u.fecha_uso AS fecha, u.sala_id, u.medico_id, COALESCE(m.nombre, '') AS medico_nombre, u.duracion "
        "FROM historial_uso u "
        "LEFT JOIN medicos m ON u.medico_id = m.id "
        "LEFT JOIN salas_quirofano s ON u.sala_id = s.id "
        "WHERE 1=1"
    )
    params2 = []

    # tipo filter
    if tipo:
        if tipo == 'uso' or tipo.lower() == 'uso':
            # Only use historial_uso
            sel1 += " AND 0=1"
        else:
            sel1 += " AND h.tipo = %s"
            params1.append(tipo)
            sel2 += " AND 0=1"

    # fecha range
    if fecha_inicio and fecha_fin:
        sel1 += " AND (h.fecha BETWEEN %s AND %s)"
        sel2 += " AND (u.fecha_uso BETWEEN %s AND %s)"
        params1.extend([fecha_inicio + ' 00:00:00', fecha_fin + ' 23:59:59'])
        params2.extend([fecha_inicio + ' 00:00:00', fecha_fin + ' 23:59:59'])

    # texto búsqueda q (en descripcion/accion/usuario)
    if q:
        like = f"%{q}%"
        sel1 += " AND (h.descripcion LIKE %s OR h.accion LIKE %s OR h.usuario LIKE %s)"
        params1.extend([like, like, like])
        sel2 += " AND (u.descripcion LIKE %s)"
        params2.append(like)

    # usuario filter exact or partial
    if usuario_filter:
        likeu = f"%{usuario_filter}%"
        sel1 += " AND (h.usuario LIKE %s)"
        params1.append(likeu)

    # Construir query final
    query = f"({sel1}) UNION ALL ({sel2}) ORDER BY fecha DESC"
    params = params1 + params2

    cur.execute(query, params)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []

    # Convertir a lista de dicts con serialización
    rows_serial = []
    for row in rows:
        item = {}
        for i, c in enumerate(cols):
            item[c] = _serialize_value(row[i])
        rows_serial.append(item)

    return rows_serial, cols


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

    # Registrar en historial de uso (guardamos tipo/usuario dentro de la descripción para no cambiar esquema)
    usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
    try:
        registrar_historial('reserva', f'Reserva creada sala={sala_id} fecha={fecha} {hora_inicio}-{hora_fin} paciente={paciente_id} equipo={equipo_id}', usuario=usuario, sala_id=sala_id, medico_id=equipo_id)
    except Exception:
        # No interrumpir por errores de logging
        pass

    flash('Reserva registrada correctamente.')
    # Mostrar la lista de reservas para que el usuario/admin vea la nueva reserva
    return redirect(url_for('reservas'))

@app.route('/detalle_reserva/<int:id>')
def detalle_reserva(id):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT r.fecha, r.hora_inicio, r.hora_fin,
               p.id AS paciente_id, p.nombre_completo, e.id AS equipo_id, e.nombre_equipo
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

        # r layout: (fecha, hora_inicio, hora_fin, paciente_id, nombre_completo, equipo_id, nombre_equipo)
        return jsonify({
            "fecha": safe_date(r[0]),
            "inicio": safe_time(r[1]),
            "fin": safe_time(r[2]),
            "paciente_id": r[3],
            "paciente": r[4] or 'Sin paciente',
            "equipo_id": r[5],
            "equipo": r[6] or 'Sin equipo'
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

        # Si alguno de los campos paciente_id o equipo_id no viene en el formulario
        # preservamos el valor existente en la BBDD para evitar sobrescribir con NULL/''.
        cur.execute("SELECT paciente_id, equipo_id FROM reservas WHERE id=%s", (id,))
        existing = cur.fetchone()
        if existing:
            existing_paciente, existing_equipo = existing[0], existing[1]
            if not paciente_id and existing_paciente is not None:
                paciente_id = existing_paciente
            if not equipo_id and existing_equipo is not None:
                equipo_id = existing_equipo

        cur.execute("""
            UPDATE reservas
            SET fecha=%s, hora_inicio=%s, hora_fin=%s,
                paciente_id=%s, equipo_id=%s
            WHERE id=%s
        """, (fecha, hora_inicio, hora_fin, paciente_id, equipo_id, id))
        mysql.connection.commit()
        # Registrar en historial: actualización de reserva
        try:
            usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
            sala_form = request.form.get('sala_id')
            sala_reg = sala_form if sala_form else 'desconocida'
            registrar_historial('reserva_update', f'Reserva actualizada id={id} sala={sala_reg} fecha={fecha} {hora_inicio}-{hora_fin} paciente={paciente_id} equipo={equipo_id}', usuario=usuario, sala_id=(sala_form if sala_form else None))
        except Exception:
            pass
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


# Compatibilidad: aceptar POST desde formularios antiguos que apuntan a /actualizar_reserva
@app.route('/actualizar_reserva', methods=['POST'])
def actualizar_reserva():
    """Compat layer: acepta id en form (name='id') y actualiza la reserva.
    Esto permite que formularios antiguos que postearon a /actualizar_reserva sigan funcionando.
    """
    cur = mysql.connection.cursor()
    reserva_id = request.form.get('id')
    if not reserva_id:
        flash('Id de reserva faltante')
        return redirect(url_for('reservas'))

    fecha = request.form.get('fecha')
    hora_inicio = request.form.get('hora_inicio')
    hora_fin = request.form.get('hora_fin')
    paciente_id = request.form.get('paciente_id')
    equipo_id = request.form.get('equipo_id')

    # Defensive: preserve existing paciente_id/equipo_id when form omits them
    cur.execute("SELECT paciente_id, equipo_id FROM reservas WHERE id=%s", (reserva_id,))
    existing = cur.fetchone()
    if existing:
        existing_paciente, existing_equipo = existing[0], existing[1]
        if not paciente_id and existing_paciente is not None:
            paciente_id = existing_paciente
        if not equipo_id and existing_equipo is not None:
            equipo_id = existing_equipo

    cur.execute("""
        UPDATE reservas
        SET fecha=%s, hora_inicio=%s, hora_fin=%s, paciente_id=%s, equipo_id=%s
        WHERE id=%s
    """, (fecha, hora_inicio, hora_fin, paciente_id, equipo_id, reserva_id))
    mysql.connection.commit()

    # Registrar en historial: actualización de reserva
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        sala_form = request.form.get('sala_id')
        sala_reg = sala_form if sala_form else 'desconocida'
        registrar_historial('reserva_update', f'Reserva actualizada id={reserva_id} sala={sala_reg} fecha={fecha} {hora_inicio}-{hora_fin} paciente={paciente_id} equipo={equipo_id}', usuario=usuario, sala_id=(sala_form if sala_form else None))
    except Exception:
        pass

    flash('Reserva actualizada correctamente.')
    return redirect(url_for('reservas'))



@app.route('/eliminar_reserva/<int:id>', methods=['POST'])
def eliminar_reserva(id):
    cur = mysql.connection.cursor()
    # Obtener datos antes de eliminar para registrar en historial
    cur.execute("SELECT sala_id, fecha, hora_inicio, hora_fin, paciente_id, equipo_id FROM reservas WHERE id = %s", (id,))
    row = cur.fetchone()
    cur.execute("DELETE FROM reservas WHERE id = %s", (id,))
    mysql.connection.commit()
    try:
        usuario = session.get('nombre_usuario') or session.get('usuario_autenticado') or session.get('usuario') or 'anon'
        if row:
            sala_id, fecha, hora_inicio, hora_fin, paciente_id, equipo_id = row
            registrar_historial('reserva_delete', f'Reserva eliminada id={id} sala={sala_id} fecha={fecha} {hora_inicio}-{hora_fin} paciente={paciente_id} equipo={equipo_id}', usuario=usuario, sala_id=sala_id)
        else:
            registrar_historial('reserva_delete', f'Reserva eliminada id={id}', usuario=usuario)
    except Exception:
        pass
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



@app.route('/historial/print')
def historial_print():
    if 'usuario_autenticado' not in session:
        flash('Acceso requerido')
        return redirect(url_for('index'))
    tipo = request.args.get('tipo', '')
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')
    q = request.args.get('q', '')
    usuario_filter = request.args.get('usuario', '')
    registros, cols = fetch_historial(tipo, fecha_inicio, fecha_fin, q=q, usuario_filter=usuario_filter)
    # sensible default columns for print
    preferred = ['fecha', 'tipo', 'entidad_nombre', 'accion', 'descripcion', 'usuario', 'medico_nombre', 'sala_id', 'duracion']
    selected = [c for c in preferred if c in cols] or cols
    return render_template('historial.html', registros=registros, tipo=tipo, printable=True, columns=cols, selected_columns=selected, filters={'inicio': fecha_inicio, 'fin': fecha_fin, 'q': q, 'usuario': usuario_filter})


@app.route('/historial/export/excel')
def historial_export_excel():
    if 'usuario_autenticado' not in session:
        flash('Acceso requerido')
        return redirect(url_for('index'))
    # Export the same data shown in /historial (now unified) so CSV/Excel matches the UI
    tipo = request.args.get('tipo', '')
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')
    rows, cols = fetch_historial(tipo, fecha_inicio, fecha_fin)
    try:
        # rows == list of dicts; let pandas infer columns when possible
        df = pd.DataFrame(rows) if rows else None
        # reindex columns to keep consistent order if cols provided
        if df is not None and cols:
            df = df.reindex(columns=cols)
    except Exception:
        df = None
    output = BytesIO()
    if df is not None:
        try:
            df.to_excel(output, index=False, engine='openpyxl')
        except Exception:
            output.write(df.to_csv(index=False).encode('utf-8'))
    else:
        # Fallback simple CSV if pandas isn't available; rows are dicts
        header = cols if cols else (list(rows[0].keys()) if rows else [])
        output.write((','.join(header) + '\n').encode('utf-8'))
        for r in rows:
            line = ','.join([str(r.get(c, '')) for c in header]) + '\n'
            output.write(line.encode('utf-8'))
    output.seek(0)
    registrar_historial('export', 'Export historial a excel', usuario=session.get('nombre_usuario') or 'anon')
    return send_file(output, as_attachment=True, download_name='historial.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/historial/export/pdf')
def historial_export_pdf():
    if 'usuario_autenticado' not in session:
        flash('Acceso requerido')
        return redirect(url_for('index'))
    # Export the same data shown in /historial (now unified) so PDF matches the UI
    tipo = request.args.get('tipo', '')
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')
    rows, cols = fetch_historial(tipo, fecha_inicio, fecha_fin)

    # Monkeypatch for reportlab/OpenSSL md5 signature incompatibility on some Windows/Python combinations
    # reportlab.pdfbase.pdfdoc.md5 may call openssl_md5 with keyword arg 'usedforsecurity' which some builds don't accept.
    try:
        def _md5_compat(*args, **kwargs):
            # remove unsupported kw and call hashlib.md5
            kwargs.pop('usedforsecurity', None)
            return hashlib.md5(*args, **kwargs)
        pdfdoc.md5 = _md5_compat
    except Exception:
        pass

    buffer = BytesIO()
    # Use slightly larger top margin to place header
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=72, bottomMargin=36)

    styles = getSampleStyleSheet()
    # APA-like title style (Times New Roman-like)
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontName='Times-Roman', fontSize=14, leading=18, alignment=1)
    normal = ParagraphStyle('NormalSmall', parent=styles['Normal'], fontName='Times-Roman', fontSize=9, leading=12)
    header_small = ParagraphStyle('HeaderSmall', parent=styles['Normal'], fontName='Times-Roman', fontSize=10, leading=12, alignment=1)

    elements = []

    # Header with logo and title
    try:
        logo_path = os.path.join(app.root_path, 'static', 'logo', 'huc.png')
        if os.path.exists(logo_path):
            img = Image(logo_path, width=60, height=60)
        else:
            img = None
    except Exception:
        img = None

    title_text = 'Historial del Sistema - HUC'
    subtitle = f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if tipo:
        subtitle += f" | Tipo: {tipo}"
    if fecha_inicio and fecha_fin:
        subtitle += f" | Rango: {fecha_inicio} — {fecha_fin}"

    # Build header table: logo left, title center
    header_cells = []
    if img:
        header_cells.append(img)
    else:
        header_cells.append(Paragraph('<b>HUC</b>', header_small))
    header_cells.append(Paragraph(f"<b>{title_text}</b><br/><i>{subtitle}</i>", title_style))

    header_table = Table([header_cells], colWidths=[70, doc.width - 70])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 12))

    # Prepare table data: header row then data rows
    header_row = [c.replace('_', ' ').title() for c in cols]

    # Convert each cell into a Paragraph to allow wrapping
    data = [header_row]
    for r in rows:
        row_cells = []
        for c in cols:
            text = r.get(c, '') if isinstance(r, dict) else (r[cols.index(c)] if cols and len(r) > cols.index(c) else '')
            # Ensure text is string
            text = '' if text is None else str(text)
            row_cells.append(Paragraph(text, normal))
        data.append(row_cells)

    # Column widths: distribute evenly but give more space to description if present
    total_width = letter[0] - doc.leftMargin - doc.rightMargin
    col_count = max(1, len(cols))
    # if 'descripcion' present give it 30% width
    if 'descripcion' in cols:
        desc_idx = cols.index('descripcion')
        desc_w = total_width * 0.30
        other_w = (total_width - desc_w) / (col_count - 1) if col_count > 1 else total_width
        colWidths = [other_w if i != desc_idx else desc_w for i in range(col_count)]
    else:
        colWidths = [total_width / col_count for _ in range(col_count)]

    table = Table(data, repeatRows=1, colWidths=colWidths)
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2F4F4F')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Times-Roman'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ])
    table.setStyle(style)

    elements.append(table)

    # Footer with page numbers
    def _footer(canvas, doc_):
        canvas.saveState()
        footer_text = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} — Página {canvas.getPageNumber()}"
        canvas.setFont('Times-Roman', 9)
        canvas.drawCentredString(letter[0] / 2.0, 20, footer_text)
        canvas.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    registrar_historial('export', 'Export historial a pdf', usuario=session.get('nombre_usuario') or 'anon')
    return send_file(buffer, as_attachment=True, download_name='historial.pdf', mimetype='application/pdf')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=50000)