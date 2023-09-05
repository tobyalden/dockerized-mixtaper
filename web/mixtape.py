import os

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, send_from_directory, current_app
)

from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename

# from flaskr.auth import login_required
from db import get_db
# from flaskr.utils import (convert_mixtape, get_image_extension, allowed_image_file)

import shortuuid
from urllib.parse import urlparse, parse_qs

from rq import Queue
import redis

bp = Blueprint('mixtape', __name__)

pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
redis_conn = redis.Redis()
job_queue = Queue(connection=redis_conn)

@bp.route('/')
def index():
    db = get_db()
    mixtapes = db.execute(
        'SELECT m.id, m.url, m.art, m.title, m.body, m.created, m.author_id, u.username, u.avatar, count(t.mixtape_id) as track_count'
        ' FROM mixtape m'
        ' LEFT JOIN user u ON m.author_id = u.id'
        ' LEFT JOIN track t ON m.id = t.mixtape_id'
        ' GROUP BY m.id'
        ' ORDER BY m.created DESC'
    ).fetchall()
    return 'Hello world!'
    # return render_template('mixtape/index.html', mixtapes=mixtapes)
