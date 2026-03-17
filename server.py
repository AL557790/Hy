import subprocess
import sys
import threading
import time
import requests
import os
import uuid
import glob

def install(package):
    subprocess.check_call([sys.executable,"-m","pip","install",package])

try:
    import flask
except:
    install("flask")

try:
    import yt_dlp
except:
    install("yt-dlp")

try:
    from flask_cors import CORS
except:
    install("flask-cors")
    from flask_cors import CORS

from flask import Flask, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

BOT_URL = "https://hy-z1b1.onrender.com"


@app.route("/")
def home():
    return {
        "status": "running",
        "supported": [
            "YouTube",
            "Facebook",
            "Instagram",
            "TikTok"
        ],
        "endpoints": ["/info", "/download"]
    }


@app.route("/info", methods=["POST", "OPTIONS"])
def info():
    if request.method == "OPTIONS":
        return '', 204

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "no url"}), 400

    try:
        ydl_opts = {
            "quiet": True,
            "nocheckcertificate": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.facebook.com/"
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info["formats"]:
            if f.get("ext"):
                formats.append({
                    "id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "height": f.get("height"),
                    "filesize": f.get("filesize")
                })

        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats
        })

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return '', 204

    data = request.json
    url = data.get("url")
    format_id = data.get("format", "best")

    if not url:
        return jsonify({"error": "no url"}), 400

    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid)

    ydl_opts = {
        "format": format_id,
        "outtmpl": path + ".%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,

        # مهم لفيسبوك
        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.facebook.com/"
        },

        "geo_bypass": True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        ext = info["ext"]
        final = path + "." + ext

        return send_file(final, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)})


def delete_old_files():
    while True:
        files = glob.glob(DOWNLOAD_FOLDER + "/*")
        now = time.time()

        for f in files:
            if os.path.isfile(f):
                if now - os.path.getmtime(f) > 600:
                    os.remove(f)

        time.sleep(60)


def ping():
    while True:
        try:
            requests.get(BOT_URL)
            print("Ping OK")
        except:
            print("Ping failed")

        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=ping).start()
    threading.Thread(target=delete_old_files).start()

    app.run(host="0.0.0.0", port=5000)