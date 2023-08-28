from flask import Flask, request, jsonify
from redis import Redis

app = Flask(__name__)
redis = Redis(host='redis', port=6379)

@app.route('/')
def hello():
    redis.incr('hits')
    counter = str(redis.get('hits'),'utf-8')
    return "This webpage has been viewed "+counter+" time(s)"

@app.route('/cache-me')
def cache():
	return "nginx will cache this response"

@app.route('/info')
def info():

	resp = {
		'connecting_ip': request.headers['X-Real-IP'],
		'proxy_ip': request.headers['X-Forwarded-For'],
		'host': request.headers['Host'],
		'user-agent': request.headers['User-Agent']
	}

	return jsonify(resp)

@app.route('/flask-health-check')
def flask_health_check():
	return "success"
