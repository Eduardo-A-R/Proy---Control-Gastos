import json
import os

ARCHIVO_GASTOS = "gastos.txt"
ARCHIVO_CATEGORIAS = "categorias.txt"

CATEGORIAS_DEFECTO = [
    {"id": 1, "nombre": "Alimentación", "limite": 300.0},
    {"id": 2, "nombre": "Transporte", "limite": 120.0},
    {"id": 3, "nombre": "Estudios y Fotocopias", "limite": 80.0}
]


def cargar_datos(archivo, datos_defecto=None):
    """Lee el archivo .txt en cada ejecución/petición."""
    if datos_defecto is None:
        datos_defecto = []

    if not os.path.exists(archivo):
        guardar_datos(archivo, datos_defecto)
        return datos_defecto
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return datos_defecto


def guardar_datos(archivo, datos):
    """Escribe los datos en el archivo .txt con formato texto estándar."""
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)
