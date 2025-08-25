from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os

# Si usas carpetas por defecto: templates/ y static/
app = Flask(__name__, template_folder="templates", static_folder="static")

# Llave de sesión (lee de env en prod)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")

# ---------- Rutas de páginas ----------
@app.get("/")
def home():
    # Renderiza el index.html que ya tienes en /templates
    return render_template("index.html")

@app.get("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("home"))
    # Un dashboard mínimo por ahora
    return f"""
    <!doctype html>
    <html lang="es"><meta charset="utf-8">
    <title>Dashboard</title>
    <body style="font-family:system-ui;margin:24px">
      <h1>Bienvenido, {session['user']}</h1>
      <p>Dashboard de ejemplo. Aquí irá el módulo de inventario.</p>
      <form action="/logout" method="post"><button>Salir</button></form>
    </body></html>
    """

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------- API (ejemplo) ----------
@app.post("/api/login")
def api_login():
    """
    Endpoint de ejemplo para autenticar.
    Reemplaza por tu lógica real (BD, JWT, etc).
    Espera JSON: {"usuario": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    user = (data.get("usuario") or "").strip()
    pwd = (data.get("password") or "").strip()

    # DEMO: valida fijo. Cambia esto por tu verificación real.
    if user and pwd and len(pwd) >= 4:
        session["user"] = user
        return jsonify({"ok": True, "redirect": url_for("dashboard")})

    return jsonify({"ok": False, "error": "Credenciales inválidas"}), 400


# ---------- Punto de entrada ----------
if __name__ == "__main__":
    # host="0.0.0.0" si lo vas a exponer en red
    app.run(debug=True)
