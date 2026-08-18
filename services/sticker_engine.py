import os
import subprocess
import tempfile
from io import BytesIO
from PIL import Image

class StickerEngine:
    @staticmethod
    def process_image(file_bytes: bytearray) -> BytesIO:
        """Processes static images to fit Telegram PNG requirements"""
        img = Image.open(BytesIO(file_bytes))
        if getattr(img, "is_animated", False):
            img.seek(0)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        ratio = 512 / max(img.width, img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

        bio = BytesIO()
        bio.name = 'kang.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio

    @classmethod
    def process(cls, file_bytes: bytearray, is_video: bool) -> tuple[BytesIO, str]:
        """Converts static images to PNG, and video/animation media to WEBM VP9 video stickers"""
        if not is_video:
            try:
                bio = cls.process_image(file_bytes)
                return bio, 'kang.png'
            except Exception as e:
                # If Pillow fails to identify the image file, it might be an animated GIF or video misclassified.
                # Fall back to FFmpeg processing.
                print(f"StickerEngine: Pillow failed to identify image ({e}). Falling back to FFmpeg transcoder...")
                is_video = True

        # Video sticker conversion logic via FFmpeg
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as temp_in:
            temp_in.write(file_bytes)
            temp_in_path = temp_in.name

        temp_out_path = tempfile.mktemp(suffix=".webm")

        try:
            scale_filter = "scale='if(gt(iw,ih),512,-2)':'if(gt(iw,ih),-2,512)'"
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", temp_in_path,
                "-an",                       # Remove audio
                "-r", "30",                  # Force 30fps max
                "-t", "3",                   # Limit to 3 seconds
                "-vf", scale_filter,         # Scale dimension
                "-c:v", "libvpx-vp9",        # Codec VP9
                "-b:v", "256k",              # Target bitrate
                "-pix_fmt", "yuv420p",       # Standard pixel format
                temp_out_path
            ]

            print(f"StickerEngine: Running FFmpeg on '{temp_in_path}'...")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
            
            if not os.path.exists(temp_out_path) or os.path.getsize(temp_out_path) == 0:
                raise Exception("FFmpeg processing output file was empty or missing.")

            with open(temp_out_path, "rb") as f:
                out_bytes = f.read()

            bio = BytesIO(out_bytes)
            bio.name = "kang.webm"
            return bio, "kang.webm"

        except subprocess.CalledProcessError as cpe:
            stderr_log = cpe.stderr or "No error log."
            print(f"StickerEngine FFmpeg error: {stderr_log}")
            raise Exception(f"FFmpeg failed: {stderr_log.splitlines()[-1] if stderr_log.splitlines() else stderr_log}")
        finally:
            # Clean up temp files
            if os.path.exists(temp_in_path):
                os.remove(temp_in_path)
            if os.path.exists(temp_out_path):
                os.remove(temp_out_path)
