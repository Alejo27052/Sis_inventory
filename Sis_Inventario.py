# Sis_Inventario.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

# =============================================================================
# FLASK
# =============================================================================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")  # cambia en prod

# =============================================================================
# CONEXIÓN A MARIADB (tus valores)
# =============================================================================
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASS = "Gabriel1402"          # ⚠️ evita subir este archivo con esta clave a GitHub
DB_NAME = "Inventario_Super_Unico"

DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

engine = create_engine(DATABASE_URI, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# =============================================================================
# PÁGINAS
# =============================================================================
@app.get("/")
def home():
    # si ya inició sesión, que el "inicio" sea el dashboard
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")  # login

@app.get("/crear-cuenta")
def crear_cuenta():
    return render_template("crear_cuenta.html")

@app.get("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html")

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# --- PÁGINAS ---
@app.get("/proveedores")
def proveedores_listado():
    if "user" not in session:
        return redirect(url_for("home"))
    # Renderiza tu Listado + Form embebido
    return render_template("Listado_pro.html")

@app.get("/proveedores/nuevo")
def proveedores_nuevo():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("Crear_Proveedor.html")

@app.get("/productos/ingreso")
def productos_ingreso():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("ingreso_productos.html")


# =============================================================================
# AUTENTICACIÓN
# =============================================================================
@app.post("/api/login")
def api_login():
    """
    Login por Email o por Nombre contra la tabla `Usuario`
    (columnas: ID_Usuario, Nombre, Rol, Email, Contraseña, Estado).
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("usuario") or "").strip()
    password = (data.get("password") or "")

    if not username or not password:
        return jsonify({"ok": False, "error": "Faltan credenciales"}), 400

    sql = text("""
        SELECT `Nombre`, `Email`, `Contraseña`, `Estado`
        FROM `Usuario`
        WHERE `Email` = :u OR `Nombre` = :u
        LIMIT 1
    """)

    with engine.connect() as conn:
        row = conn.execute(sql, {"u": username.lower()}).mappings().first()

    if row and int(row["Estado"] or 0) == 1 and check_password_hash(row["Contraseña"], password):
        session["user"] = row["Nombre"] or row["Email"]
        return jsonify({"ok": True, "redirect": url_for("dashboard")})

    return jsonify({"ok": False, "error": "Credenciales inválidas o usuario inactivo"}), 400


@app.post("/api/register")
def api_register():
    """
    Registra usuario en `Usuario`.
    Espera JSON: {Nombre, Rol, Email, Contrasena, Estado(0|1)}.
    Guarda hash en `Contraseña`.
    """
    data = request.get_json(silent=True) or {}
    nombre  = (data.get("Nombre") or "").strip()
    rol     = (data.get("Rol") or "").strip()
    email   = (data.get("Email") or "").strip().lower()
    pwd_raw = (data.get("Contrasena") or "")
    estado  = 1 if str(data.get("Estado") or "0") in ("1", "true", "True") else 0

    if not nombre or not rol or not email or not pwd_raw:
        return jsonify({"ok": False, "error": "Faltan datos obligatorios"}), 400
    if len(nombre) > 50 or len(rol) > 10 or len(email) > 100 or len(pwd_raw) > 255:
        return jsonify({"ok": False, "error": "Longitud de campos excedida"}), 400

    pwd_hash = generate_password_hash(pwd_raw)

    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM `Usuario` WHERE `Email` = :email LIMIT 1"),
            {"email": email}
        ).first()
        if exists:
            return jsonify({"ok": False, "error": "El email ya está registrado"}), 409

        conn.execute(
            text("""
                INSERT INTO `Usuario`
                    (`Nombre`, `Rol`, `Email`, `Contraseña`, `Estado`)
                VALUES
                    (:nombre, :rol, :email, :pwd, :estado)
            """),
            {"nombre": nombre, "rol": rol, "email": email, "pwd": pwd_hash, "estado": estado}
        )

    return jsonify({"ok": True, "message": "Usuario creado correctamente"})

# =============================================================================
# APIS DEL DASHBOARD (usa tus tablas: Producto, Pedido, Detalle_Pedido)
# =============================================================================
@app.get("/api/dashboard/summary")
def api_dashboard_summary():
    """
    KPIs:
      - productos_en_stock: Producto.Stock > 0 (Estado != 'Inactivo')
      - alerta_stock_bajo: Stock <= min_stock (query param ?min=5)
      - sin_stock: Stock == 0
      - valor_total_stock: SUM(Stock * Precio_Unitario)
      - ventas_mes: SUM(Pedido.Total) del mes actual (Estados válidos)
    """
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    min_stock = int(request.args.get("min", 5))

    sql_prod_stock = text("""
        SELECT COUNT(*) AS n
        FROM `Producto`
        WHERE COALESCE(`Stock`,0) > 0
          AND (COALESCE(`Estado`,'Activo') <> 'Inactivo')
    """)
    sql_stock_bajo = text("""
        SELECT COUNT(*) AS n
        FROM `Producto`
        WHERE COALESCE(`Stock`,0) <= :min_stock
          AND (COALESCE(`Estado`,'Activo') <> 'Inactivo')
    """)
    sql_sin_stock = text("""
        SELECT COUNT(*) AS n
        FROM `Producto`
        WHERE COALESCE(`Stock`,0) = 0
          AND (COALESCE(`Estado`,'Activo') <> 'Inactivo')
    """)
    sql_valor_inv = text("""
        SELECT COALESCE(SUM(COALESCE(`Stock`,0) * COALESCE(`Precio_Unitario`,0)), 0) AS total
        FROM `Producto`
        WHERE (COALESCE(`Estado`,'Activo') <> 'Inactivo')
    """)
    sql_ventas_mes = text("""
        SELECT COALESCE(SUM(`Total`),0) AS total
        FROM `Pedido`
        WHERE YEAR(`Fecha`) = YEAR(CURDATE())
          AND MONTH(`Fecha`) = MONTH(CURDATE())
          AND (COALESCE(`Estado`,'Confirmado') NOT IN ('Anulado','Cancelado'))
    """)

    with engine.connect() as conn:
        productos_en_stock = conn.execute(sql_prod_stock).scalar() or 0
        alerta_stock_bajo  = conn.execute(sql_stock_bajo, {"min_stock": min_stock}).scalar() or 0
        sin_stock          = conn.execute(sql_sin_stock).scalar() or 0
        valor_total_stock  = float(conn.execute(sql_valor_inv).scalar() or 0)
        ventas_mes         = float(conn.execute(sql_ventas_mes).scalar() or 0)

    return jsonify({
        "ok": True,
        "productos_en_stock": int(productos_en_stock),
        "alerta_stock_bajo": int(alerta_stock_bajo),
        "sin_stock": int(sin_stock),
        "valor_total_stock": valor_total_stock,
        "ventas_mes": ventas_mes
    })


@app.get("/api/dashboard/top-movimientos")
def api_dashboard_top_movimientos():
    """
    Últimos 20 movimientos (por fecha) desde Detalle_Pedido + Pedido + Producto.
    """
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    sql = text("""
        SELECT
            dp.`ID_Detalle`       AS id_detalle,
            p.`Fecha`             AS fecha,
            pr.`Nombre`           AS producto,
            pr.`SKU`              AS sku,
            pr.`Stock`            AS stock_actual,
            dp.`Cantidad`         AS cantidad,
            dp.`Precio_Unitario`  AS precio_unit,
            dp.`Subtotal`         AS subtotal
        FROM `Detalle_Pedido` dp
        JOIN `Pedido`   p  ON p.`ID_Pedido`    = dp.`ID_Pedido`
        JOIN `Producto` pr ON pr.`ID_Producto` = dp.`ID_Producto`
        ORDER BY p.`Fecha` DESC, dp.`ID_Detalle` DESC
        LIMIT 20
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()

    items = []
    for r in rows:
        fecha_str = r["fecha"].strftime("%Y-%m-%d") if hasattr(r["fecha"], "strftime") else str(r["fecha"])
        items.append({
            "id": r["id_detalle"],
            "producto": r["producto"],
            "sku": r["sku"] or "",
            "stock": r["stock_actual"],
            "cantidad": r["cantidad"],
            "precio_unit": float(r["precio_unit"] or 0),
            "subtotal": float(r["subtotal"] or 0),
            "fecha": fecha_str,
            # para la columna "categoria" del dashboard usamos el SKU (o deja '—')
            "categoria": r["sku"] or "—"
        })

    return jsonify({"ok": True, "items": items})

# ======= PROVEEDORES: APIs =======
# Buscar por nombre o NIT
@app.get("/api/proveedores")
def api_proveedores_search():
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    q = (request.args.get("q") or "").strip()
    sql = text("""
        SELECT
          `ID_Proveedor`, `NIT`, `Nombre`, COALESCE(`Telefono`,'') AS Telefono,
          COALESCE(`Direccion`,'') AS Direccion,
          COALESCE(`Email`,'') AS Email,
          COALESCE(`Estado`,1)  AS Estado
        FROM `Proveedor`
        WHERE (:q = '')
           OR (`Nombre` LIKE CONCAT('%', :q, '%'))
           OR (`NIT`    LIKE CONCAT('%', :q, '%'))
        ORDER BY `Nombre` ASC
        LIMIT 50
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"q": q}).mappings().all()

    return jsonify({"ok": True, "items": [dict(r) for r in rows]})


# Traer un proveedor por NIT
@app.get("/api/proveedores/<nit>")
def api_proveedores_get(nit):
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    sql = text("""
        SELECT
          `ID_Proveedor`, `NIT`, `Nombre`, COALESCE(`Telefono`,'') AS Telefono,
          COALESCE(`Direccion`,'') AS Direccion,
          COALESCE(`Email`,'') AS Email,
          COALESCE(`Estado`,1)  AS Estado
        FROM `Proveedor`
        WHERE `NIT` = :nit
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"nit": nit}).mappings().first()

    if not row:
        return jsonify({"ok": True, "found": False})
    return jsonify({"ok": True, "found": True, "item": dict(row)})


