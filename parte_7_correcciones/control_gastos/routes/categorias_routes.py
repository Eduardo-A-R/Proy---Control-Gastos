import math
from flask import Blueprint, render_template, request, redirect, url_for, flash
from persistence import cargar_datos, guardar_datos, ARCHIVO_CATEGORIAS, ARCHIVO_GASTOS, CATEGORIAS_DEFECTO

categorias_bp = Blueprint('categorias', __name__, url_prefix='/categorias')

NOMBRE_MAX_LONGITUD = 50


@categorias_bp.route("/")
def index():
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    return render_template("categorias.html", categorias=categorias, categoria_editar=None)


@categorias_bp.route("/guardar", methods=["POST"])
def guardar():
    nombre = request.form.get("nombre", "").strip()
    limite_texto = request.form.get("limite", "").strip()

    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)

    # Regla de negocio 1: el nombre de la categoría es obligatorio.
    if not nombre:
        flash("El nombre de la categoría es obligatorio.", "error")
        return redirect(url_for("categorias.index"))

    # Regla de negocio 2: el nombre no puede exceder una longitud máxima,
    # para evitar datos basura o nombres poco útiles en los reportes.
    if len(nombre) > NOMBRE_MAX_LONGITUD:
        flash(f"El nombre no puede superar los {NOMBRE_MAX_LONGITUD} caracteres.", "error")
        return redirect(url_for("categorias.index"))

    # Regla de negocio 3: no se permiten categorías duplicadas
    # (comparación sin distinguir mayúsculas/minúsculas ni espacios extremos).
    nombres_existentes = {c["nombre"].strip().lower() for c in categorias}
    if nombre.lower() in nombres_existentes:
        flash(f"Ya existe una categoría llamada '{nombre}'.", "error")
        return redirect(url_for("categorias.index"))

    # Regla de negocio 4: el límite de presupuesto debe ser un número válido.
    try:
        limite = float(limite_texto) if limite_texto else 0.0
    except ValueError:
        flash("El límite de presupuesto debe ser un número válido.", "error")
        return redirect(url_for("categorias.index"))

    # DEF-02: infinito y NaN no son límites válidos.
    if not math.isfinite(limite):
        flash("El límite de presupuesto debe ser un número válido.", "error")
        return redirect(url_for("categorias.index"))

    # Regla de negocio 5: el límite de presupuesto debe ser mayor a cero,
    # ya que una categoría sin presupuesto asignado no tiene sentido de control.
    if limite <= 0:
        flash("El límite de presupuesto debe ser mayor a 0.", "error")
        return redirect(url_for("categorias.index"))

    nuevo_id = max([c["id"] for c in categorias], default=0) + 1
    categorias.append({"id": nuevo_id, "nombre": nombre, "limite": limite})

    guardar_datos(ARCHIVO_CATEGORIAS, categorias)
    flash(f"Categoría '{nombre}' registrada correctamente.", "exito")
    return redirect(url_for("categorias.index"))


@categorias_bp.route("/editar/<int:id>")
def editar(id):
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    categoria = next((c for c in categorias if c["id"] == id), None)

    if categoria is None:
        flash("La categoría solicitada no existe.", "error")
        return redirect(url_for("categorias.index"))

    return render_template("categorias.html", categorias=categorias, categoria_editar=categoria)


@categorias_bp.route("/actualizar/<int:id>", methods=["POST"])
def actualizar(id):
    nombre = request.form.get("nombre", "").strip()
    limite_texto = request.form.get("limite", "").strip()

    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    categoria = next((c for c in categorias if c["id"] == id), None)

    if categoria is None:
        flash("La categoría solicitada no existe.", "error")
        return redirect(url_for("categorias.index"))

    # Las mismas reglas 1, 2, 4 y 5 aplican también al actualizar.
    if not nombre:
        flash("El nombre de la categoría es obligatorio.", "error")
        return redirect(url_for("categorias.editar", id=id))

    if len(nombre) > NOMBRE_MAX_LONGITUD:
        flash(f"El nombre no puede superar los {NOMBRE_MAX_LONGITUD} caracteres.", "error")
        return redirect(url_for("categorias.editar", id=id))

    # Regla de negocio 3 (variante actualizar): no permitir duplicados,
    # excluyendo a la propia categoría que se está editando.
    nombres_existentes = {
        c["nombre"].strip().lower() for c in categorias if c["id"] != id
    }
    if nombre.lower() in nombres_existentes:
        flash(f"Ya existe una categoría llamada '{nombre}'.", "error")
        return redirect(url_for("categorias.editar", id=id))

    try:
        limite = float(limite_texto) if limite_texto else 0.0
    except ValueError:
        flash("El límite de presupuesto debe ser un número válido.", "error")
        return redirect(url_for("categorias.editar", id=id))

    if not math.isfinite(limite):
        flash("El límite de presupuesto debe ser un número válido.", "error")
        return redirect(url_for("categorias.editar", id=id))

    if limite <= 0:
        flash("El límite de presupuesto debe ser mayor a 0.", "error")
        return redirect(url_for("categorias.editar", id=id))

    nombre_anterior = categoria["nombre"]
    categoria["nombre"] = nombre
    categoria["limite"] = limite
    guardar_datos(ARCHIVO_CATEGORIAS, categorias)

    # Regla de negocio 13: si se renombra la categoría, los gastos ya
    # registrados que la referencian (por nombre) se actualizan para
    # mantener la integridad de los datos entre ambos archivos.
    if nombre_anterior != nombre:
        gastos = cargar_datos(ARCHIVO_GASTOS, [])
        cambiaron = False
        for g in gastos:
            if g["categoria"] == nombre_anterior:
                g["categoria"] = nombre
                cambiaron = True
        if cambiaron:
            guardar_datos(ARCHIVO_GASTOS, gastos)

    flash(f"Categoría '{nombre}' actualizada correctamente.", "exito")
    return redirect(url_for("categorias.index"))


@categorias_bp.route("/eliminar/<int:id>", methods=["POST"])
def eliminar(id):
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    categoria = next((c for c in categorias if c["id"] == id), None)

    if categoria is None:
        flash("La categoría solicitada no existe.", "error")
        return redirect(url_for("categorias.index"))

    # Regla de negocio 14: no se puede eliminar una categoría que ya
    # tiene gastos asociados, para no dejar gastos "huérfanos" sin categoría.
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    tiene_gastos = any(g["categoria"] == categoria["nombre"] for g in gastos)
    if tiene_gastos:
        flash(
            f"No se puede eliminar '{categoria['nombre']}': tiene gastos "
            "registrados asociados. Elimina o reasigna esos gastos primero.",
            "error",
        )
        return redirect(url_for("categorias.index"))

    categorias = [c for c in categorias if c["id"] != id]
    guardar_datos(ARCHIVO_CATEGORIAS, categorias)
    flash(f"Categoría '{categoria['nombre']}' eliminada correctamente.", "exito")
    return redirect(url_for("categorias.index"))
