import os

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

bp = Blueprint("mixtape", __name__)

redis = Redis(host='redis', port=6379)
# redis = Redis()  # For testing outside of docker
job_queue = Queue(connection=redis)


@bp.route("/")
def index():
    db = get_db()
    logged_in_uid = -1
    if g.user:
        logged_in_uid = g.user['id']
    mixtapes = db.execute(
        "SELECT m.id, m.url, m.art, m.title, m.body, m.created, m.author_id, m.locked, m.converted, m.hidden, u.username, u.avatar, COUNT(t.mixtape_id) as track_count"
        " FROM mixtape m"
        " INNER JOIN user u ON m.author_id = u.id"
        " LEFT JOIN track t ON m.id = t.mixtape_id"
        " WHERE m.hidden = 0 OR m.author_id = ?"
        " GROUP BY m.id"
        " ORDER BY m.created DESC",
        (logged_in_uid,)
    ).fetchall()
    # mixtapes_per_row = 2
    # mixtapes_in_rows = [mixtapes[i:i + mixtapes_per_row] for i in range(0, len(mixtapes), mixtapes_per_row)]
    return render_template(
        "mixtape/index.html", mixtapes=mixtapes, max_tracks=TRACKS_PER_MIXTAPE
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
        hidden = False
        if "hidden" in request.form:
            hidden = True
        url = get_uuid()
        error = None

        if not title:
            error = "Title is required."

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

        if not art:
            error = "Art is required."

        if error is not None:
            flash(error, FLASH_ERROR)
        else:
            db = get_db()
            db.execute(
                "INSERT INTO mixtape (title, body, author_id, url, art, hidden)"
                " VALUES (?, ?, ?, ?, ?, ?)",
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
            hidden = False
            if "hidden" in request.form:
                hidden = True
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
            "SELECT m.id, m.url, m.art, m.locked, m.converted, m.title, m.body, m.created, m.author_id, m.hidden, u.username, u.avatar, COUNT(t.mixtape_id) AS track_count"
            " FROM mixtape m"
            " INNER JOIN user u ON m.author_id = u.id"
            " LEFT JOIN track t ON m.id = t.mixtape_id"
            " WHERE m.url = ?"
            " GROUP BY m.id",
            (url,),
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
                youtube_id = get_youtube_id(youtube_url)
            except ValueError:
                error = "Not a valid YouTube URL."

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

    if mixtape["locked"]:
        error = "Mixtape is locked and cannot be converted."
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


def get_youtube_id(url):
    if url.startswith(("youtu", "www")):
        url = "http://" + url

    query = urlparse(url)

    if "youtube" in query.hostname:
        if query.path == "/watch":
            return parse_qs(query.query)["v"][0]
        if query.path.startswith(("/embed/", "/v/")):
            return query.path.split("/")[2]
    elif "youtu.be" in query.hostname:
        return query.path[1:]
    else:
        raise ValueError
