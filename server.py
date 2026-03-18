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

# ===== قائمة Invidious instances كـ fallback ليوتيوب =====
INVIDIOUS_INSTANCES = [
    "https://invidious.snopyta.org",
    "https://invidious.kavin.rocks",
    "https://vid.puffyan.us",
    "https://yt.artemislena.eu",
    "https://invidious.flokinet.to",
]

def get_youtube_id(url):
    """استخرج video ID من رابط يوتيوب"""
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def invidious_info(video_id):
    """جيب معلومات الفيديو من Invidious API"""
    for instance in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=10)
            if r.status_code == 200:
                return r.json(), instance
        except:
            continue
    return None, None

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

def build_opts(platform, outtmpl, sim=False, fmt=None):
    h = {"User-Agent": UA_CHROME}
    base = {
        "outtmpl": outtmpl, "quiet": True, "no_warnings": True,
        "noplaylist": True, "nocheckcertificate": True, "geo_bypass": True,
        "retries": 10, "fragment_retries": 10,
        "http_headers": h,
    }
    if sim: base["simulate"] = True

    if platform == "youtube":
        base["format"] = fmt or "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
        # ===== الحل الرئيسي: استخدام tv_embedded client يتجاوز bot detection =====
        base["extractor_args"] = {
            "youtube": {
                "player_client": ["tv_embedded", "web"],
                "player_skip": ["webpage", "configs"],
            }
        }

    elif platform == "tiktok":
        h["User-Agent"] = UA_MOBILE
        h["Referer"] = "https://www.tiktok.com/"
        h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        base["format"] = fmt or "best[ext=mp4]/bestvideo[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "facebook":
        h["Referer"] = "https://www.facebook.com/"
        h["Accept-Language"] = "en-US,en;q=0.5"
        base["format"] = fmt or "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "instagram":
        h["Referer"] = "https://www.instagram.com/"
        base["format"] = fmt or "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "twitter":
        h["Referer"] = "https://twitter.com/"
        base["format"] = fmt or "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    else:
        base["format"] = fmt or "best[ext=mp4]/best"
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

    # ===== يوتيوب: جرب yt-dlp أولاً، وإذا فشل استخدم Invidious =====
    if plat == "youtube":
        try:
            return _youtube_info_ytdlp(url)
        except Exception as e:
            err_str = str(e)
            print(f"yt-dlp failed: {err_str}, trying Invidious...")
            if "Sign in" in err_str or "bot" in err_str or "429" in err_str:
                return _youtube_info_invidious(url)
            return jsonify({"error": err_str}), 500

    # باقي المنصات
    try:
        opts = build_opts(plat, "/tmp/info_tmp", sim=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=False)

        formats, seen = [], set()
        for f in info_data.get("formats", []):
            vcodec = f.get("vcodec","none")
            acodec = f.get("acodec","none")
            ext = f.get("ext","")
            h_val = f.get("height")
            if vcodec == "none": continue
            key = str(h_val) if h_val else f.get("format_note","")
            if not key or key in seen: continue
            seen.add(key)
            formats.append({
                "id": f.get("format_id"),
                "ext": ext or "mp4",
                "height": h_val,
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


def _youtube_info_ytdlp(url):
    """جلب معلومات يوتيوب عبر yt-dlp مع tv_embedded"""
    opts = build_opts("youtube", "/tmp/info_tmp", sim=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info_data = ydl.extract_info(url, download=False)

    formats, seen = [], set()
    for f in info_data.get("formats", []):
        vcodec = f.get("vcodec","none")
        acodec = f.get("acodec","none")
        ext = f.get("ext","")
        h_val = f.get("height")
        if vcodec == "none" or acodec == "none": continue
        if ext not in ("mp4","webm"): continue
        key = str(h_val) if h_val else f.get("format_note","")
        if not key or key in seen: continue
        seen.add(key)
        formats.append({
            "id": f.get("format_id"),
            "ext": ext or "mp4",
            "height": h_val,
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "format_note": f.get("format_note","")
        })
    formats.sort(key=lambda x: x.get("height") or 0, reverse=True)

    return jsonify({
        "title": info_data.get("title"),
        "thumbnail": info_data.get("thumbnail"),
        "duration": info_data.get("duration"),
        "platform": "youtube",
        "formats": formats[:8]
    })


def _youtube_info_invidious(url):
    """جلب معلومات يوتيوب عبر Invidious API كـ fallback"""
    video_id = get_youtube_id(url)
    if not video_id:
        return jsonify({"error": "تعذر استخراج معرف الفيديو"}), 400

    inv_data, instance = invidious_info(video_id)
    if not inv_data:
        return jsonify({"error": "فشل الاتصال بجميع الخوادم البديلة"}), 500

    formats = []
    seen = set()
    for f in inv_data.get("adaptiveFormats", []) + inv_data.get("formatStreams", []):
        quality = f.get("qualityLabel","")
        url_f = f.get("url","")
        itag = str(f.get("itag",""))
        if not url_f or not quality: continue
        if quality in seen: continue
        seen.add(quality)
        # استخرج الارتفاع من qualityLabel مثل "720p" -> 720
        h_match = re.match(r"(\d+)p", quality)
        height = int(h_match.group(1)) if h_match else 0
        formats.append({
            "id": f"inv_{itag}_{instance}_{video_id}",
            "ext": "mp4",
            "height": height,
            "filesize": f.get("contentLength"),
            "format_note": quality,
            "direct_url": url_f   # رابط مباشر من Invidious
        })
    formats.sort(key=lambda x: x.get("height") or 0, reverse=True)

    # إذا ما فيهش formats جرب formatStreams
    if not formats:
        return jsonify({"error": "لم يتم العثور على صيغ قابلة للتحميل"}), 500

    duration = inv_data.get("lengthSeconds", 0)
    thumbnail = next((t["url"] for t in inv_data.get("videoThumbnails",[]) if t.get("quality") == "maxres"), 
                     inv_data.get("videoThumbnails",[{}])[0].get("url",""))

    return jsonify({
        "title": inv_data.get("title"),
        "thumbnail": thumbnail,
        "duration": int(duration) if duration else None,
        "platform": "youtube",
        "formats": formats[:8],
        "source": "invidious"
    })


@app.route("/download", methods=["POST","OPTIONS"])
def download():
    if request.method == "OPTIONS": return '', 204
    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    fmt = data.get("format", "best[ext=mp4]/best")
    if not url: return jsonify({"error": "لم يتم توفير الرابط"}), 400

    # ===== إذا كان format_id يبدأ بـ inv_ → رابط Invidious مباشر =====
    if fmt.startswith("inv_"):
        return _download_invidious(fmt)

    url = fix_url(url)
    plat = detect_platform(url)
    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid)

    opts = build_opts(plat, path + ".%(ext)s", fmt=fmt)

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
        err_str = str(e)
        print(traceback.format_exc())
        # ===== يوتيوب: إذا فشل بسبب bot detection جرب Invidious =====
        if plat == "youtube" and ("Sign in" in err_str or "bot" in err_str or "429" in err_str):
            video_id = get_youtube_id(url)
            if video_id:
                return _download_invidious_by_id(video_id)
        return jsonify({"error": err_str}), 500


def _download_invidious(fmt_id):
    """تحميل مباشر من رابط Invidious المخزن في format_id"""
    # fmt_id شكله: inv_{itag}_{instance}_{video_id}
    try:
        parts = fmt_id.split("_", 3)  # inv, itag, instance_url, video_id
        # نعيد بناء الـ instance والـ video_id
        _, itag, instance_encoded, video_id = parts
        # instance مخزن بدون https://
        instance = instance_encoded if instance_encoded.startswith("http") else f"https://{instance_encoded}"
    except:
        return jsonify({"error": "معرف الصيغة غير صحيح"}), 400

    return _download_invidious_by_id(video_id, itag, instance)


def _download_invidious_by_id(video_id, itag=None, instance=None):
    """تحميل فيديو يوتيوب عبر Invidious"""
    inv_data, used_instance = invidious_info(video_id)
    if not inv_data:
        return jsonify({"error": "فشل الاتصال بخوادم يوتيوب البديلة"}), 500

    if instance:
        used_instance = instance

    # اختر أفضل رابط
    all_formats = inv_data.get("formatStreams", []) + inv_data.get("adaptiveFormats", [])
    best = None
    for f in all_formats:
        if itag and str(f.get("itag")) == str(itag):
            best = f
            break
    if not best:
        # اختر أفضل جودة mp4 متاحة
        mp4_formats = [f for f in all_formats if "mp4" in f.get("type","") and f.get("url")]
        if mp4_formats:
            best = max(mp4_formats, key=lambda x: int(re.match(r"(\d+)", x.get("qualityLabel","0p")).group(1)) if re.match(r"(\d+)", x.get("qualityLabel","0p")) else 0)

    if not best or not best.get("url"):
        return jsonify({"error": "لم يتم العثور على رابط التحميل"}), 500

    direct_url = best["url"]
    quality = best.get("qualityLabel", "video")
    title = clean_title(inv_data.get("title"))

    # حمل الملف عبر requests وأرسله للمستخدم
    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, f"{fileid}.mp4")

    try:
        with requests.get(direct_url, stream=True, timeout=60,
                          headers={"User-Agent": UA_CHROME, "Referer": "https://www.youtube.com/"}) as r:
            r.raise_for_status()
            with open(path, 'wb') as fout:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        fout.write(chunk)

        print(f"[youtube/invidious] {path} — {os.path.getsize(path)//1024}KB")
        return send_file(path, as_attachment=True, download_name=f"{title}.mp4", mimetype="video/mp4")

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"فشل تحميل الفيديو: {str(e)}"}), 500


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
