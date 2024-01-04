import os
from flask import Flask, send_from_directory, render_template, session
from datetime import timedelta

TRACKS_PER_MIXTAPE = 7
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp"}
MAX_USERNAME_LENGTH = 30
MAX_MIXTAPE_TITLE_LENGTH = 50
MAX_MIXTAPE_DESCRIPTION_LENGTH = 256
MAX_TRACK_DESCRIPTION_LENGTH = 256

FLASH_ERROR = "error"
FLASH_SUCCESS = "success"



def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        CUSTOM_STATIC_PATH=os.path.join(app.root_path, "cdn"),
        SECRET_KEY="dev",
        DATABASE=os.path.join(app.root_path, "static", "mixtapegarden.sqlite"),
        MIXES_FOLDER=os.path.join(app.root_path, "static", "mixtapes"),
        MIXTAPE_ART_FOLDER=os.path.join(app.root_path, "static", "mixtape_art"),
        USER_AVATAR_FOLDER=os.path.join(app.root_path, "static", "user_avatars"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=365)
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    import db

    db.init_app(app)

    import auth

    app.register_blueprint(auth.bp)

    import mixtape

    app.register_blueprint(mixtape.bp)
    app.add_url_rule("/", endpoint="index")

    import user

    app.register_blueprint(user.bp)

    @app.route('/about')
    def about():
        return render_template("about.html")

    @app.route('/cdn/<path:filename>')
    def custom_static(filename):
        return send_from_directory(app.config['CUSTOM_STATIC_PATH'], filename)

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    return app
