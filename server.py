import subprocess, sys, threading, time, requests, os, uuid, glob, traceback, re

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL)

# تثبيت / تحديث المكتبات
for pkg in ["flask", "yt-dlp", "flask-cors", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        install(pkg)

# تحديث yt-dlp دائمًا
subprocess.call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], stdout=subprocess.DEVNULL)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

SERVER_URL = "https://hy-z1b1.onrender.com"

UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile Safari/604.1"

# ===============================
# إصلاح الروابط المختصرة
# ===============================
def fix_url(url):
    try:
        if any(x in url for x in ["vm.tiktok", "fb.watch", "t.co"]):
            r = requests.get(url, allow_redirects=True, timeout=10)
            return r.url
    except:
        pass
    return url

# ===============================
# تحديد المنصة
# ===============================
def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url: return "tiktok"
    if "facebook.com" in url or "fb.watch" in url: return "facebook"
    return "generic"

# ===============================
# إعداد yt-dlp
# ===============================
def build_opts(platform, outtmpl, sim=False):
    opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "retries": 10,
        "fragment_retries": 10,
        "http_headers": {
            "User-Agent": UA_CHROME
        }
    }

    if sim:
        opts["simulate"] = True

    # دعم cookies (اختياري)
    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"

    # تخصيص المنصات
    if platform == "youtube":
        opts["format"] = "best[ext=mp4]"
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android"]
            }
        }

    elif platform == "tiktok":
        opts["format"] = "best"
        opts["http_headers"] = {
            "User-Agent": UA_MOBILE,
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9"
        }

    elif platform == "facebook":
        opts["format"] = "best"

    else:
        opts["format"] = "best"

    return opts

# ===============================
def clean_title(t):
    if not t: return "video"
    return re.sub(r'[^\w\s\-]', '', t)[:50]

# ===============================
@app.route("/")
def home():
    return {"status": "running"}

# ===============================
@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return {"error": "no url"}, 400

    url = fix_url(url)
    platform = detect_platform(url)

    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid + ".%(ext)s")

    opts = build_opts(platform, path)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        files = glob.glob(os.path.join(DOWNLOAD_FOLDER, fileid + ".*"))
        if not files:
            return {"error": "download failed"}, 500

        file_path = files[0]
        title = clean_title(info.get("title"))

        return send_file(file_path, as_attachment=True, download_name=f"{title}.mp4")

    except Exception as e:
        print(traceback.format_exc())
        return {"error": str(e)}, 500

# ===============================
def cleanup():
    while True:
        now = time.time()
        for f in glob.glob(os.path.join(DOWNLOAD_FOLDER, "*")):
            if now - os.path.getmtime(f) > 600:
                try: os.remove(f)
                except: pass
        time.sleep(60)

# ===============================
def keep_alive():
    while True:
        try:
            requests.get(SERVER_URL)
        except:
            pass
        time.sleep(300)

# ===============================
if __name__ == "__main__":
    threading.Thread(target=cleanup, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)