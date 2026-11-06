from flask import Flask, redirect, url_for
from routes.gastos_routes import gastos_bp
from routes.categorias_routes import categorias_bp
from routes.metricas_routes import metricas_bp

app = Flask(__name__)
app.secret_key = "clave_secreta_control_gastos"

# Registro de Módulos (Blueprints): gastos y categorías con CRUD completo,
# más el módulo de métricas como pantalla principal.
app.register_blueprint(gastos_bp)
app.register_blueprint(categorias_bp)
app.register_blueprint(metricas_bp)


@app.route("/")
def index():
    return redirect(url_for("metricas.index"))


if __name__ == "__main__":
    app.run(debug=True)
