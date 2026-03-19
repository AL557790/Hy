import yt_dlp
import os

path = os.path.join(os.path.expanduser("~"), "Downloads")

# ===== إعدادات تتجاوز bot detection ليوتيوب =====
YOUTUBE_EXTRACTOR_ARGS = {
    "youtube": {
        "player_client": ["tv_embedded", "web"],
        "player_skip": ["webpage", "configs"],
    }
}

print("="*60)
print("            Welcome to Video Downloader")
print("="*60)

while True:
    url = input("Enter video URL: ")

    is_youtube = "youtube.com" in url or "youtu.be" in url

    try:
        info_opts = {
            'quiet': True,
        }
        if is_youtube:
            info_opts['extractor_args'] = YOUTUBE_EXTRACTOR_ARGS

        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            print(f"\nTitle: {info['title']}")

            available = False
            print("\nAvailable Qualities:")
            for f in info['formats']:
                if f.get('height') and f.get('acodec') != 'none':
                    available = True
                    size = f.get('filesize')
                    quality = f.get('height')
                    if size:
                        size_mb = size / (1024 * 1024)
                        print(f"Quality: {quality}p | Size: {size_mb:.2f} MB")
                    else:
                        print(f"Quality: {quality}p | Size: Unknown")

            if available:
                print("\nDownloading best quality...")

                options = {
                    'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
                    'outtmpl': os.path.join(path, '%(title)s.%(ext)s'),
                    'quiet': True,
                    'merge_output_format': 'mp4',
                }
                if is_youtube:
                    options['extractor_args'] = YOUTUBE_EXTRACTOR_ARGS

                with yt_dlp.YoutubeDL(options) as ydl2:
                    ydl2.download([url])
                    print(f"\nSaved to: {path}")
            else:
                print("No video with audio available")

    except Exception as e:
        print(f"Error: {e}")

    again = input("\nDownload another? (yes/no): ")
    if again.lower() != 'yes':
        print("Goodbye!")
        break
