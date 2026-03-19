import subprocess, sys, threading, time, requests, os, uuid, glob, traceback, re, json

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for pkg in ["flask", "yt-dlp", "flask-cors", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        install(pkg)

# ✅ تأكد من وجود ffmpeg في النظام
try:
    subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except:
    print("⚠️ WARNING: ffmpeg not found! YouTube downloads may be limited to 720p or lower.")

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_methods": ["GET","POST","OPTIONS"], "allow_headers": ["Content-Type"]}})

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
SERVER_URL = "https://hy-z1b1.onrender.com"

# ✅ User-Agents محسّنة
UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

def fix_url(url):
    """إصلاح الروابط المختصرة وإعادة التوجيه"""
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
    """كشف المنصة من الرابط"""
    if "youtube.com" in url or "youtu.be" in url: return "youtube"
    if "tiktok.com" in url or "vt.tiktok.com" in url: return "tiktok"
    if "instagram.com" in url or "instagr.am" in url: return "instagram"
    if "twitter.com" in url or "x.com" in url or "t.co" in url: return "twitter"    if "facebook.com" in url or "fb.watch" in url: return "facebook"
    if "reddit.com" in url or "redd.it" in url or "v.redd.it" in url: return "reddit"
    return "generic"

def build_opts(platform, outtmpl, simulate=False):
    """بناء خيارات yt-dlp حسب المنصة"""
    
    # ✅ headers محسّنة
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

    # ✅ إعدادات خاصة بكل منصة
    if platform == "youtube":
        # يوتيوب: نسمح بالفورمات المنفصلة لدمجها لاحقاً مع ffmpeg
        # نفضل mp4 مدمج، أو ندمج فيديو+صوت إذا لزم
        base["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"
        # ✅ إضافة cookies إذا وجدت (للفيديوهات المقيدة)
        cookie_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookie_path):
            base["cookiefile"] = cookie_path

    elif platform == "tiktok":
        headers["User-Agent"] = UA_MOBILE
        headers["Referer"] = "https://www.tiktok.com/"
        base["format"] = "best[ext=mp4]/best"
        base["merge_output_format"] = "mp4"

    elif platform == "facebook":
        headers["Referer"] = "https://www.facebook.com/"        base["format"] = "best[ext=mp4]/best"
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
    """تنظيف عنوان الفيديو لاسم الملف"""
    if not t: return "video"
    return re.sub(r'[^\w\s\-\.]', '', t).strip()[:80] or "video"

@app.route("/")
def home():
    return jsonify({"status": "running", "ffmpeg": subprocess.call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0})

@app.route("/info", methods=["POST","OPTIONS"])
def info():
    if request.method == "OPTIONS": return '', 204
    
    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    if not url: 
        return jsonify({"error": "لم يتم توفير الرابط"}), 400

    url = fix_url(url)
    plat = detect_platform(url)
    print(f"[INFO] Platform: {plat}, URL: {url[:80]}...")

    try:
        opts = build_opts(plat, "/tmp/info_tmp", simulate=True)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=False)

        if not info_data:
            return jsonify({"error": "فشل في جلب معلومات الفيديو"}), 500
        # ✅ معالجة الفورمات - السماح بالفورمات المنفصلة ليوتيوب
        formats, seen = [], set()
        all_fmts = info_data.get("formats", [])
        
        for f in all_fmts:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            ext = f.get("ext", "")
            height = f.get("height")
            filesize = f.get("filesize") or f.get("filesize_approx")
            format_note = f.get("format_note", "")
            format_id = f.get("format_id", "")
            
            # ✅ ليوتيوب: نسمح بالفورمات المنفصلة (video-only أو audio-only)
            if plat == "youtube":
                # نأخذ الفيديو فقط (لدمجه لاحقاً) أو الفورمات المدمجة
                if vcodec == "none": continue  # نتجاهل الصوت فقط في قائمة الجودة
                if ext not in ("mp4", "webm", "m4v"): continue
            else:
                # للمنصات الأخرى: نأخذ فقط الفيديو الكامل
                if vcodec == "none": continue
            
            # منع التكرار
            key = f"{height}p_{format_id}" if height else format_id
            if key in seen: continue
            seen.add(key)
            
            formats.append({
                "id": format_id,
                "ext": ext or "mp4",
                "height": height,
                "width": f.get("width"),
                "filesize": filesize,
                "format_note": format_note,
                "vcodec": vcodec,
                "acodec": acodec,
                "fps": f.get("fps"),
                "quality": f.get("quality", 0)
            })
        
        # ✅ ترتيب حسب الجودة (الطول أولاً، ثم وجود الصوت)
        formats.sort(key=lambda x: (x.get("height") or 0, x.get("acodec") != "none"), reverse=True)

        return jsonify({
            "title": info_data.get("title", "Untitled"),
            "thumbnail": info_data.get("thumbnail"),
            "duration": info_data.get("duration"),
            "duration_string": info_data.get("duration_string"),
            "platform": plat,
            "uploader": info_data.get("uploader"),            "view_count": info_data.get("view_count"),
            "formats": formats[:10],  # إظهار أفضل 10 فورمات
            "webpage_url": info_data.get("webpage_url", url)
        })
        
    except yt_dlp.utils.DownloadError as e:
        print(f"[ERROR] yt-dlp DownloadError: {e}")
        return jsonify({"error": f"خطأ في جلب الفيديو: {str(e)[:200]}"}), 500
    except Exception as e:
        print(f"[ERROR] Unexpected: {traceback.format_exc()}")
        return jsonify({"error": f"خطأ غير متوقع: {str(e)[:200]}"}), 500