# Crear proveedor (si no existe NIT)
@app.post("/api/proveedores")
def api_proveedores_create():
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    data = request.get_json(silent=True) or {}
    nit   = (data.get("nit") or "").strip()
    nombre= (data.get("nombre") or "").strip()
    tel   = (data.get("telefono") or "").strip()
    dir_  = (data.get("direccion") or "").strip()
    email = (data.get("email") or "").strip().lower()
    estado= 1 if str(data.get("estado") or "1") in ("1","true","True") else 0

    if not nit or not nombre:
        return jsonify({"ok": False, "error": "NIT y Nombre son obligatorios"}), 400
    if len(nit) > 15 or len(nombre) > 50 or len(tel) > 10 or len(dir_) > 30 or len(email) > 100:
        return jsonify({"ok": False, "error": "Longitud de campos excedida"}), 400

    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM `Proveedor` WHERE `NIT` = :nit LIMIT 1"), {"nit": nit}).first()
        if exists:
            return jsonify({"ok": False, "error": "Ya existe un proveedor con ese NIT"}), 409

        conn.execute(text("""
            INSERT INTO `Proveedor`
                (`NIT`, `Nombre`, `Telefono`, `Direccion`, `Email`, `Estado`)
            VALUES
                (:nit, :nombre, :tel, :dir_, :email, :estado)
        """), {"nit": nit, "nombre": nombre, "tel": tel, "dir_": dir_, "email": email, "estado": estado})

    return jsonify({"ok": True, "message": "Proveedor creado"})


