import subprocess, sys, threading, time, requests, os, uuid, glob, traceback, re

# ── Auto-install ─────────────────────────────────────────────
for pkg in ["flask", "yt-dlp", "flask-cors", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL)

from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type"]
}})

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
SERVER_URL = "https://hy-z1b1.onrender.com"

UA_CHROME  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# ── Helpers ───────────────────────────────────────────────────

def fix_url(url):
    """حل الروابط المختصرة"""
    SHORT = ["fb.watch", "vm.tiktok.com", "vt.tiktok.com", "t.co", "bit.ly", "instagram.com/reel"]
    if any(x in url for x in SHORT) or "facebook.com/share" in url:
        try:
            s = requests.Session()
            s.headers["User-Agent"] = UA_CHROME
            r = s.get(url, allow_redirects=True, timeout=15)
            final = r.url
            # تنظيف fbclid وغيرها
            for junk in ["?fbclid=", "&fbclid=", "?_rdc=", "?_fb_noscript="]:
                if junk in final:
                    final = final.split(junk)[0]
            print(f"[fix_url] {url} → {final}")
            return final
        except Exception as e:
            print(f"[fix_url] error: {e}")
    return url

def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url:                        return "tiktok"
    if "instagram.com" in url:                     return "instagram"
    if "twitter.com" in url or "x.com" in url:    return "twitter"
    if "facebook.com" in url or "fb.watch" in url: return "facebook"
    if "reddit.com" in url or "redd.it" in url:   return "reddit"
    return "generic"

def clean_title(t):
    if not t: return "video"
    return re.sub(r'[\\/*?:"<>|]', '', t).strip()[:80] or "video"

# ── Format strategies per platform ───────────────────────────
# كل منصة عندها قائمة format مرتبة من الأفضل للأسهل

FORMATS = {
    # يوتيوب: نأخذ mp4 مدمج (بدون ffmpeg) — إذا فشل ناخذ أي best
    "youtube": [
        "best[ext=mp4][vcodec^=avc][acodec!=none]",
        "best[ext=mp4][vcodec!=none][acodec!=none]",
        "best[ext=mp4]/best",
        "best",
    ],
    # تيك توك: أول شيء بدون watermark، إذا فشل ناخذ العادي
    "tiktok": [
        "download_addr-0",           # بدون watermark (yt-dlp specific)
        "best[ext=mp4]/best[ext=mp4]/best",
        "best",
    ],
    # انستغرام
    "instagram": [
        "best[ext=mp4]/best",
        "best",
    ],
    # تويتر/X
    "twitter": [
        "best[ext=mp4]/best",
        "best",
    ],
    # فيسبوك
    "facebook": [
        "best[ext=mp4]/best",
        "best",
    ],
    # ريديت
    "reddit": [
        "best[ext=mp4]/best",
        "best",
    ],
    "generic": [
        "best[ext=mp4]/best",
        "best",
    ],
}

def get_base_opts(platform, outtmpl):
    h = {"User-Agent": UA_CHROME}

    if platform == "tiktok":
        h["User-Agent"] = UA_MOBILE
        h["Referer"] = "https://www.tiktok.com/"

    elif platform == "facebook":
        h["Referer"] = "https://www.facebook.com/"
        h["Accept-Language"] = "en-US,en;q=0.9"

    elif platform == "instagram":
        h["Referer"] = "https://www.instagram.com/"

    elif platform == "twitter":
        h["Referer"] = "https://twitter.com/"

    return {
        "outtmpl":           outtmpl,
        "quiet":             True,
        "no_warnings":       True,
        "noplaylist":        True,
        "nocheckcertificate":True,
        "geo_bypass":        True,
        "retries":           5,
        "fragment_retries":  5,
        "http_headers":      h,
        "merge_output_format": "mp4",
    }

def try_download(url, platform, outtmpl, fmt):
    """محاولة تحميل بفورمات معين"""
    opts = get_base_opts(platform, outtmpl)
    opts["format"] = fmt
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info

