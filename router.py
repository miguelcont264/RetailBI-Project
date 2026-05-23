from flask import render_template, request, redirect, url_for, flash
import sqlite3

def configurar_rutas(app, DB_NAME):

    # LOGIN
    @app.route('/')
    def index():
        return render_template('login.html')

    # VALIDAR LOGIN
    @app.route('/login', methods=['POST'])
    def login():

        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM usuarios WHERE username = ? AND password = ?",
            (username, password)
        )

        usuario = cursor.fetchone()

        conn.close()

        if usuario:
            return redirect(url_for('dashboard'))

        else:
            flash("Usuario o contraseña incorrectos")
            return redirect(url_for('index'))

    # DASHBOARD
    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    # HISTORIAL
    @app.route('/historial')
    def historial():
        return render_template('historial_de_cargas.html')

    # CARGAR
    @app.route('/cargar')
    def cargar():
        return render_template('cargar_archivo.html')