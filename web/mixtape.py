import os
import math
import re
from datetime import timedelta

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
    send_from_directory,
    current_app,
)

from werkzeug.exceptions import abort

from app import (
    TRACKS_PER_MIXTAPE,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_MIXTAPE_TITLE_LENGTH,
    MAX_MIXTAPE_DESCRIPTION_LENGTH,
    MAX_TRACK_DESCRIPTION_LENGTH,
    FLASH_ERROR,
    FLASH_SUCCESS,
    MIXTAPES_PER_PAGE,
    YOUTUBE_API_KEY
)
from auth import login_required
from db import get_db
from utils import (
    convert_mixtape,
    get_image_extension,
    allowed_image_file,
    owns_mixtape,
    owns_track,
)

import shortuuid
from urllib.parse import urlparse, parse_qs

from rq import Queue
from redis import Redis

from pyyoutube import Api

youtube_api = Api(api_key=YOUTUBE_API_KEY)

bp = Blueprint("mixtape", __name__)

redis = Redis(host='redis', port=6379)
# redis = Redis()  # For testing outside of docker
job_queue = Queue(connection=redis)

def get_logged_in_uid():
    logged_in_uid = -1
    if g.user:
        logged_in_uid = g.user['id']
    return logged_in_uid

@bp.route("/")
def index():
    db = get_db()
    page = int(request.args.get('page') or 0)
    mixtape_filter = request.args.get('mixtape_filter')
    count_args = (get_logged_in_uid(),)
    count_query = "SELECT COUNT(*) FROM mixtape m WHERE (m.hidden = 0 OR m.author_id = ?)"
    if mixtape_filter == "mytapes":
        count_query += " AND m.author_id = ?"
        count_args = (get_logged_in_uid(), get_logged_in_uid())
    elif mixtape_filter == "favorites":
        count_query = "SELECT COUNT(*) FROM mixtape m INNER JOIN favorite f ON (m.id = f.mixtape_id AND f.user_id = ?) WHERE (m.hidden = 0 OR m.author_id = ?)"
        count_args = (get_logged_in_uid(), get_logged_in_uid())
    elif mixtape_filter == "completed":
        count_query += " AND m.converted = 1"
    elif mixtape_filter == "unfinished":
        count_query += " AND m.converted = 0"
    mixtape_count = db.execute(count_query, count_args).fetchone()

    query = "SELECT m.id, m.url, m.art, m.title, m.body, m.author_id, m.locked, m.converted, m.hidden, u.username, u.avatar, COUNT(t.mixtape_id) as track_count, f.id as has_fav"
    query += " FROM mixtape m"
    query += " INNER JOIN user u ON m.author_id = u.id"
    query += " LEFT JOIN track t ON m.id = t.mixtape_id"
    args = (get_logged_in_uid(), get_logged_in_uid(), MIXTAPES_PER_PAGE, page * MIXTAPES_PER_PAGE)
    if mixtape_filter == "favorites":
        query += " INNER JOIN favorite f ON (m.id = f.mixtape_id AND f.user_id = ?)"
    else:
        query += " LEFT JOIN favorite f ON (m.id = f.mixtape_id AND f.user_id = ?)"
    query += " WHERE (m.hidden = 0 OR m.author_id = ?)"
    if mixtape_filter == "mytapes":
        query += " AND m.author_id = ?"
        args = (get_logged_in_uid(), get_logged_in_uid(), get_logged_in_uid(), MIXTAPES_PER_PAGE, page * MIXTAPES_PER_PAGE)
    elif mixtape_filter == "completed":
        query += " AND m.converted = 1"
    elif mixtape_filter == "unfinished":
        query += " AND m.converted = 0"
    query += " GROUP BY m.id"
    if mixtape_filter == "favorites":
        query += " ORDER BY f.created DESC "
    else:
        query += " ORDER BY m.updated DESC "
    query += " LIMIT ? OFFSET ?"
    mixtapes = db.execute(query, args).fetchall()
    prev_page = page - 1
    show_prev_page = prev_page >= 0
    next_page = page + 1
    show_next_page = mixtape_count[0] > next_page * MIXTAPES_PER_PAGE
    total_pages = math.ceil(mixtape_count[0] / MIXTAPES_PER_PAGE)
    total_pages = max(total_pages, 1)
    return render_template(
        "mixtape/index.html", mixtapes=mixtapes, max_tracks=TRACKS_PER_MIXTAPE,
        prev_page=prev_page, next_page=next_page, show_prev_page=show_prev_page, show_next_page=show_next_page, mixtape_filter=mixtape_filter,
        page=page + 1, total_pages=total_pages
    )


