from flask import Blueprint, render_template, request, redirect, url_for, flash
import math
from datetime import datetime, timedelta
from persistence import cargar_datos, guardar_datos, ARCHIVO_GASTOS, ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO

gastos_bp = Blueprint('gastos', __name__, url_prefix='/gastos')

CONCEPTO_MAX_LONGITUD = 100
NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _validar_campos(concepto, categoria, monto_texto, fecha_texto, categorias):
    """Aplica las reglas de negocio 6-11 y devuelve (error, categoria_obj, monto, fecha_texto)."""
    if not concepto:
        return "El concepto del gasto es obligatorio.", None, None, None

    if len(concepto) > CONCEPTO_MAX_LONGITUD:
        return f"El concepto no puede superar los {CONCEPTO_MAX_LONGITUD} caracteres.", None, None, None

    categoria_obj = next((c for c in categorias if c["nombre"] == categoria), None)
    if categoria_obj is None:
        return "Debe seleccionar una categoría válida.", None, None, None

    try:
        monto = float(monto_texto) if monto_texto else 0.0
    except ValueError:
        return "El monto debe ser un número válido.", None, None, None

    # DEF-01: float("inf") y float("nan") son "números" pero no son montos válidos.
    if not math.isfinite(monto):
        return "El monto debe ser un número válido.", None, None, None

    if monto <= 0:
        return "El monto del gasto debe ser mayor a 0.", None, None, None

    if not fecha_texto:
        return "La fecha del gasto es obligatoria.", None, None, None
    try:
        fecha = datetime.strptime(fecha_texto, "%Y-%m-%d")
    except ValueError:
        return "La fecha ingresada no es válida.", None, None, None
    if fecha.date() > datetime.now().date():
        return "No se pueden registrar gastos con fecha futura.", None, None, None

    # DEF-03: se guarda normalizada (AAAA-MM-DD) para que métricas y calendario la encuentren.
    return None, categoria_obj, monto, fecha.strftime("%Y-%m-%d")


@gastos_bp.route("/")
def index():
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "gastos.html", categorias=categorias, gastos=gastos,
        fecha_hoy=fecha_hoy, gasto_editar=None,
    )


@gastos_bp.route("/guardar", methods=["POST"])
def guardar():
    concepto = request.form.get("concepto", "").strip()
    categoria = request.form.get("categoria", "").strip()
    monto_texto = request.form.get("monto", "").strip()
    fecha_texto = request.form.get("fecha", "").strip()

    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    gastos = cargar_datos(ARCHIVO_GASTOS, [])

    # Reglas de negocio 6 a 11: concepto, categoría, monto y fecha válidos.
    error, categoria_obj, monto, fecha_texto = _validar_campos(
        concepto, categoria, monto_texto, fecha_texto, categorias
    )
    if error:
        flash(error, "error")
        return redirect(url_for("gastos.index"))

    nuevo_id = max([g["id"] for g in gastos], default=0) + 1
    gastos.append({
        "id": nuevo_id,
        "concepto": concepto,
        "categoria": categoria,
        "monto": monto,
        "fecha": fecha_texto,
    })
    guardar_datos(ARCHIVO_GASTOS, gastos)

    # Regla de negocio 12: si el total gastado en la categoría durante ese mes
    # (incluyendo este nuevo gasto) supera su límite mensual, se avisa al usuario.
    # El gasto igual se registra: el sistema controla/alerta, no bloquea.
    _avisar_si_excede_presupuesto(gastos, categoria, categoria_obj, fecha_texto, "registrado")
    return redirect(url_for("gastos.index"))


@gastos_bp.route("/editar/<int:id>")
def editar(id):
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    gasto = next((g for g in gastos if g["id"] == id), None)

    if gasto is None:
        flash("El gasto solicitado no existe.", "error")
        return redirect(url_for("gastos.index"))

    return render_template(
        "gastos.html", categorias=categorias, gastos=gastos,
        fecha_hoy=gasto["fecha"], gasto_editar=gasto,
    )


