import os

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
    current_app,
)

from db import get_db
from app import ALLOWED_IMAGE_EXTENSIONS, FLASH_ERROR, FLASH_SUCCESS
from utils import get_image_extension, allowed_image_file
from werkzeug.exceptions import abort

bp = Blueprint("user", __name__)


@bp.route("/user/<username>", methods=("GET", "POST"))
def view(username):
    db = get_db()
    user = (
        db
        .execute(
            "SELECT u.id, u.username, u.avatar" " FROM user u"
            " WHERE u.username = ?",
            (username,),
        )
        .fetchone()
    )

    if user is None:
        abort(404, f"User with username {username} doesn't exist.")

    logged_in_uid = -1
    if g.user:
        logged_in_uid = g.user['id']

    mixtapes = (
        db
        .execute(
            "SELECT m.id, m.title, m.url, m.art, m.hidden, m.converted, m.updated FROM mixtape m WHERE m.author_id = ? AND (m.hidden = 0 OR m.author_id = ?) ORDER BY m.updated DESC",
            (user['id'], logged_in_uid,)
        )
        .fetchall()
    )

    complete_mixtapes = [m for m in mixtapes if not m['converted']]
    unfinished_mixtapes = [m for m in mixtapes if not m['converted']]

    favorites = (
        db
        .execute(
            "SELECT m.id, m.title, m.url FROM mixtape m INNER JOIN favorite f ON (m.id = f.mixtape_id AND f.user_id = ?) WHERE (m.hidden = 0 OR m.author_id = ?) ORDER BY f.created DESC",
            (user['id'], logged_in_uid,)
        )
        .fetchall()
    )

    if request.method == "POST":
        if g.user["id"] != user["id"]:
            abort(403)

        error = None
        if "avatar" in request.files:
            file = request.files["avatar"]
            if file.filename == "":
                error = "No image file attached."
            elif not allowed_image_file(file.filename):
                error = (
                    "Image file type not allowed. Allowed image types are: "
                    + ", ".join(ALLOWED_IMAGE_EXTENSIONS)
                )
            else:
                avatar = username + "." + get_image_extension(file.filename)
                if user["avatar"]:
                    old_filename = os.path.join(
                        current_app.config["USER_AVATAR_FOLDER"], user["avatar"]
                    )
                    if os.path.exists(old_filename):
                        os.remove(old_filename)
                file.save(
                    os.path.join(current_app.config["USER_AVATAR_FOLDER"], avatar)
                )

                db = get_db()
                db.execute(
                    "UPDATE user SET avatar = ?" " WHERE id = ?", (avatar, user["id"])
                )
                db.commit()
                flash("Updated avatar.", FLASH_SUCCESS)
                return redirect(url_for("user.view", username=user["username"], mixtapes=mixtapes, complete_mixtapes=complete_mixtapes, unfinished_mixtapes=unfinished_mixtapes, favorites=favorites))

        if error is not None:
            flash(error, FLASH_ERROR)

    return render_template("user/view.html", user=user, mixtapes=mixtapes, complete_mixtapes=complete_mixtapes, unfinished_mixtapes=unfinished_mixtapes, favorites=favorites)