@bp.route("/create", methods=("GET", "POST"))
@login_required
def create():
    if request.method == "POST":
        if g.user is None:
            abort(403)

        title = request.form["title"]
        title = title[:MAX_MIXTAPE_TITLE_LENGTH]
        body = request.form["body"]
        body = body[:MAX_MIXTAPE_DESCRIPTION_LENGTH]
        hidden = True
        if "isPublic" in request.form:
            hidden = False
        url = get_uuid()
        error = None

        art = None
        if "art" in request.files:
            file = request.files["art"]
            if allowed_image_file(file.filename):
                art = url + "." + get_image_extension(file.filename)
                file.save(os.path.join(current_app.config["MIXTAPE_ART_FOLDER"], art))
            else:
                error = (
                    "Image file type not allowed. Allowed image types are: "
                    + ", ".join(ALLOWED_IMAGE_EXTENSIONS)
                )

        if not title:
            error = "Title is required."
        elif not art:
            error = "Art is required."

        if error is not None:
            flash(error, FLASH_ERROR)
        else:
            db = get_db()
            db.execute(
                "INSERT INTO mixtape (title, body, author_id, url, art, hidden, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (title, body, g.user["id"], url, art, hidden),
            )
            db.commit()
            flash("Created new mixtape.", FLASH_SUCCESS)

            return redirect(url_for("mixtape.view", url=url))

    return render_template(
        "mixtape/create.html",
        MAX_MIXTAPE_TITLE_LENGTH=MAX_MIXTAPE_TITLE_LENGTH,
        MAX_MIXTAPE_DESCRIPTION_LENGTH=MAX_MIXTAPE_DESCRIPTION_LENGTH,
    )


@bp.route("/edit/<url>", methods=("GET", "POST"))
@login_required
def edit(url):
    mixtape = get_mixtape_by_url(url)
    if request.method == "POST":
        if not owns_mixtape(g.user, mixtape):
            abort(403)
        if "title" in request.form:
            title = request.form["title"]
            title = title[:MAX_MIXTAPE_TITLE_LENGTH]
            body = request.form["body"]
            body = body[:MAX_MIXTAPE_DESCRIPTION_LENGTH]
            hidden = True
            if "isPublic" in request.form:
                hidden = False
            error = None

            if not title:
                error = "Title is required."

            art = None
            if "art" in request.files:
                file = request.files["art"]
                if file.filename != "":
                    if allowed_image_file(file.filename):
                        art = url + "." + get_image_extension(file.filename)
                        file.save(
                            os.path.join(current_app.config["MIXTAPE_ART_FOLDER"], art)
                        )
                    else:
                        error = (
                            "Image file type not allowed. Allowed image types are: "
                            + ", ".join(ALLOWED_IMAGE_EXTENSIONS)
                        )

            if error is not None:
                flash(error, FLASH_ERROR)
            else:
                db = get_db()
                if art is None:
                    db.execute(
                        "UPDATE mixtape SET title = ?, body = ?, hidden = ?"
                        " WHERE url = ?",
                        (title, body, hidden, url),
                    )
                else:
                    db.execute(
                        "UPDATE mixtape SET title = ?, body = ?, art = ?, hidden = ?"
                        " WHERE url = ?",
                        (title, body, art, hidden, url),
                    )
                db.commit()
                flash("Updated mixtape.", FLASH_SUCCESS)

                return redirect(url_for("mixtape.view", url=url))
        elif "deleteMixtape" in request.form:
            db = get_db()
            db.execute("DELETE FROM mixtape " " WHERE id = ?", (mixtape["id"],))
            db.execute("DELETE FROM track " " WHERE mixtape_id = ?", (mixtape["id"],))
            db.commit()

            mixtape_path = os.path.join(
                current_app.config["MIXES_FOLDER"], mixtape["url"] + ".mp3"
            )
            if os.path.exists(mixtape_path):
                os.remove(mixtape_path)

            flash("Deleted mixtape.", FLASH_SUCCESS)
            return redirect(url_for("mixtape.index"))

    return render_template(
        "mixtape/edit.html",
        mixtape=mixtape,
        MAX_MIXTAPE_TITLE_LENGTH=MAX_MIXTAPE_TITLE_LENGTH,
        MAX_MIXTAPE_DESCRIPTION_LENGTH=MAX_MIXTAPE_DESCRIPTION_LENGTH,
    )


