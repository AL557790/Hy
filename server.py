import subprocess, sys, threading, time, requests, os, uuid, glob, traceback, re

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for pkg in ["flask", "yt-dlp", "flask-cors", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        install(pkg)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_methods": ["GET","POST","OPTIONS"], "allow_headers": ["Content-Type"]}})

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
SERVER_URL = "https://hy-z1b1.onrender.com"

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

def fix_url(url):
    try:
        if any(x in url for x in ["facebook.com/share", "web.facebook.com", "fb.watch", "vm.tiktok", "t.co", "youtu.be"]):
            s = requests.Session()
            s.headers["User-Agent"] = UA_DESKTOP
            r = s.get(url, allow_redirects=True, timeout=15)
            return r.url.split('?')[0] if '?' in r.url else r.url
    except Exception as e:
        print(f"fix_url error: {e}")
    return url

def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url or "vt.tiktok.com" in url: return "tiktok"
    if "instagram.com" in url or "instagr.am" in url: return "instagram"
    if "twitter.com" in url or "x.com" in url or "t.co" in url: return "twitter"
    if "facebook.com" in url or "fb.watch" in url: return "facebook"
    if "reddit.com" in url or "redd.it" in url or "v.redd.it" in url: return "reddit"
    return "generic"

def build_opts(platform, outtmpl, simulate=False):
    headers = {
        "User-Agent": UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    base = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "retries": 10,
        "fragment_retries": 10,
        "http_headers": headers,
        "extract_flat": False,
    }

    if simulate:
        base["simulate"] = True
        base["skip_download"] = True

    if platform == "youtube":
        base["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
    elif platform == "tiktok":
        headers["User-Agent"] = UA_MOBILE
        headers["Referer"] = "https://www.tiktok.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
    elif platform == "facebook":
        headers["Referer"] = "https://www.facebook.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
    elif platform == "instagram":
        headers["Referer"] = "https://www.instagram.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
    elif platform == "twitter":
        headers["Referer"] = "https://twitter.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
    else:
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    return base

def clean_title(t):
    if not t:
        return "video"
    return re.sub(r'[^\w\s\-\.]', '', t).strip()[:80] or "video"

@app.route("/")
def home():
    return jsonify({"status": "running"})

@app.route("/info", methods=["POST","OPTIONS"])
def info():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    url = fix_url(url)
    plat = detect_platform(url)

    try:
        opts = build_opts(plat, "/tmp/info_tmp", simulate=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=False)

        if not info_data:
            return jsonify({"error": "Failed to fetch video info"}), 500

        formats, seen = [], set()

        for f in info_data.get("formats", []):
            vcodec = f.get("vcodec","none")
            ext = f.get("ext","")
            height = f.get("height")

            if plat == "youtube":
                if vcodec == "none":
                    continue
                if ext not in ("mp4","webm","m4v"):
                    continue
            else:
                if vcodec == "none":
                    continue

            key = f"{height}p_{f.get('format_id','')}" if height else f.get("format_id","")
            if key in seen:
                continue

            seen.add(key)

            formats.append({
                "id": f.get("format_id"),
                "ext": ext or "mp4",
                "height": height,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "format_note": f.get("format_note","")
            })

        formats.sort(key=lambda x: x.get("height") or 0, reverse=True)

        return jsonify({
            "title": info_data.get("title","Untitled"),
            "thumbnail": info_data.get("thumbnail"),
            "duration": info_data.get("duration"),
            "platform": plat,
            "formats": formats[:10]
        })

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)[:200]}), 500

@app.route("/download", methods=["POST","OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    fmt = data.get("format", "best")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    url = fix_url(url)
    plat = detect_platform(url)

    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid)

    opts = build_opts(plat, path + ".%(ext)s")
    opts["format"] = fmt

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=True)

        files = glob.glob(path + ".*")

        if not files:
            return jsonify({"error": "File not found"}), 500

        final_path = max(files, key=os.path.getsize)
        ext = os.path.splitext(final_path)[1].lstrip('.') or "mp4"
        title = clean_title(info_data.get("title") if info_data else None)

        return send_file(
            final_path,
            as_attachment=True,
            download_name=f"{title}.{ext}",
            mimetype=f"video/{ext}"
        )

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)[:200]}), 500

def delete_old():
    while True:
        try:
            now = time.time()
            for f in glob.glob(os.path.join(DOWNLOAD_FOLDER,"*")):
                if os.path.isfile(f) and now - os.path.getmtime(f) > 600:
                    os.remove(f)
        except:
            pass
        time.sleep(60)

def keep_alive():
    while True:
        try:
            requests.get(SERVER_URL, timeout=8)
        except:
            pass
        time.sleep(300)

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=delete_old, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)