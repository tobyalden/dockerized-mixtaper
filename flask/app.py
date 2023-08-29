from flask import Flask, request, jsonify
from redis import Redis
from rq import Queue
from utils import test_job

def create_app(test_config=None):
    app = Flask(__name__)
    redis = Redis(host='redis', port=6379)
    q = Queue(connection=redis)

    @app.route('/')
    def hello():
        redis.incr('hits')
        counter = str(redis.get('hits'),'utf-8')
        q.enqueue(test_job)
        return "This cool website has been viewed "+counter+" time(s)"

    return app
