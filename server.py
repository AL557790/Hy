from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

YOUTUBE_EXTRACTOR_ARGS = {
    "youtube": {
        "player_client": ["android", "web"],
    }
}

def get_video_info(url):
    ydl_opts = {
        "quiet": True,
    }

    if "youtube" in url or "youtu.be" in url:
        ydl_opts["extractor_args"] = YOUTUBE_EXTRACTOR_ARGS

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL provided"})

    try:
        info = get_video_info(url)

        formats = []
        for f in info["formats"]:
            if f.get("height") and f.get("acodec") != "none":
                formats.append({
                    "quality": f.get("height"),
                    "url": f.get("url")
                })

        return jsonify({
            "title": info["title"],
            "formats": formats
        })

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/download", methods=["GET"])
def download():
    url = request.args.get("url")

    if not url:
        return jsonify({"error": "No URL provided"})

    try:
        ydl_opts = {
            "format": "best[ext=mp4][height<=720]/best",
            "quiet": True,
        }

        if "youtube" in url or "youtu.be" in url:
            ydl_opts["extractor_args"] = YOUTUBE_EXTRACTOR_ARGS

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                "title": info["title"],
                "download_url": info["url"]
            })

    except Exception as e:
        return jsonify({"error": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)