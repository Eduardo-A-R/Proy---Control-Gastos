from flask import Blueprint, render_template, request
from datetime import datetime
from persistence import cargar_datos, ARCHIVO_GASTOS, ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO
from metricas_calculo import calcular_metricas, desplazar_mes

metricas_bp = Blueprint('metricas', __name__, url_prefix='/metricas')


@metricas_bp.route("/")
def index():
    categorias = cargar_datos(ARCHIVO_CATEGORIAS, CATEGORIAS_DEFECTO)
    gastos = cargar_datos(ARCHIVO_GASTOS, [])
    hoy = datetime.now()

    # El parámetro ?mes=AAAA-MM elige qué mes ver; si falta, es inválido o
    # es un mes futuro, se muestra el mes actual.
    try:
        referencia = datetime.strptime(request.args.get("mes", "").strip(), "%Y-%m")
        anio, mes = referencia.year, referencia.month
    except ValueError:
        anio, mes = hoy.year, hoy.month
    if (anio, mes) > (hoy.year, hoy.month):
        anio, mes = hoy.year, hoy.month

    anterior = desplazar_mes(anio, mes, -1)
    siguiente = desplazar_mes(anio, mes, 1)
    metricas = calcular_metricas(gastos, categorias, hoy, anio, mes)

    return render_template(
        "metricas.html",
        mes_anterior_param=f"{anterior[0]:04d}-{anterior[1]:02d}",
        # No se puede navegar a meses futuros: aún no hay gastos en ellos.
        mes_siguiente_param=(
            f"{siguiente[0]:04d}-{siguiente[1]:02d}"
            if siguiente <= (hoy.year, hoy.month) else None
        ),
        **metricas,
    )
