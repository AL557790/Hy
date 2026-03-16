import subprocess
import sys
import threading
import time
import requests

def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import flask
except ImportError:
    install("flask")

try:
    import yt_dlp
except ImportError:
    install("yt-dlp")

try:
    import requests
except ImportError:
    install("requests")

from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import uuid

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route("/")
def home():
    return {"status": "Server is running", "endpoint": "/download", "method": "POST"}

@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    filename = str(uuid.uuid4()) + ".mp4"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": filepath,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/favicon.ico")
def favicon():
    return "", 204

def self_ping():
    while True:
        try:
            requests.get("https://hy-z1b1.onrender.com/")
        except:
            pass
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=self_ping).start()
    app.run(host="0.0.0.0", port=5000)