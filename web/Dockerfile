FROM python:3.10.19-alpine

# install deno
RUN curl -fsSL https://deno.land/install.sh | sh

# install gcc
RUN apk update
RUN apk add gcc ffmpeg

# get curl for healthchecks
RUN apk add curl

# permissions and nonroot user for tightened security
WORKDIR /home/app

# copy all the files to the container
COPY . .

# venv
ENV VIRTUAL_ENV=/home/app/venv

# python setup
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN export FLASK_APP=app.py
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
#RUN pip install -U https://github.com/coletdjnz/yt-dlp-youtube-oauth2/archive/refs/heads/master.zip
RUN pip install -U "yt-dlp[default]"

# define the port number the container should expose
EXPOSE 5000

RUN flask --app app init-db

# Overridden in compose.yaml; test standalone image with:
# docker build web -t standalone-web
# docker run -it -p5000:5000 standalone-web
CMD ["flask", "--app", "app", "run", "-h", "0.0.0.0", "-p", "5000"]
