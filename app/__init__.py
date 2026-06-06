from flask import Flask


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.secret_key = "lego-deals-change-this-secret"

    from app.routes import bp
    app.register_blueprint(bp)

    return app