# Actualizar proveedor existente por NIT
@app.put("/api/proveedores/<nit>")
def api_proveedores_update(nit):
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    data = request.get_json(silent=True) or {}
    nombre= (data.get("nombre") or "").strip()
    tel   = (data.get("telefono") or "").strip()
    dir_  = (data.get("direccion") or "").strip()
    email = (data.get("email") or "").strip().lower()
    estado= data.get("estado")
    if estado is None:
        estado = 1
    else:
        estado = 1 if str(estado) in ("1","true","True") else 0

    if len(nit) > 15 or len(nombre) > 50 or len(tel) > 10 or len(dir_) > 30 or len(email) > 100:
        return jsonify({"ok": False, "error": "Longitud de campos excedida"}), 400

    with engine.begin() as conn:
        row = conn.execute(text("SELECT `ID_Proveedor` FROM `Proveedor` WHERE `NIT` = :nit LIMIT 1"), {"nit": nit}).first()
        if not row:
            return jsonify({"ok": False, "error": "Proveedor no existe"}), 404

        conn.execute(text("""
            UPDATE `Proveedor`
            SET `Nombre`=:nombre, `Telefono`=:tel, `Direccion`=:dir_,
                `Email`=:email, `Estado`=:estado
            WHERE `NIT` = :nit
        """), {"nombre": nombre, "tel": tel, "dir_": dir_, "email": email, "estado": estado, "nit": nit})

    return jsonify({"ok": True, "message": "Proveedor actualizado"})

