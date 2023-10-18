import os

from flask import Blueprint
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, send_from_directory, current_app
)

from db import get_db
from app import ALLOWED_IMAGE_EXTENSIONS
from utils import (get_image_extension, allowed_image_file)

bp = Blueprint('user', __name__)

@bp.route('/user/<username>', methods=('GET', 'POST'))
def view(username):
    user = get_db().execute(
        'SELECT u.id, u.username, u.avatar'
        ' FROM user u'
        ' WHERE u.username = ?',
        (username,)
    ).fetchone()

    if user is None:
        abort(404, f"User with username {username} doesn't exist.")

    if request.method == 'POST':
        error = None
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename == '':
                error = 'No image file attached.'
            elif not allowed_image_file(file.filename):
                error = 'Image file type not allowed. Allowed image types are: ' + ', '.join(ALLOWED_IMAGE_EXTENSIONS)
            else:
                avatar = username + '.' + get_image_extension(file.filename)
                if user['avatar']:
                    old_filename = os.path.join(current_app.config['USER_AVATAR_FOLDER'], user['avatar'])
                    if os.path.exists(old_filename):
                        os.remove(old_filename)
                file.save(os.path.join(current_app.config['USER_AVATAR_FOLDER'], avatar))

                db = get_db()
                db.execute(
                    'UPDATE user SET avatar = ?'
                    ' WHERE id = ?',
                    (avatar, user['id'])
                )
                db.commit()
                return redirect(url_for('user.view', username=user['username']))

        if error is not None:
            flash(error)

    return render_template('user/view.html', user=user)

