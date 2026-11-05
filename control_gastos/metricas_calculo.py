import calendar

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# Umbrales del semáforo (en % del límite consumido). Son una convención de
# alerta temprana, la misma idea de las alertas de presupuesto de apps
# bancarias: avisar antes de pasarse, no después. Se pueden ajustar aquí.
UMBRAL_AVISO = 80.0    # amarillo: ya casi llegas al límite
UMBRAL_ALERTA = 100.0  # rojo: te pasaste del límite

# Cuántos días de datos se necesitan para que la proyección sea medianamente fiable.
DIAS_MINIMOS_PROYECCION = 5


def desplazar_mes(anio, mes, delta):
    """Devuelve (anio, mes) desplazado `delta` meses (puede ser negativo)."""
    indice = anio * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def _estado_por_porcentaje(porcentaje):
    if porcentaje >= UMBRAL_ALERTA:
        return "alerta"
    if porcentaje >= UMBRAL_AVISO:
        return "aviso"
    return "ok"


def _soles(valor):
    signo = "-" if valor < 0 else ""
    return f"{signo}S/ {abs(valor):.2f}"


def _metrica(titulo, valor, detalle, estado, porque):
    return {
        "titulo": titulo,
        "valor": valor,
        "detalle": detalle,
        "estado": estado,  # "ok" | "aviso" | "alerta" | "neutro"
        "porque": porque,
    }