# ================== PRODUCTOS: APIs ==================
from sqlalchemy import text

# Buscar por nombre o SKU (lista)
@app.get("/api/productos")
def api_productos_search():
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    q = (request.args.get("q") or "").strip()
    sql = text("""
        SELECT
          `ID_Producto`,
          `SKU`,
          `Nombre`,
          COALESCE(`Descripción`, '')       AS Descripcion,
          COALESCE(`Precio_Unitario`, 0)    AS Precio_Unitario,
          COALESCE(`Stock`, 0)              AS Stock,
          COALESCE(`Estado`, 'Activo')      AS Estado,
          `ID_Categoria`
        FROM `Producto`
        WHERE (:q = '')
           OR (`Nombre` LIKE CONCAT('%', :q, '%'))
           OR (`SKU`    LIKE CONCAT('%', :q, '%'))
        ORDER BY `Nombre` ASC
        LIMIT 50
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"q": q}).mappings().all()

    return jsonify({"ok": True, "items": [dict(r) for r in rows]})


# Traer un producto por SKU
@app.get("/api/productos/<sku>")
def api_productos_get(sku):
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    sql = text("""
        SELECT
          `ID_Producto`,
          `SKU`,
          `Nombre`,
          COALESCE(`Descripción`, '')       AS Descripcion,
          COALESCE(`Precio_Unitario`, 0)    AS Precio_Unitario,
          COALESCE(`Stock`, 0)              AS Stock,
          COALESCE(`Estado`, 'Activo')      AS Estado,
          `ID_Categoria`
        FROM `Producto`
        WHERE `SKU` = :sku
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"sku": sku}).mappings().first()

    if not row:
        return jsonify({"ok": True, "found": False})
    return jsonify({"ok": True, "found": True, "item": dict(row)})


