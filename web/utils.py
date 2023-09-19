from app import (create_app, ALLOWED_IMAGE_EXTENSIONS)
from db import get_db
from mutagen.id3 import ID3, APIC


def get_image_extension(filename):
    return filename.rsplit('.', 1)[1].lower()

def allowed_image_file(filename):
    return '.' in filename and get_image_extension(filename) in ALLOWED_IMAGE_EXTENSIONS

def convert_mixtape(youtube_ids, mixtape_url):
    import os
    import shutil
    from yt_dlp import YoutubeDL
    from pydub import AudioSegment

    app = create_app()

    print('created app');

    mixtape = None
    with app.app_context():
        mixtape = get_db().execute(
            'SELECT m.art, m.title, m.body, m.created, m.author_id'
            ' FROM mixtape m'
            ' WHERE m.url = ?',
            (mixtape_url,)
        ).fetchone()

    # TODO: Rewrite using os.path.join()
    rip_directory = './youtube_rips/' + mixtape_url + '/'

    if os.path.isdir(rip_directory):
        shutil.rmtree(rip_directory)

    tracklist_path = os.path.join(app.config['MIXES_FOLDER'], mixtape_url + "-tracklist.txt")
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
        'outtmpl': {'default': '%(autonumber)s %(title)s.%(ext)s',},
        'print_to_file': {'post_process': [('%(autonumber)s - %(title)s', tracklist_path)]}
    }

    print('going to download');

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download(youtube_ids)

    print('downloaded all');

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

    print('mixed tracks');

    mixtape_path = os.path.join(app.config['MIXES_FOLDER'], mixtape_url + ".mp3")
    tracklist = open(tracklist_path, 'r')
    tracklist_text = mixtape['title'] + '\n\n' + tracklist.read() + '\n\n' + 'created at mixtapegarden.com'
    tracklist.close()

    mixed_tracks.export(mixtape_path, format="mp3", bitrate="320k")

    # TODO: Use mutagen to add tracklist to description as well as artist and album
    tags = ID3(mixtape_path)
    art_path = os.path.join(app.config['MIXTAPE_ART_FOLDER'], mixtape['art'])
    with open(art_path, 'rb') as art:
        tags.add(
            APIC(
                encoding=3,
                mime='image/png', # TODO: Convert image into PNG if not already. Also ensure there _is_ art
                type=3, # 3 is for the cover image
                desc=u'Cover',
                data=art.read()
            )
        )
    tags.save(v2_version=3)

    print('exported tape');

    if os.path.isdir(rip_directory):
        shutil.rmtree(rip_directory)

    with app.app_context():
        db = get_db()
        db.execute(
            'UPDATE mixtape SET converted = ?'
            ' WHERE url = ?',
            (True, mixtape_url)
        )
        db.commit()

    print('marked as converted');