def calcular_metricas(gastos, categorias, hoy, anio, mes):
    """Calcula las métricas de consumo del mes (anio, mes).

    Los límites de las categorías se interpretan como presupuesto MENSUAL, por
    eso todas las métricas se calculan sobre un mes y no sobre todo el
    histórico (un acumulado de varios meses contra un límite mensual no
    sirve para decidir nada).

    `hoy` es el momento actual; se usa para saber cuántos días del mes
    van transcurridos y cuántos quedan.
    """
    prefijo = f"{anio:04d}-{mes:02d}"
    dias_mes = calendar.monthrange(anio, mes)[1]
    es_mes_actual = (anio, mes) == (hoy.year, hoy.month)
    dias_transcurridos = hoy.day if es_mes_actual else dias_mes
    # Días que quedan contando hoy: el gasto de hoy todavía puede cambiar.
    dias_restantes = (dias_mes - hoy.day + 1) if es_mes_actual else 0
    mes_texto = f"{MESES_ES[mes - 1]} {anio}"

    gastos_mes = [g for g in gastos if g["fecha"].startswith(prefijo)]
    gastado = sum(g["monto"] for g in gastos_mes)
    presupuesto = sum(c["limite"] for c in categorias)
    disponible = presupuesto - gastado
    porcentaje = (gastado / presupuesto * 100) if presupuesto > 0 else 0
    estado_global = _estado_por_porcentaje(porcentaje)

    # ---- Resumen por categoría (base de varias métricas y de la tabla) ----
    resumen_categorias = []
    for c in categorias:
        gastado_cat = sum(g["monto"] for g in gastos_mes if g["categoria"] == c["nombre"])
        porcentaje_cat = (gastado_cat / c["limite"] * 100) if c["limite"] > 0 else 0
        resumen_categorias.append({
            "nombre": c["nombre"],
            "limite": c["limite"],
            "gastado": gastado_cat,
            "disponible": c["limite"] - gastado_cat,
            "porcentaje": min(porcentaje_cat, 100),   # ancho de la barra (tope 100%)
            "porcentaje_real": porcentaje_cat,        # texto (puede pasar de 100%)
            "estado": _estado_por_porcentaje(porcentaje_cat),
        })

    # =====================================================================
    # GRUPO 1: lo esencial (las 4 métricas base)
    # =====================================================================

    # M1 - Cuánto tenías en total.
    m_presupuesto = _metrica(
        "Cuánto tenías en total (presupuesto del mes)",
        _soles(presupuesto),
        f"Suma de los límites mensuales de tus {len(categorias)} categorías",
        "neutro",
        "Es el punto de partida de todo control: sin saber cuánto dinero tienes "
        "asignado no se puede decir si gastas mucho o poco. Todas las demás "
        "métricas se miden contra esta cifra.",
    )

    # M2 - Cuánto gastaste.
    m_gastado = _metrica(
        "Cuánto gastaste",
        _soles(gastado),
        f"{len(gastos_mes)} gasto(s) registrado(s) en {mes_texto}",
        "neutro",
        "Es el dato real contra el que se compara el plan. Ver el total acumulado "
        "del mes te hace consciente de lo que ya salió; los gastos pequeños y "
        "frecuentes suelen pasar desapercibidos si solo los miras de uno en uno.",
    )

    # M3 - Cuánto te falta.
    if disponible >= 0:
        detalle_disp = f"Te queda el {max(100 - porcentaje, 0):.1f}% del presupuesto"
    else:
        detalle_disp = f"Te pasaste del presupuesto por {_soles(-disponible)}"
    m_disponible = _metrica(
        "Cuánto te falta (disponible)",
        _soles(disponible),
        detalle_disp,
        estado_global,
        "Es la diferencia entre lo planeado y lo real (en control presupuestario "
        "se llama desviación). Te dice cuánto margen te queda para decidir; si "
        "es negativo, ya te pasaste y toca recortar en otras categorías.",
    )

    # M4 - Categoría que más falta (la de mayor saldo disponible).
    cat_mas_saldo = max(resumen_categorias, key=lambda r: r["disponible"], default=None)
    if cat_mas_saldo:
        valor_saldo = cat_mas_saldo["nombre"]
        detalle_saldo = (
            f"Te quedan {_soles(cat_mas_saldo['disponible'])} de "
            f"{_soles(cat_mas_saldo['limite'])}"
        )
    else:
        valor_saldo, detalle_saldo = "—", "Aún no hay categorías registradas"
    m_mas_saldo = _metrica(
        "Categoría con más saldo disponible",
        valor_saldo,
        detalle_saldo,
        "neutro",
        "Muestra dónde tienes más holgura. Si surge un imprevisto, es la "
        "categoría que menos daño le hace al plan; y si sobra mucho al cierre "
        "del mes, quizá su límite está sobreestimado y conviene reasignarlo.",
    )

    # =====================================================================
    # GRUPO 2: alertas (dónde actuar)
    # =====================================================================

    # M5 - % del presupuesto consumido, con semáforo.
    m_porcentaje = _metrica(
        "% del presupuesto consumido",
        f"{porcentaje:.1f}%",
        f"Verde: menos de {UMBRAL_AVISO:.0f}% · Amarillo: {UMBRAL_AVISO:.0f}% a "
        f"{UMBRAL_ALERTA - 0.1:.1f}% · Rojo: {UMBRAL_ALERTA:.0f}% o más",
        estado_global,
        "Convierte soles en una proporción comparable: S/ 400 gastados significan "
        "algo muy distinto con un presupuesto de S/ 500 que con uno de S/ 2000. "
        "El semáforo es una alerta temprana: avisa antes de excederte, no después.",
    )

    # M6 - Categoría más crítica (mayor % de su límite consumido).
    cat_critica = max(resumen_categorias, key=lambda r: r["porcentaje_real"], default=None)
    if cat_critica and cat_critica["porcentaje_real"] > 0:
        if cat_critica["disponible"] < 0:
            detalle_crit = f"Excedida por {_soles(-cat_critica['disponible'])}"
        else:
            detalle_crit = (
                f"{cat_critica['porcentaje_real']:.1f}% de su límite consumido "
                f"(quedan {_soles(cat_critica['disponible'])})"
            )
        m_critica = _metrica(
            "Categoría más crítica",
            cat_critica["nombre"],
            detalle_crit,
            cat_critica["estado"],
            "Los problemas de presupuesto suelen concentrarse en pocas "
            "categorías, no repartirse parejo. Identificar cuál está más cerca "
            "(o más allá) de su límite te dice dónde actuar primero con el "
            "menor esfuerzo.",
        )
    else:
        m_critica = _metrica(
            "Categoría más crítica",
            "—",
            "Aún no hay gastos en este mes",
            "ok",
            "Los problemas de presupuesto suelen concentrarse en pocas "
            "categorías, no repartirse parejo. Cuando registres gastos aquí "
            "verás cuál está más cerca de su límite.",
        )

    # =====================================================================
    # GRUPO 3: ritmo y proyección (anticiparte)
    # =====================================================================

    # M7 - Gasto promedio diario.
    promedio_diario = gastado / dias_transcurridos if dias_transcurridos > 0 else 0
    m_promedio = _metrica(
        "Gasto promedio por día",
        _soles(promedio_diario),
        f"Calculado sobre {dias_transcurridos} día(s) del mes",
        "neutro",
        "Convierte un total mensual, difícil de sentir, en un ritmo diario "
        "concreto (en finanzas se llama tasa de consumo o \"burn rate\"). "
        "Compararlo con el gasto diario sugerido te dice si vas acelerado.",
    )

    # M8 - Cuánto puedes gastar por día hasta fin de mes.
    if not es_mes_actual:
        m_sugerido = _metrica(
            "Puedes gastar por día hasta fin de mes",
            "—",
            "Mes cerrado: ya no quedan días por delante",
            "neutro",
            "Es la métrica más accionable: transforma \"te quedan S/ 300\" en "
            "\"puedes gastar S/ 18 por día\". Solo aplica al mes en curso.",
        )
    elif disponible <= 0:
        m_sugerido = _metrica(
            "Puedes gastar por día hasta fin de mes",
            _soles(0),
            "Ya agotaste el presupuesto del mes",
            "alerta",
            "Es la métrica más accionable: transforma \"te quedan S/ 300\" en "
            "\"puedes gastar S/ 18 por día\". Con saldo cero, cualquier gasto "
            "nuevo sale de lo que ya no tienes.",
        )
    else:
        sugerido = disponible / dias_restantes
        m_sugerido = _metrica(
            "Puedes gastar por día hasta fin de mes",
            _soles(sugerido),
            f"Para los {dias_restantes} día(s) que quedan (contando hoy)",
            "aviso" if promedio_diario > sugerido else "ok",
            "Es la métrica más accionable: transforma \"te quedan S/ 300\" en "
            "\"puedes gastar S/ 18 por día\". Es más fácil decidir un gasto de "
            "hoy con una cifra diaria que con un saldo mensual. Amarillo = tu "
            "ritmo actual es mayor que este tope.",
        )

    # M9 - Proyección a fin de mes (o cierre, si el mes ya terminó).
    if es_mes_actual:
        proyeccion = promedio_diario * dias_mes
        diferencia = presupuesto - proyeccion
        if diferencia >= 0:
            detalle_proy = f"Si sigues igual, te sobrarían {_soles(diferencia)}"
        else:
            detalle_proy = f"Si sigues igual, te pasarías por {_soles(-diferencia)}"
        if dias_transcurridos < DIAS_MINIMOS_PROYECCION:
            detalle_proy += " (pocos días de datos: estimación poco fiable)"
        m_proyeccion = _metrica(
            "Proyección a fin de mes",
            _soles(proyeccion),
            detalle_proy,
            "alerta" if proyeccion > presupuesto else "ok",
            "Estima cómo cerrarás el mes si mantienes el mismo ritmo (proyección "
            "lineal: promedio diario × días del mes). Sirve para anticiparte: "
            "puedes corregir a mitad de mes en vez de enterarte el día 30. Es "
            "una estimación, no una certeza; se vuelve más fiable con los días.",
        )
    else:
        diferencia = presupuesto - gastado
        m_proyeccion = _metrica(
            "Cierre del mes",
            _soles(gastado),
            (f"Cerraste con {_soles(diferencia)} de margen" if diferencia >= 0
             else f"Cerraste pasándote por {_soles(-diferencia)}"),
            "alerta" if gastado > presupuesto else "ok",
            "En un mes ya cerrado no hay nada que proyectar: el resultado final "
            "contra el presupuesto es la lección para planificar el siguiente.",
        )

    # M10 - Comparación con el mes anterior (mismo tramo del mes).
    anio_prev, mes_prev = desplazar_mes(anio, mes, -1)
    prefijo_prev = f"{anio_prev:04d}-{mes_prev:02d}"
    tramo = dias_transcurridos if es_mes_actual else 31
    gastado_prev = sum(
        g["monto"] for g in gastos
        if g["fecha"].startswith(prefijo_prev) and int(g["fecha"][8:10]) <= tramo
    )
    nombre_prev = MESES_ES[mes_prev - 1]
    if es_mes_actual:
        comparado = f"primeros {tramo} día(s) de cada mes"
    else:
        comparado = "mes completo contra mes completo"
    porque_comparacion = (
        "Un total aislado no dice si estás mejorando o empeorando. Se compara "
        "el mismo tramo de ambos meses (por ejemplo, los primeros 16 días de "
        "cada uno) para no caer en la trampa de comparar un mes incompleto "
        "con uno completo; así se ve la tendencia real de tu hábito."
    )
    if gastado_prev > 0:
        variacion = (gastado - gastado_prev) / gastado_prev * 100
        m_comparacion = _metrica(
            f"Comparación con {nombre_prev}",
            f"{variacion:+.1f}%",
            f"{_soles(gastado)} vs {_soles(gastado_prev)} ({comparado})",
            "aviso" if variacion > 10 else "ok",
            porque_comparacion + " Amarillo = gastas más de 10% por encima.",
        )
    else:
        m_comparacion = _metrica(
            f"Comparación con {nombre_prev}",
            "—",
            f"Sin gastos registrados en {nombre_prev} para comparar",
            "neutro",
            porque_comparacion,
        )

    grupos = [
        {
            "titulo": "1. Lo esencial: tu situación del mes",
            "descripcion": "Las cuatro preguntas básicas: cuánto tenías, cuánto gastaste, cuánto te falta y dónde.",
            "metricas": [m_presupuesto, m_gastado, m_disponible, m_mas_saldo],
        },
        {
            "titulo": "2. Alertas: dónde actuar",
            "descripcion": "Indicadores con semáforo para detectar a tiempo qué está por salirse de control.",
            "metricas": [m_porcentaje, m_critica],
        },
        {
            "titulo": "3. Ritmo y proyección: anticípate",
            "descripcion": "Convierten los totales en un ritmo diario y en una estimación de cómo cerrarás el mes.",
            "metricas": [m_promedio, m_sugerido, m_proyeccion, m_comparacion],
        },
    ]

    return {
        "grupos": grupos,
        "resumen_categorias": resumen_categorias,
        "mes_texto": mes_texto,
        "es_mes_actual": es_mes_actual,
        "dias_transcurridos": dias_transcurridos,
        "dias_mes": dias_mes,
    }