# Crear producto (si SKU no existe)
@app.post("/api/productos")
def api_productos_create():
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    d = request.get_json(silent=True) or {}
    sku     = (d.get("sku") or "").strip()
    nombre  = (d.get("nombre") or "").strip()
    desc    = (d.get("descripcion") or "").strip()  # lo guardamos en `Descripción`
    precio  = d.get("precio_unitario")
    stock   = d.get("stock")
    estado  = (d.get("estado") or "Activo").strip() or "Activo"
    idcat   = d.get("id_categoria")

    # saneo y validaciones
    try:
        precio = float(precio or 0)
        stock  = int(stock or 0)
        idcat  = int(idcat) if idcat not in (None, "", "null") else None
    except ValueError:
        return jsonify({"ok": False, "error": "Tipos inválidos en precio/stock/id_categoria"}), 400

    if not sku or not nombre:
        return jsonify({"ok": False, "error": "SKU y Nombre son obligatorios"}), 400
    if len(nombre) > 20 or len(sku) > 30 or len(desc) > 255 or len(estado) > 10:
        return jsonify({"ok": False, "error": "Longitud de campos excedida"}), 400

    try:
        with engine.begin() as conn:
            ex = conn.execute(text("SELECT 1 FROM `Producto` WHERE `SKU`=:sku LIMIT 1"), {"sku": sku}).first()
            if ex:
                return jsonify({"ok": False, "error": "Ya existe un producto con ese SKU"}), 409

            conn.execute(text("""
                INSERT INTO `Producto`
                    (`Nombre`, `SKU`, `Descripción`, `Precio_Unitario`, `Stock`, `Estado`, `ID_Categoria`)
                VALUES
                    (:nombre, :sku, :desc, :precio, :stock, :estado, :idcat)
            """), {
                "nombre": nombre, "sku": sku, "desc": desc,
                "precio": precio, "stock": stock, "estado": estado, "idcat": idcat
            })
        return jsonify({"ok": True, "message": "Producto creado"})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": f"Error en servidor: {type(e).__name__}"}), 500


# Actualizar producto por SKU (si existe)
@app.put("/api/productos/<sku>")
def api_productos_update(sku):
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    d = request.get_json(silent=True) or {}
    nombre  = (d.get("nombre") or "").strip()
    desc    = (d.get("descripcion") or "").strip()
    precio  = d.get("precio_unitario")
    stock   = d.get("stock")
    estado  = (d.get("estado") or "Activo").strip() or "Activo"
    idcat   = d.get("id_categoria")

    try:
        precio = float(precio or 0)
        stock  = int(stock or 0)
        idcat  = int(idcat) if idcat not in (None, "", "null") else None
    except ValueError:
        return jsonify({"ok": False, "error": "Tipos inválidos en precio/stock/id_categoria"}), 400

    if len(nombre) > 20 or len(desc) > 255 or len(estado) > 10:
        return jsonify({"ok": False, "error": "Longitud de campos excedida"}), 400

    try:
        with engine.begin() as conn:
            ex = conn.execute(text("SELECT 1 FROM `Producto` WHERE `SKU`=:sku LIMIT 1"), {"sku": sku}).first()
            if not ex:
                return jsonify({"ok": False, "error": "No existe un producto con ese SKU"}), 404

            conn.execute(text("""
                UPDATE `Producto`
                SET `Nombre`=:nombre,
                    `Descripción`=:desc,
                    `Precio_Unitario`=:precio,
                    `Stock`=:stock,
                    `Estado`=:estado,
                    `ID_Categoria`=:idcat
                WHERE `SKU`=:sku
            """), {
                "nombre": nombre, "desc": desc, "precio": precio,
                "stock": stock, "estado": estado, "idcat": idcat, "sku": sku
            })
        return jsonify({"ok": True, "message": "Producto actualizado"})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": f"Error en servidor: {type(e).__name__}"}), 500
    
@app.get("/api/proveedores/select")
def api_proveedores_select():
    # Debe haber sesión iniciada
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    try:
        sql = text("""
            SELECT
              `ID_Proveedor`,
              `Nombre`,
              `NIT`
            FROM `Proveedor`
            WHERE COALESCE(`Estado`, 1) = 1
            ORDER BY `Nombre` ASC
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
        return jsonify({"ok": True, "items": [dict(r) for r in rows]})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": f"DB error: {type(e).__name__}"}), 500

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    # host="0.0.0.0" si quieres exponerlo en la red local
    app.run(debug=True)