def get_uuid():
    return shortuuid.ShortUUID().random(length=8)


def get_mixtape_by_url(url):
    mixtape = (
        get_db()
        .execute(
            "SELECT m.id, m.url, m.art, m.locked, m.converted, m.title, m.body, m.created, m.author_id, m.hidden, u.username, u.avatar, COUNT(t.mixtape_id) AS track_count, f.id as has_fav"
            " FROM mixtape m"
            " INNER JOIN user u ON m.author_id = u.id"
            " LEFT JOIN track t ON m.id = t.mixtape_id"
            " LEFT JOIN favorite f ON (m.id = f.mixtape_id AND f.user_id = ?)"
            " WHERE m.url = ?"
            " GROUP BY m.id",
            (get_logged_in_uid(), url,),
        )
        .fetchone()
    )

    if mixtape is None:
        abort(404, f"Mixtape with URL {url} doesn't exist.")

    return mixtape


def get_tracks(mixtape_id):
    db = get_db()
    tracks = db.execute(
        "SELECT t.id, t.youtube_id, t.created, t.author_id, t.body, u.username, u.avatar"
        " FROM track t INNER JOIN user u ON t.author_id = u.id"
        " WHERE t.mixtape_id = ?"
        " ORDER BY t.created ASC",
        (mixtape_id,),
    ).fetchall()

    return tracks


def get_track(track_id):
    db = get_db()
    track = db.execute(
        "SELECT t.id, t.author_id, t.mixtape_id, t.youtube_id, t.created"
        " FROM track t"
        " WHERE t.id = ?",
        (track_id,),
    ).fetchone()

    if track is None:
        abort(404, f"Track with ID {track_id} doesn't exist.")

    return track


@bp.route("/<url>", methods=("GET", "POST"))
def view(url):
    mixtape = get_mixtape_by_url(url)
    tracks = get_tracks(mixtape["id"])
    one_track_from_full = mixtape["track_count"] == TRACKS_PER_MIXTAPE - 1
    if request.method == "POST":
        if "deleteTrack" in request.form:
            # Delete track from mixtape
            track = get_track(request.form["trackId"])
            if (
                mixtape["locked"]
                or not owns_track(g.user, track)
            ):
                abort(403)

            db = get_db()
            db.execute("DELETE FROM track " " WHERE id = ?", (track["id"],))
            db.commit()
            flash("Deleted track.", FLASH_SUCCESS)

            return redirect(url_for("mixtape.view", url=mixtape["url"]))
        if "youtubeUrl" in request.form:
            if g.user is None:
                abort(403)

            # Add track to mixtape
            youtube_url = request.form["youtubeUrl"]
            error = None

            if not youtube_url:
                error = "YouTube URL is required."

            try:
                youtube_id = validate_youtube_id(youtube_url)
                if len(youtube_id) != 11:
                    error = "Not a valid YouTube URL."
            except InvalidID:
                error = "Not a valid YouTube URL."
            except VideoTooLong:
                error = "Video too long. It must be under 20 minutes."

            if mixtape["locked"]:
                error = "Mixtape is locked and cannot be added to."

            if mixtape["track_count"] >= TRACKS_PER_MIXTAPE:
                error = "Mixtape is full and cannot be added to."

            track_description = request.form["trackBody"]
            track_description = track_description[:MAX_TRACK_DESCRIPTION_LENGTH]

            if error is not None:
                flash(error, FLASH_ERROR)
            else:
                db = get_db()

                db.execute(
                    "UPDATE mixtape SET updated = CURRENT_TIMESTAMP WHERE id = ?", (mixtape["id"], )
                )

                db.execute(
                    "INSERT INTO track (author_id, mixtape_id, youtube_id, body)"
                    " VALUES (?, ?, ?, ?)",
                    (g.user["id"], mixtape["id"], youtube_id, track_description),
                )
                db.commit()

                if mixtape["track_count"] == TRACKS_PER_MIXTAPE - 1:
                    # Convert mixtape
                    return redirect(url_for("mixtape.convert", url=mixtape["url"]))

                flash("Added track.", FLASH_SUCCESS)
                return redirect(url_for("mixtape.view", url=mixtape["url"]))

    return render_template(
        "mixtape/view.html",
        mixtape=mixtape,
        tracks=tracks,
        one_track_from_full=one_track_from_full,
        MAX_TRACK_DESCRIPTION_LENGTH=MAX_TRACK_DESCRIPTION_LENGTH,
        max_tracks=TRACKS_PER_MIXTAPE,
    )


