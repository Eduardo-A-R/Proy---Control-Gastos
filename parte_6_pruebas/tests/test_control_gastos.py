"""Pruebas automatizadas del Sistema de Control de Gastos (pytest + Flask test client)."""
import json, os, sys
from datetime import datetime, timedelta
import pytest

PROYECTO = os.environ.get("PROYECTO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "control_gastos"))
sys.path.insert(0, PROYECTO)
import app as app_mod            # noqa: E402
import persistence               # noqa: E402
from metricas_calculo import calcular_metricas, desplazar_mes  # noqa: E402

HOY = datetime.now().strftime("%Y-%m-%d")
AYER = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
MANANA = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


import copy
_DEFECTO_ORIGINAL = copy.deepcopy(persistence.CATEGORIAS_DEFECTO)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # los .txt se crean en el directorio actual
    persistence.CATEGORIAS_DEFECTO[:] = copy.deepcopy(_DEFECTO_ORIGINAL)   # aísla cada prueba
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


def gastos():
    return persistence.cargar_datos("gastos.txt", [])


def cats():
    return persistence.cargar_datos("categorias.txt", persistence.CATEGORIAS_DEFECTO)


def post(cli, url, **data):
    return cli.post(url, data=data, follow_redirects=True).get_data(as_text=True)


def nuevo_gasto(cli, concepto="Almuerzo", categoria="Alimentación", monto="10", fecha=None):
    return post(cli, "/gastos/guardar", concepto=concepto, categoria=categoria,
                monto=monto, fecha=fecha or HOY)


# ---------------- Categorías ----------------
def test_CT01_crear_categoria_valida(cli):
    h = post(cli, "/categorias/guardar", nombre="Salud", limite="150")
    assert "registrada correctamente" in h and any(c["nombre"] == "Salud" for c in cats())

def test_CT02_categoria_nombre_vacio(cli):
    assert "obligatorio" in post(cli, "/categorias/guardar", nombre="  ", limite="10")

def test_CT03_categoria_nombre_largo(cli):
    assert "50 caracteres" in post(cli, "/categorias/guardar", nombre="x" * 51, limite="10")

def test_CT04_categoria_duplicada_sin_distinguir_mayusculas(cli):
    assert "Ya existe" in post(cli, "/categorias/guardar", nombre="  ALIMENTACIÓN ", limite="10")

def test_CT05_categoria_limite_no_numerico(cli):
    assert "número válido" in post(cli, "/categorias/guardar", nombre="Ocio", limite="abc")

@pytest.mark.parametrize("v", ["0", "-5"])
def test_CT06_categoria_limite_no_positivo(cli, v):
    assert "mayor a 0" in post(cli, "/categorias/guardar", nombre="Ocio", limite=v)

def test_CT07_actualizar_categoria(cli):
    post(cli, "/categorias/actualizar/1", nombre="Comida", limite="350")
    assert cats()[0]["nombre"] == "Comida" and cats()[0]["limite"] == 350

def test_CT08_renombrar_categoria_propaga_a_gastos(cli):
    nuevo_gasto(cli)
    post(cli, "/categorias/actualizar/1", nombre="Comida", limite="300")
    assert gastos()[0]["categoria"] == "Comida"

def test_CT09_no_eliminar_categoria_con_gastos(cli):
    nuevo_gasto(cli)
    assert "No se puede eliminar" in post(cli, "/categorias/eliminar/1")
    assert len(cats()) == 3

def test_CT10_eliminar_categoria_sin_gastos(cli):
    post(cli, "/categorias/eliminar/2")
    assert all(c["id"] != 2 for c in cats())

def test_CT11_categoria_inexistente(cli):
    assert "no existe" in cli.get("/categorias/editar/99", follow_redirects=True).get_data(as_text=True)


# ---------------- Gastos ----------------
def test_CT12_registrar_gasto_valido(cli):
    h = nuevo_gasto(cli)
    assert "registrado correctamente" in h and len(gastos()) == 1

def test_CT13_gasto_concepto_vacio(cli):
    assert "concepto del gasto es obligatorio" in nuevo_gasto(cli, concepto=" ")

def test_CT14_gasto_concepto_largo(cli):
    assert "100 caracteres" in nuevo_gasto(cli, concepto="x" * 101)

def test_CT15_gasto_categoria_invalida(cli):
    assert "categoría válida" in nuevo_gasto(cli, categoria="Inexistente")

@pytest.mark.parametrize("m", ["0", "-3"])
def test_CT16_gasto_monto_no_positivo(cli, m):
    assert "mayor a 0" in nuevo_gasto(cli, monto=m)

def test_CT17_gasto_monto_no_numerico(cli):
    assert "número válido" in nuevo_gasto(cli, monto="diez")

def test_CT18_gasto_fecha_vacia(cli):
    assert "fecha del gasto es obligatoria" in post(cli, "/gastos/guardar", concepto="a", categoria="Transporte", monto="5", fecha="")

def test_CT19_gasto_fecha_invalida(cli):
    assert "fecha ingresada no es válida" in nuevo_gasto(cli, fecha="31-02-2026")

def test_CT20_gasto_fecha_futura(cli):
    assert "fecha futura" in nuevo_gasto(cli, fecha=MANANA)

def test_CT21_alerta_si_excede_limite_mensual(cli):
    h = nuevo_gasto(cli, categoria="Estudios y Fotocopias", monto="90")
    assert "superó su límite mensual" in h and len(gastos()) == 1   # alerta, no bloquea

def test_CT22_editar_gasto(cli):
    nuevo_gasto(cli)
    post(cli, "/gastos/actualizar/1", concepto="Cena", categoria="Alimentación", monto="25.5", fecha=AYER)
    g = gastos()[0]
    assert (g["concepto"], g["monto"], g["fecha"]) == ("Cena", 25.5, AYER)

def test_CT23_eliminar_gasto(cli):
    nuevo_gasto(cli)
    assert "eliminado correctamente" in post(cli, "/gastos/eliminar/1") and gastos() == []

def test_CT24_gasto_inexistente(cli):
    assert "no existe" in post(cli, "/gastos/eliminar/42")

def test_CT25_id_incremental_sin_reutilizar(cli):
    nuevo_gasto(cli); nuevo_gasto(cli); post(cli, "/gastos/eliminar/1"); nuevo_gasto(cli)
    assert [g["id"] for g in gastos()] == [2, 3]


# ---------------- Calendario ----------------
def test_CT26_calendario_semana_lunes_a_domingo(cli):
    nuevo_gasto(cli, monto="10", fecha="2026-10-27"); nuevo_gasto(cli, monto="5", fecha="2026-10-25")
    h = cli.get("/gastos/calendario?semana=2026-10-27").get_data(as_text=True)
    assert "26/10/2026 — 01/11/2026" in h and "S/ 10.00" in h

def test_CT27_calendario_parametro_invalido(cli):
    assert cli.get("/gastos/calendario?semana=xx").status_code == 200


# ---------------- Métricas ----------------
def _m(gs, cs, hoy, a, m):
    r = calcular_metricas(gs, cs, hoy, a, m)
    return {x["titulo"]: x for g in r["grupos"] for x in g["metricas"]}, r

CS = [{"id": 1, "nombre": "A", "limite": 100.0}, {"id": 2, "nombre": "B", "limite": 100.0}]

def test_CT28_presupuesto_gastado_disponible():
    gs = [{"categoria": "A", "monto": 30.0, "fecha": "2026-10-05"}, {"categoria": "B", "monto": 20.0, "fecha": "2026-10-06"}]
    m, _ = _m(gs, CS, datetime(2026, 10, 10), 2026, 10)
    assert m["Cuánto tenías en total (presupuesto del mes)"]["valor"] == "S/ 200.00"
    assert m["Cuánto gastaste"]["valor"] == "S/ 50.00"
    assert m["Cuánto te falta (disponible)"]["valor"] == "S/ 150.00"

@pytest.mark.parametrize("monto,estado", [(79.9, "ok"), (80, "aviso"), (99.9, "aviso"), (100, "alerta"), (150, "alerta")])
def test_CT29_semaforo(monto, estado):
    cs = [{"id": 1, "nombre": "A", "limite": 100.0}]
    m, _ = _m([{"categoria": "A", "monto": monto, "fecha": "2026-10-02"}], cs, datetime(2026, 10, 10), 2026, 10)
    assert m["% del presupuesto consumido"]["estado"] == estado

def test_CT30_promedio_y_proyeccion_lineal():
    gs = [{"categoria": "A", "monto": 100.0, "fecha": "2026-10-03"}]
    m, _ = _m(gs, CS, datetime(2026, 10, 10), 2026, 10)
    assert m["Gasto promedio por día"]["valor"] == "S/ 10.00"
    assert m["Proyección a fin de mes"]["valor"] == "S/ 310.00"       # 10 * 31
    assert m["Proyección a fin de mes"]["estado"] == "alerta"

def test_CT31_gasto_diario_sugerido():
    gs = [{"categoria": "A", "monto": 50.0, "fecha": "2026-10-03"}]
    m, _ = _m(gs, CS, datetime(2026, 10, 10), 2026, 10)
    assert m["Puedes gastar por día hasta fin de mes"]["valor"] == "S/ 6.82"   # 150 / 22

def test_CT32_mes_cerrado_muestra_cierre():
    gs = [{"categoria": "A", "monto": 50.0, "fecha": "2026-09-03"}]
    m, r = _m(gs, CS, datetime(2026, 10, 10), 2026, 9)
    assert "Cierre del mes" in m and r["es_mes_actual"] is False

def test_CT33_comparacion_mes_anterior_mismo_tramo():
    gs = [{"categoria": "A", "monto": 50.0, "fecha": "2026-09-03"}, {"categoria": "A", "monto": 90.0, "fecha": "2026-09-25"},
          {"categoria": "A", "monto": 60.0, "fecha": "2026-10-03"}]
    m, _ = _m(gs, CS, datetime(2026, 10, 10), 2026, 10)
    assert m["Comparación con Septiembre"]["valor"] == "+20.0%"       # 60 vs 50 (solo días 1-10)

def test_CT34_categoria_mas_critica():
    gs = [{"categoria": "A", "monto": 120.0, "fecha": "2026-10-03"}, {"categoria": "B", "monto": 10.0, "fecha": "2026-10-03"}]
    m, _ = _m(gs, CS, datetime(2026, 10, 10), 2026, 10)
    assert m["Categoría más crítica"]["valor"] == "A" and m["Categoría más crítica"]["estado"] == "alerta"

def test_CT35_sin_categorias_no_divide_por_cero():
    m, _ = _m([], [], datetime(2026, 10, 10), 2026, 10)
    assert m["% del presupuesto consumido"]["valor"] == "0.0%"

@pytest.mark.parametrize("a,m,d,esperado", [(2026, 1, -1, (2025, 12)), (2026, 12, 1, (2027, 1)), (2026, 3, -14, (2025, 1))])
def test_CT36_desplazar_mes(a, m, d, esperado):
    assert desplazar_mes(a, m, d) == esperado

def test_CT37_pagina_metricas_y_mes_futuro(cli):
    assert cli.get("/").status_code == 302
    assert cli.get("/metricas/?mes=2099-01").status_code == 200
    assert cli.get("/metricas/?mes=basura").status_code == 200


# ---------------- Pruebas de robustez / seguridad básica ----------------
def test_CT38_xss_escapado_por_jinja(cli):
    nuevo_gasto(cli, concepto="<script>alert(1)</script>")
    h = cli.get("/gastos/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in h and "&lt;script&gt;" in h

def test_CT39_monto_infinito_rechazado(cli):
    nuevo_gasto(cli, monto="inf")
    assert gastos() == []

def test_CT40_limite_nan_rechazado(cli):
    post(cli, "/categorias/guardar", nombre="Raro", limite="nan")
    assert all(c["nombre"] != "Raro" for c in cats())

def test_CT41_fecha_sin_cero_inicial_rechazada(cli):
    nuevo_gasto(cli, fecha="2026-1-5")
    assert gastos() == [] or gastos()[0]["fecha"] == "2026-01-05"

def test_CT42_archivo_corrupto_no_se_sobrescribe_sin_respaldo(cli):
    nuevo_gasto(cli)
    open("gastos.txt", "w").write("{corrupto")
    nuevo_gasto(cli, concepto="Otro")           # se guarda sobre un archivo que no se pudo leer
    assert os.path.exists("gastos.txt.bak")     # se esperaría un respaldo del archivo dañado

def test_CT43_categorias_por_defecto_no_se_comparten_entre_peticiones(cli):
    post(cli, "/categorias/guardar", nombre="Salud", limite="50")   # 1.ª petición: crea el archivo
    assert len(persistence.CATEGORIAS_DEFECTO) == 3                 # la constante no debe mutar
