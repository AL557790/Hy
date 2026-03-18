import subprocess, sys, threading, time, requests, os, uuid, glob, traceback, re

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL)

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

UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"

def fix_url(url):
    try:
        if any(x in url for x in ["facebook.com/share", "web.facebook.com", "fb.watch", "vm.tiktok", "t.co"]):
            s = requests.Session()
            s.headers["User-Agent"] = UA_CHROME
            r = s.get(url, allow_redirects=True, timeout=15)
            final = r.url.split('?')[0] if any(x in r.url for x in ["_rdc=1","_fb_noscript","fbclid"]) else r.url
            print(f"Resolved: {url} -> {final}")
            return final
    except Exception as e:
        print(f"fix_url error: {e}")
    return url

def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url: return "tiktok"
    if "instagram.com" in url: return "instagram"
    if "twitter.com" in url or "x.com" in url: return "twitter"
    if "facebook.com" in url or "fb.watch" in url: return "facebook"
    if "reddit.com" in url or "redd.it" in url: return "reddit"
    return "generic"

def build_opts(platform, outtmpl, sim=False):
    h = {"User-Agent": UA_CHROME}
    base = {
        "outtmpl": outtmpl, "quiet": True, "no_warnings": True,
        "noplaylist": True, "nocheckcertificate": True, "geo_bypass": True,
        "retries": 10, "fragment_retries": 10,
        "http_headers": h,
    }
    if sim: base["simulate"] = True

    if platform == "youtube":
        # بدون ffmpeg: نختار فيديو كامل mp4 مدمج مسبقاً
        base["format"] = "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "tiktok":
        h["User-Agent"] = UA_MOBILE
        h["Referer"] = "https://www.tiktok.com/"
        h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        # تيك توك: نأخذ أي فورمات متاح
        base["format"] = "best[ext=mp4]/bestvideo[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "facebook":
        h["Referer"] = "https://www.facebook.com/"
        h["Accept-Language"] = "en-US,en;q=0.5"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "instagram":
        h["Referer"] = "https://www.instagram.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "twitter":
        h["Referer"] = "https://twitter.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    else:
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    return base

def clean_title(t):
    if not t: return "video"
    return re.sub(r'[^\w\s\-]', '', t).strip()[:60] or "video"

@app.route("/")
def home():
    return jsonify({"status": "running"})

@app.route("/info", methods=["POST","OPTIONS"])
def info():
    if request.method == "OPTIONS": return '', 204
    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    if not url: return jsonify({"error": "لم يتم توفير الرابط"}), 400

    url = fix_url(url)
    plat = detect_platform(url)

    try:
        opts = build_opts(plat, "/tmp/info_tmp", sim=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=False)

        formats, seen = [], set()
        all_fmts = info_data.get("formats", [])
        for f in all_fmts:
            vcodec = f.get("vcodec","none")
            acodec = f.get("acodec","none")
            ext = f.get("ext","")
            h = f.get("height")
            # يوتيوب: خذ فقط الفورمات المدمجة (فيديو+صوت معاً) أو mp4
            if plat == "youtube":
                if vcodec == "none" or acodec == "none": continue
                if ext not in ("mp4","webm"): continue
            else:
                if vcodec == "none": continue
            key = str(h) if h else f.get("format_note","")
            if not key or key in seen: continue
            seen.add(key)
            formats.append({
                "id": f.get("format_id"),
                "ext": ext or "mp4",
                "height": h,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "format_note": f.get("format_note","")
            })
        formats.sort(key=lambda x: x.get("height") or 0, reverse=True)

        return jsonify({
            "title": info_data.get("title"),
            "thumbnail": info_data.get("thumbnail"),
            "duration": info_data.get("duration"),
            "platform": plat,
            "formats": formats[:8]
        })
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route("/download", methods=["POST","OPTIONS"])
def download():
    if request.method == "OPTIONS": return '', 204
    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    fmt = data.get("format", "best[ext=mp4]/best")
    if not url: return jsonify({"error": "لم يتم توفير الرابط"}), 400

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
        if not files: return jsonify({"error": "فشل في إنشاء الملف"}), 500

        final_path = max(files, key=os.path.getsize)
        ext = os.path.splitext(final_path)[1].lstrip('.') or "mp4"
        title = clean_title(info_data.get("title") if info_data else None)
        print(f"[{plat}] {final_path} — {os.path.getsize(final_path)//1024}KB")

        return send_file(final_path, as_attachment=True, download_name=f"{title}.{ext}", mimetype="video/mp4")
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

def delete_old():
    while True:
        try:
            now = time.time()
            for f in glob.glob(os.path.join(DOWNLOAD_FOLDER,"*")):
                if os.path.isfile(f) and now - os.path.getmtime(f) > 600:
                    os.remove(f)
        except: pass
        time.sleep(60)

def keep_alive():
    while True:
        try: requests.get(SERVER_URL, timeout=8)
        except: pass
        time.sleep(300)

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=delete_old, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
