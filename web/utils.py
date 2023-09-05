from app import (create_app, ALLOWED_IMAGE_EXTENSIONS)
from db import get_db

def get_image_extension(filename):
    return filename.rsplit('.', 1)[1].lower()

def allowed_image_file(filename):
    return '.' in filename and get_image_extension(filename) in ALLOWED_IMAGE_EXTENSIONS

def convert_mixtape(youtube_ids, mixtape_id, mixtape_url):
    import os
    import shutil
    from yt_dlp import YoutubeDL
    from pydub import AudioSegment

    # TODO: Rewrite using os.path.join()
    rip_directory = './youtube_rips/' + mixtape_url + '/'

    if os.path.isdir(rip_directory):
        shutil.rmtree(rip_directory)

    ydl_opts = {
        'paths': {
            'home': rip_directory,
            'temp': './temp',
        },
        'format': 'm4a/bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
        }],
        'outtmpl': {'default': '%(autonumber)s %(title)s.%(ext)s',}
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download(youtube_ids)

    all_tracks = []
    for filename in sorted(os.listdir(rip_directory)):
        if filename.endswith('.wav'):
            track = AudioSegment.from_file(rip_directory + filename)
            all_tracks.append(track)

    default_crossfade_time = 10 * 1000

    mixed_tracks = None
    for i, track in enumerate(all_tracks):
        if mixed_tracks == None:
            mixed_tracks = track
        else:
            last_track_length = len(all_tracks[i - 1])
            next_track_length = len(all_tracks[i])
            if min(last_track_length, next_track_length) < 30000:
                # Don't crossfade in or out of tracks shorter than 30 seconds
                crossfade_time = min(100, last_track_length, next_track_length)
            else:
                crossfade_time = min(
                    default_crossfade_time,
                    last_track_length / 3,
                    next_track_length / 3,
                )
            mixed_tracks = mixed_tracks.append(track, crossfade=crossfade_time)

    app = create_app()

    mixtape_path = os.path.join(app.config['MIXES_FOLDER'], mixtape_url + ".mp3")
    mixed_tracks.export(mixtape_path, format="mp3", bitrate="320k")

    if os.path.isdir(rip_directory):
        shutil.rmtree(rip_directory)

    with app.app_context():
        db = get_db()
        db.execute(
            'UPDATE mixtape SET converted = ?'
            ' WHERE id = ?',
            (True, mixtape_id)
        )
        db.commit()

