import os
from flask import Flask, request, jsonify
from redis import Redis
from rq import Queue
from utils import test_job

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'mixtapegarden.sqlite'),
    )

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    print('database is ' + app.config['DATABASE'], flush=True)
    redis = Redis(host='redis', port=6379)
    q = Queue(connection=redis)

    import db
    db.init_app(app)

    import mixtape
    app.register_blueprint(mixtape.bp)
    app.add_url_rule('/', endpoint='index')

    return app
