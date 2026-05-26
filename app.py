from flask import Flask
from api.routes import api_bp
from api.database import init_db
import os

def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.register_blueprint(api_bp, url_prefix="/api")
    init_db()

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
