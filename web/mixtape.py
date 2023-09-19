import os

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, send_from_directory, current_app
)

from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename

from app import TRACKS_PER_MIXTAPE
from auth import login_required
from db import get_db
from utils import (convert_mixtape, get_image_extension, allowed_image_file)

import shortuuid
from urllib.parse import urlparse, parse_qs

from rq import Queue
from redis import Redis

bp = Blueprint('mixtape', __name__)

# pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
# redis_conn = redis.Redis()
# job_queue = Queue(connection=redis_conn)
redis = Redis(host='redis', port=6379)
job_queue = Queue(connection=redis)

@bp.route('/')
def index():
    db = get_db()
    mixtapes = db.execute(
        'SELECT m.id, m.url, m.art, m.title, m.body, m.created, m.author_id, m.locked, m.converted, u.username, u.avatar, COUNT(t.mixtape_id) as track_count'
        ' FROM mixtape m'
        ' INNER JOIN user u ON m.author_id = u.id'
        ' LEFT JOIN track t ON m.id = t.mixtape_id'
        ' GROUP BY m.id'
        ' ORDER BY m.created DESC'
    ).fetchall()
    return render_template('mixtape/index.html', mixtapes=mixtapes)

@bp.route('/create', methods=('GET', 'POST'))
@login_required
def create():
    if request.method == 'POST':
        title = request.form['title']
        body = request.form['body']
        url = get_uuid()
        error = None

        if not title:
            error = 'Title is required.'

        art = None
        if 'art' in request.files:
            file = request.files['art']
            if allowed_image_file(file.filename):
                art = url + '.' + get_image_extension(file.filename)
                file.save(os.path.join(current_app.config['MIXTAPE_ART_FOLDER'], art))

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                'INSERT INTO mixtape (title, body, author_id, url, art)'
                ' VALUES (?, ?, ?, ?, ?)',
                (title, body, g.user['id'], url, art)
            )
            db.commit()

            return redirect(url_for('mixtape.view', url=url))

    return render_template('mixtape/create.html')

def get_uuid():
    # TODO: Ensure UUIDs are unique and don't conflict with other URLs
    return shortuuid.ShortUUID().random(length=8)

def get_mixtape_by_url(url, check_author=True):
    mixtape = get_db().execute(
        'SELECT m.id, m.url, m.art, m.locked, m.converted, m.title, m.body, m.created, m.author_id, u.username, u.avatar, COUNT(t.mixtape_id) AS track_count'
        ' FROM mixtape m'
        ' INNER JOIN user u ON m.author_id = u.id'
        ' LEFT JOIN track t ON m.id = t.mixtape_id'
        ' WHERE m.url = ?'
        ' GROUP BY m.id',
        (url,)
    ).fetchone()

    if mixtape is None:
        abort(404, f"Mixtape with URL {url} doesn't exist.")

    if check_author and (g.user is None or mixtape['author_id'] != g.user['id']):
        abort(403)

    return mixtape

def get_tracks(mixtape_id, check_author=True):
    db = get_db()
    tracks = db.execute(
        'SELECT t.id, t.youtube_id, t.created, t.author_id, u.username'
        ' FROM track t INNER JOIN user u ON t.author_id = u.id'
        ' WHERE t.mixtape_id = ?'
        ' ORDER BY t.created ASC',
        (mixtape_id,)
    ).fetchall()

    # TODO: Probably need to do some validation here

    return tracks

def get_track(track_id):
    db = get_db()
    track = db.execute(
        'SELECT t.id, t.author_id, t.mixtape_id, t.youtube_id, t.created'
        ' FROM track t'
        ' WHERE t.id = ?',
        (track_id,)
    ).fetchone()

    if track is None:
        abort(404, f"Track with ID {track_id} doesn't exist.")

    return track
    # TODO: Probably need to do some validation here