@gastos_bp.route("/actualizar/<int:id>", methods=["POST"])
def actualizar(id):
    concepto = request.form.get("concepto", "").strip()
    categoria = request.form.get("categoria", "").strip()
    monto_texto = request.form.get("monto", "").strip()
    fecha_texto = request.form.get("fecha", "").strip()

    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    gasto = next((g for g in gastos if g["id"] == id), None)

    if gasto is None:
        flash("El gasto solicitado no existe.", "error")
        return redirect(url_for("gastos.index"))

    # Las mismas reglas 6 a 11 aplican también al actualizar.
    error, categoria_obj, monto, fecha_texto = _validar_campos(
        concepto, categoria, monto_texto, fecha_texto, categorias
    )
    if error:
        flash(error, "error")
        return redirect(url_for("gastos.editar", id=id))

    gasto["concepto"] = concepto
    gasto["categoria"] = categoria
    gasto["monto"] = monto
    gasto["fecha"] = fecha_texto
    guardar_datos(ARCHIVO_GASTOS, gastos)

    _avisar_si_excede_presupuesto(gastos, categoria, categoria_obj, fecha_texto, "actualizado")
    return redirect(url_for("gastos.index"))


@gastos_bp.route("/eliminar/<int:id>", methods=["POST"])
def eliminar(id):
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    gasto = next((g for g in gastos if g["id"] == id), None)

    if gasto is None:
        flash("El gasto solicitado no existe.", "error")
        return redirect(url_for("gastos.index"))

    gastos = [g for g in gastos if g["id"] != id]
    guardar_datos(ARCHIVO_GASTOS, gastos)
    flash(f"Gasto '{gasto['concepto']}' eliminado correctamente.", "exito")
    return redirect(url_for("gastos.index"))


@gastos_bp.route("/calendario")
def calendario():
    gastos = cargar_datos(ARCHIVO_GASTOS, [])

    # El parámetro "semana" indica cualquier día de la semana a mostrar;
    # si no viene o es inválido, se muestra la semana actual.
    semana_param = request.args.get("semana", "").strip()
    try:
        fecha_ref = datetime.strptime(semana_param, "%Y-%m-%d") if semana_param else datetime.now()
    except ValueError:
        fecha_ref = datetime.now()

    # La semana empieza el lunes (weekday() == 0) y termina el domingo.
    inicio_semana = fecha_ref - timedelta(days=fecha_ref.weekday())
    hoy_texto = datetime.now().strftime("%Y-%m-%d")

    dias_semana = []
    total_semana_grid = 0.0
    for i in range(7):
        dia = inicio_semana + timedelta(days=i)
        fecha_texto = dia.strftime("%Y-%m-%d")
        gastos_dia = [g for g in gastos if g["fecha"] == fecha_texto]
        total_dia = sum(g["monto"] for g in gastos_dia)
        total_semana_grid += total_dia
        dias_semana.append({
            "nombre": NOMBRES_DIAS[i],
            "fecha": fecha_texto,
            "fecha_corta": dia.strftime("%d/%m"),
            "gastos": gastos_dia,
            "total": total_dia,
            "es_hoy": fecha_texto == hoy_texto,
        })

    fin_semana = inicio_semana + timedelta(days=6)
    semana_anterior = (inicio_semana - timedelta(days=7)).strftime("%Y-%m-%d")
    semana_siguiente = (inicio_semana + timedelta(days=7)).strftime("%Y-%m-%d")

    return render_template(
        "gastos_calendario.html",
        dias_semana=dias_semana,
        total_semana_grid=total_semana_grid,
        inicio_semana=inicio_semana.strftime("%d/%m/%Y"),
        fin_semana=fin_semana.strftime("%d/%m/%Y"),
        semana_anterior=semana_anterior,
        semana_siguiente=semana_siguiente,
    )


def _avisar_si_excede_presupuesto(gastos, categoria, categoria_obj, fecha_texto, accion):
    # El límite es mensual: solo cuentan los gastos de la categoría que caen
    # en el mismo mes (AAAA-MM) que el gasto registrado.
    mes_del_gasto = fecha_texto[:7]
    total_categoria = sum(
        g["monto"] for g in gastos
        if g["categoria"] == categoria and g["fecha"].startswith(mes_del_gasto)
    )
    limite_categoria = categoria_obj.get("limite", 0.0)
    if total_categoria > limite_categoria:
        exceso = total_categoria - limite_categoria
        flash(
            f"Gasto {accion}, pero la categoría '{categoria}' "
            f"superó su límite mensual de presupuesto (S/ {limite_categoria:.2f}) "
            f"por S/ {exceso:.2f}.",
            "aviso",
        )
    else:
        flash(f"Gasto {accion} correctamente.", "exito")