def try_info(url, platform, fmt):
    """جلب معلومات بدون تحميل"""
    opts = get_base_opts(platform, "/tmp/info_dummy.%(ext)s")
    opts["format"] = fmt
    opts["simulate"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)

# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({"status": "running", "endpoints": ["/info", "/download"]})


@app.route("/info", methods=["POST", "OPTIONS"])
def info():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "لم يتم توفير الرابط"}), 400

    url  = fix_url(url)
    plat = detect_platform(url)

    info_data = None
    last_err  = None

    for fmt in FORMATS.get(plat, FORMATS["generic"]):
        try:
            info_data = try_info(url, plat, fmt)
            if info_data:
                break
        except Exception as e:
            last_err = str(e)
            print(f"[info] {plat} fmt={fmt} failed: {e}")
            continue

    if not info_data:
        return jsonify({"error": last_err or "فشل في جلب معلومات الفيديو"}), 500

    # ── بناء قائمة الجودات ──
    formats, seen = [], set()
    for f in info_data.get("formats", []):
        if f.get("vcodec", "none") == "none": continue
        h    = f.get("height")
        note = f.get("format_note", "")
        ext  = f.get("ext", "mp4")
        key  = str(h) if h else note
        if not key or key in seen: continue
        # يوتيوب: فقط المدمجة
        if plat == "youtube" and f.get("acodec", "none") == "none": continue
        seen.add(key)
        formats.append({
            "id":          f.get("format_id"),
            "ext":         ext,
            "height":      h,
            "filesize":    f.get("filesize") or f.get("filesize_approx"),
            "format_note": note,
        })

    formats.sort(key=lambda x: x.get("height") or 0, reverse=True)

    return jsonify({
        "title":     info_data.get("title"),
        "thumbnail": info_data.get("thumbnail"),
        "duration":  info_data.get("duration"),
        "platform":  plat,
        "formats":   formats[:8],
    })


@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return '', 204

    data = request.get_json(silent=True) or {}
    url  = data.get("url", "").strip()
    fmt  = data.get("format", "")
    if not url:
        return jsonify({"error": "لم يتم توفير الرابط"}), 400

    url      = fix_url(url)
    plat     = detect_platform(url)
    fileid   = str(uuid.uuid4())
    path     = os.path.join(DOWNLOAD_FOLDER, fileid)
    outtmpl  = path + ".%(ext)s"

    # قائمة الفورمات للمحاولة
    fmt_list = [fmt] + FORMATS.get(plat, FORMATS["generic"]) if fmt else FORMATS.get(plat, FORMATS["generic"])

    info_data = None
    last_err  = None

    for try_fmt in fmt_list:
        # نظف أي ملفات من محاولة سابقة
        for f in glob.glob(path + ".*"): os.remove(f)
        try:
            info_data = try_download(url, plat, outtmpl, try_fmt)
            files = glob.glob(path + ".*")
            if files and max(os.path.getsize(f) for f in files) > 1000:
                break  # نجح
            info_data = None
        except Exception as e:
            last_err = str(e)
            print(f"[download] {plat} fmt={try_fmt} failed: {e}")
            continue

    files = glob.glob(path + ".*")
    if not files or (files and max(os.path.getsize(f) for f in files) < 1000):
        return jsonify({"error": last_err or "فشل في تحميل الفيديو"}), 500

    final_path = max(files, key=os.path.getsize)
    ext        = os.path.splitext(final_path)[1].lstrip('.') or "mp4"
    title      = clean_title(info_data.get("title") if info_data else None)
    size_kb    = os.path.getsize(final_path) // 1024

    print(f"[download] [{plat}] {title}.{ext} — {size_kb} KB")

    return send_file(
        final_path,
        as_attachment=True,
        download_name=f"{title}.{ext}",
        mimetype="video/mp4",
    )


# ── Background tasks ──────────────────────────────────────────

def delete_old():
    while True:
        try:
            now = time.time()
            for f in glob.glob(os.path.join(DOWNLOAD_FOLDER, "*")):
                if os.path.isfile(f) and now - os.path.getmtime(f) > 600:
                    try: os.remove(f)
                    except: pass
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