@bp.route("/<url>/convert", methods=("GET", "POST"))
@login_required
def convert(url):
    mixtape = get_mixtape_by_url(url)
    tracks = get_tracks(mixtape["id"])

    error = None

    # if mixtape["locked"]:
        # error = "Mixtape is locked and cannot be converted."
    if mixtape["track_count"] != TRACKS_PER_MIXTAPE:
        error = "Mixtape does not have enough tracks to be converted."

    if error is not None:
        flash(error, FLASH_ERROR)
    else:
        db = get_db()
        db.execute(
            "UPDATE mixtape SET locked = ?" " WHERE id = ?", (True, mixtape["id"])
        )
        db.commit()

        youtube_ids = []
        for track in tracks:
            youtube_ids.append(track["youtube_id"])

        job_queue.enqueue(convert_mixtape, youtube_ids, mixtape["url"], job_timeout=600)

        flash("Added final track. Mixtape converting...", FLASH_SUCCESS)
        return redirect(url_for("mixtape.view", url=mixtape["url"]))

    return render_template("mixtape/update.html", mixtape=mixtape)


@bp.route("/<url>/download", methods=("GET", "POST"))
def download(url):
    mixtape = get_mixtape_by_url(url)
    return send_from_directory(
        os.path.join(
            os.path.dirname(current_app.instance_path),
            current_app.config["MIXES_FOLDER"],
        ),
        mixtape["url"] + ".mp3",
        as_attachment=True,
    )


@bp.route('/favorite')
def favorite():
    mixtape_id = request.args.get('mixtape_id')

    db = get_db()
    favorite = db.execute(
        "SELECT * FROM favorite WHERE user_id = ? AND mixtape_id = ?",
        (g.user["id"], mixtape_id),
    ).fetchone()

    if favorite:
        db.execute("DELETE FROM favorite WHERE id = ?", (favorite["id"],))
        db.commit()
    else:
        db.execute(
            "INSERT INTO favorite (user_id, mixtape_id)"
            " VALUES (?, ?)",
            (g.user["id"], mixtape_id),
        )
        db.commit()
    return "Successfully added " + mixtape_id


class InvalidID(Exception):
    pass

class VideoTooLong(Exception):
    pass

def validate_youtube_id(url):
    if url.startswith(("youtu", "www")):
        url = "http://" + url

    query = urlparse(url)

    youtube_id = None
    if "youtube" in query.hostname:
        if query.path == "/watch":
            youtube_id = parse_qs(query.query)["v"][0]
        if query.path.startswith(("/embed/", "/v/")):
            youtube_id = query.path.split("/")[2]
    elif "youtu.be" in query.hostname:
        youtube_id = query.path[1:]
    else:
        raise InvalidID

    video_by_id = youtube_api.get_video_by_id(video_id=youtube_id)
    if len(video_by_id.items) < 1:
        raise InvalidID

    duration_in_sec = get_seconds_from_timestamp(
        video_by_id.items[0].contentDetails.duration
    )
    if duration_in_sec > 20 * 60:
        raise VideoTooLong

    return youtube_id


def get_seconds_from_timestamp(ts):
    hours_pattern = re.compile(r'(\d+)H')
    minutes_pattern = re.compile(r'(\d+)M')
    seconds_pattern = re.compile(r'(\d+)S')
    hours_parse = hours_pattern.search(ts)
    minutes_parse = minutes_pattern.search(ts)
    seconds_parse = seconds_pattern.search(ts)
    minutes = int(minutes_parse.group(1)) if minutes_parse else 0
    hours  = int(hours_parse.group(1)) if hours_parse else 0
    seconds  = int(seconds_parse.group(1)) if seconds_parse else 0
    total_seconds = 60*60*hours + 60*minutes + seconds
    return total_seconds

