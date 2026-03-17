import subprocess
import sys
import threading
import time
import requests
import os
import uuid
import glob
import traceback

def install(package):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    except Exception as e:
        print(f"Failed to install {package}: {e}")

# تثبيت المكتبات إذا لم تكن موجودة
for pkg in ["flask", "yt-dlp", "flask-cors", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        install(pkg)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)

# إعداد CORS بشكل صريح وقوي (هذا هو الحل الرئيسي لمشكلة Failed to fetch من HTML)
CORS(app, resources={
    r"/*": {
        "origins": "*",                     # للاختبار فقط - يمكنك لاحقاً تحديد نطاقات معينة
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"],
        "supports_credentials": False,
        "max_age": 86400                    # cache preflight لمدة يوم
    }
})

DOWNLOAD_FOLDER = "downloads"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

BOT_URL = "https://hy-z1b1.onrender.com"


def fix_facebook_share(url):
    if "facebook.com/share" in url or "web.facebook.com/share" in url:
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            r = session.get(url, allow_redirects=True, timeout=12)
            final_url = r.url
            if "?_rdc=1&_rdr" in final_url or "_fb_noscript=1" in final_url:
                final_url = final_url.split('?')[0]
            print(f"Fixed URL: {final_url}")
            return final_url
        except Exception as e:
            print(f"Error fixing URL: {e}")
            return url
    return url


@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "supported": ["YouTube", "Facebook", "Instagram", "TikTok"],
        "endpoints": ["/info", "/download"]
    })


@app.route("/info", methods=["POST", "OPTIONS"])
def info():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "no url provided"}), 400

    url = fix_facebook_share(url)

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "http_headers": {"User-Agent": "Mozilla/5.0"},
            "simulate": True,
            "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
            if f.get("ext"):
                formats.append({
                    "id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "height": f.get("height"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "format_note": f.get("format_note", "")
                })

        return jsonify({
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats[:15]
        })

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url = data.get("url")
    format_id = data.get("format", "best[ext=mp4]")

    if not url:
        return jsonify({"error": "no url provided"}), 400

    url = fix_facebook_share(url)

    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid)

    ydl_opts = {
        "format": format_id,
        "outtmpl": path + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "continuedl": True,
        "retries": 10,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.facebook.com/"
        },
        "merge_output_format": None if "best" in format_id else "mp4"
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        ext = info.get("ext", "mp4")
        final_path = path + "." + ext

        if not os.path.exists(final_path):
            return jsonify({"error": "file was not created"}), 500

        return send_file(
            final_path,
            as_attachment=True,
            download_name=f"{info.get('title', 'video')}.{ext}",
            mimetype="video/mp4"
        )

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


def delete_old_files():
    while True:
        try:
            files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*"))
            now = time.time()
            for f in files:
                if os.path.isfile(f) and now - os.path.getmtime(f) > 600:
                    try:
                        os.remove(f)
                    except:
                        pass
        except:
            pass
        time.sleep(60)


def keep_alive():
    while True:
        try:
            requests.get(BOT_URL, timeout=8)
            print("Keep-alive ping OK")
        except:
            print("Keep-alive ping failed")
        time.sleep(300)


if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=delete_old_files, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)