@app.route("/download", methods=["POST","OPTIONS"])
def download():
    if request.method == "OPTIONS": return '', 204
    
    data = request.get_json(silent=True) or {}
    url = data.get("url","").strip()
    format_selector = data.get("format", "best")
    
    if not url: 
        return jsonify({"error": "لم يتم توفير الرابط"}), 400

    url = fix_url(url)
    plat = detect_platform(url)
    fileid = str(uuid.uuid4())
    path = os.path.join(DOWNLOAD_FOLDER, fileid)
    
    print(f"[DOWNLOAD] {plat} - {url[:80]}... - format: {format_selector}")

    opts = build_opts(plat, path + ".%(ext)s")
    opts["format"] = format_selector
    
    # ✅ إضافة postprocessors لدمج الفيديو والصوت إذا لزم
    opts["postprocessors"] = [{
        "key": "FFmpegVideoConvertor",
        "preferedformat": "mp4",
    }]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info_data = ydl.extract_info(url, download=True)

        if not info_data:
            return jsonify({"error": "فشل في معالجة الفيديو"}), 500

        # ✅ البحث عن الملف المحمّل
        files = glob.glob(path + ".*")
        if not files: 
            # محاولة البحث في مجلد فرعي            for root, dirs, filenames in os.walk(DOWNLOAD_FOLDER):
                for f in filenames:
                    if fileid in f:
                        files.append(os.path.join(root, f))
        
        if not files: 
            return jsonify({"error": "فشل في العثور على الملف المحمّل"}), 500

        # ✅ اختيار أكبر ملف (عادةً هو الفيديو الكامل)
        final_path = max(files, key=os.path.getsize)
        ext = os.path.splitext(final_path)[1].lstrip('.') or "mp4"
        title = clean_title(info_data.get("title"))
        size_kb = os.path.getsize(final_path) // 1024
        
        print(f"[SUCCESS] {plat} - {final_path} - {size_kb}KB")

        response = send_file(
            final_path, 
            as_attachment=True, 
            download_name=f"{title}.{ext}", 
            mimetype=f"video/{ext}"
        )
        
        # ✅ حذف الملف بعد الإرسال (في thread منفصل لعدم حجب الاستجابة)
        def cleanup():
            time.sleep(5)
            try: 
                if os.path.exists(final_path):
                    os.remove(final_path)
                    print(f"[CLEANUP] Deleted: {final_path}")
            except: pass
        threading.Thread(target=cleanup, daemon=True).start()
        
        return response
        
    except yt_dlp.utils.DownloadError as e:
        print(f"[ERROR] Download failed: {e}")
        return jsonify({"error": f"فشل التحميل: {str(e)[:200]}"}), 500
    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        return jsonify({"error": f"خطأ: {str(e)[:200]}"}), 500

# ✅ تنظيف الملفات القديمة
def delete_old():
    while True:
        try:
            now = time.time()
            for f in glob.glob(os.path.join(DOWNLOAD_FOLDER,"*")):
                if os.path.isfile(f) and now - os.path.getmtime(f) > 600:  # 10 دقائق
                    os.remove(f)                    print(f"[CLEANUP] Old file removed: {f}")
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")
        time.sleep(60)

# ✅ Keep-alive لـ Render
def keep_alive():
    while True:
        try: 
            requests.get(SERVER_URL, timeout=8)
            print("[KEEP-ALIVE] Ping sent")
        except Exception as e:
            print(f"[KEEP-ALIVE ERROR] {e}")
        time.sleep(300)

if __name__ == "__main__":
    print("🚀 Starting VAULTDROP Backend...")
    print(f"📁 Download folder: {os.path.abspath(DOWNLOAD_FOLDER)}")
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=delete_old, daemon=True).start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)