@bp.route('/<url>', methods=('GET', 'POST'))
def view(url):
    mixtape = get_mixtape_by_url(url, False) # TODO: False here should be based on if the mix is public or not
    tracks = get_tracks(mixtape['id'])
    if request.method == 'POST':
        if 'deleteMixtape' in request.form:
            # Delete mixtape
            if g.user is None or mixtape['author_id'] != g.user['id']:
                abort(403)

            db = get_db()
            db.execute(
                'DELETE FROM mixtape '
                ' WHERE id = ?',
                (mixtape['id'],)
            )
            db.execute(
                'DELETE FROM track '
                ' WHERE mixtape_id = ?',
                (mixtape['id'],)
            )
            db.commit()

            mixtape_path = os.path.join(current_app.config['MIXES_FOLDER'], mixtape['url'] + '.mp3')
            if os.path.exists(mixtape_path):
                os.remove(mixtape_path)

            return redirect(url_for('mixtape.index'))
        elif 'deleteTrack' in request.form:
            # Delete track from mixtape
            track = get_track(request.form['trackId'])
            if (
                g.user is None or
                mixtape['locked'] or
                (mixtape['author_id'] != g.user['id'] and track['author_id'] != g.user['id'])
            ):
                abort(403)

            db = get_db()
            db.execute(
                'DELETE FROM track '
                ' WHERE id = ?',
                (track['id'],)
            )
            db.commit()

            return redirect(url_for('mixtape.view', url=mixtape['url']))
        elif 'youtubeUrl' in request.form:
            # Add track to mixtape
            youtube_url = request.form['youtubeUrl']
            error = None

            if not youtube_url:
                error = 'YouTube URL is required.'

            try:
                youtube_id = get_youtube_id(youtube_url)
            except:
                error = "Not a valid YouTube URL."

            if mixtape['locked']:
                error = 'Mixtape is locked and cannot be added to.'

            if mixtape['track_count'] >= TRACKS_PER_MIXTAPE:
                error = 'Mixtape is full and cannot be added to.'

            if error is not None:
                flash(error)
            else:
                db = get_db()

                db.execute(
                    'INSERT INTO track (author_id, mixtape_id, youtube_id)'
                    ' VALUES (?, ?, ?)',
                    (g.user['id'], mixtape['id'], youtube_id)
                )
                db.commit()

                if mixtape['track_count'] == TRACKS_PER_MIXTAPE - 1:
                    # Convert mixtape
                    return redirect(url_for('mixtape.convert', url=mixtape['url']))
                else:
                    return redirect(url_for('mixtape.view', url=mixtape['url']))

    return render_template('mixtape/view.html', mixtape=mixtape, tracks=tracks)

@bp.route('/<url>/update', methods=('GET', 'POST'))
@login_required
def update(url):
    mixtape = get_mixtape_by_url(url)

    if request.method == 'POST':
        title = request.form['title']
        body = request.form['body']
        error = None

        if not title:
            error = 'Title is required.'

        art = None
        if 'art' in request.files:
            file = request.files['art']
            if allowed_image_file(file.filename):
                art = url + '.' + get_image_extension(file.filename)
                if mixtape['art']:
                    old_filename = os.path.join(current_app.config['MIXTAPE_ART_FOLDER'], mixtape['art'])
                    if os.path.exists(old_filename):
                        os.remove(old_filename)
                file.save(os.path.join(current_app.config['MIXTAPE_ART_FOLDER'], art))

        if error is not None:
            flash(error)
        else:
            db = get_db()
            if art:
                db.execute(
                    'UPDATE mixtape SET title = ?, body = ?, art = ?'
                    ' WHERE id = ?',
                    (title, body, art, mixtape['id'])
                )
            else:
                db.execute(
                    'UPDATE mixtape SET title = ?, body = ?'
                    ' WHERE id = ?',
                    (title, body, mixtape['id'])
                )
            db.commit()
            return redirect(url_for('mixtape.view', url=mixtape['url']))

    return render_template('mixtape/update.html', mixtape=mixtape)

@bp.route('/<url>/convert', methods=('GET', 'POST'))
@login_required
def convert(url):
    # TODO: Check you are the owner of the mixtape - this could be a decorator
    # TODO: Don't allow converting mixtapes that are locked or w/o 7 tracks
    mixtape = get_mixtape_by_url(url)
    tracks = get_tracks(mixtape['id'])

    error = None

    if mixtape['locked']:
        error = 'Mixtape is locked and cannot be converted.'

    if error is not None:
        flash(error)
    else:
        db = get_db()
        db.execute(
            'UPDATE mixtape SET locked = ?'
            ' WHERE id = ?',
            (True, mixtape['id'])
        )
        db.commit()

        youtube_ids = []
        for track in tracks:
            youtube_ids.append(track['youtube_id'])

        job = job_queue.enqueue(
            convert_mixtape,
            youtube_ids,
            mixtape['url']
        )

        return redirect(url_for('mixtape.view', url=mixtape['url']))

    return render_template('mixtape/update.html', mixtape=mixtape)

@bp.route('/<url>/download', methods=('GET', 'POST'))
def download(url):
    mixtape = get_mixtape_by_url(url, False) # TODO: False here should be based on if the mix is public or not
    return send_from_directory(
        os.path.join(os.path.dirname(current_app.instance_path), current_app.config['MIXES_FOLDER']),
        mixtape['url'] + '.mp3',
        as_attachment=True
    )
    # return redirect(url_for('mixtape.index'))

def get_youtube_id(url):
    if url.startswith(('youtu', 'www')):
        url = 'http://' + url

    query = urlparse(url)

    if 'youtube' in query.hostname:
        if query.path == '/watch':
            return parse_qs(query.query)['v'][0]
        elif query.path.startswith(('/embed/', '/v/')):
            return query.path.split('/')[2]
    elif 'youtu.be' in query.hostname:
        return query.path[1:]
    else:
        raise ValueError ## TODO: Don't throw ValueError

