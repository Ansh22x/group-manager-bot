import io
import math
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class WelcomeCard:
    @staticmethod
    def generate(avatar_bytes: bytes, user_name: str, chat_title: str) -> io.BytesIO:
        """Generates a dynamic 800x400 welcome image card with user avatar, polar wave border, and background wave lines"""
        width, height = 800, 400
        
        # Base deep dark slate background canvas (Giyu theme)
        img = Image.new("RGBA", (width, height), (15, 23, 42, 255))
        draw = ImageDraw.Draw(img)

        # 1. Render flowing background waves (Water Breathing curves)
        # Deep blue background wave
        wave_pts_deep = []
        for x in range(0, width + 10, 10):
            y = 340 + 15 * math.sin(x * 0.015)
            wave_pts_deep.append((x, y))
        draw.line(wave_pts_deep, fill=(30, 58, 138, 255), width=8)

        # Light cyan foreground wave
        wave_pts_light = []
        for x in range(0, width + 10, 10):
            y = 360 + 10 * math.sin(x * 0.02 + 1.2)
            wave_pts_light.append((x, y))
        draw.line(wave_pts_light, fill=(56, 189, 248, 255), width=4)

        avatar_size = 180
        avatar_cx = 60 + avatar_size // 2  # 150
        avatar_cy = 110 + avatar_size // 2  # 200

        # 2. Draw user avatar
        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                
                # Create circular clip mask
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                
                # Paste cropped avatar
                img.paste(avatar, (60, 110), mask=mask)
            except Exception as e:
                logger.error(f"WelcomeCard: Error processing profile photo: {e}")
                # Fallback blue circle
                draw.ellipse([(60, 110), (60 + avatar_size, 110 + avatar_size)], fill=(30, 58, 138, 255))
        else:
            # Fallback blue circle
            draw.ellipse([(60, 110), (60 + avatar_size, 110 + avatar_size)], fill=(30, 58, 138, 255))

        # 3. Draw polar coordinate Wave Ripple Border around the avatar circle
        border_r = (avatar_size // 2) + 6  # Base radius (96)
        amplitude = 6                      # Wave height
        frequency = 12                     # Number of waves around the circle
        wave_border_points = []
        
        for deg in range(361):             # Walk around the circle (0 to 360 degrees)
            angle = math.radians(deg)
            # Add sine wave ripple to the radius
            curr_r = border_r + amplitude * math.sin(frequency * angle)
            x = avatar_cx + curr_r * math.cos(angle)
            y = avatar_cy + curr_r * math.sin(angle)
            wave_border_points.append((x, y))
            
        # Draw the wave-shaped border outline
        draw.line(wave_border_points, fill=(56, 189, 248, 255), width=4)

        # 4. Render styled text labels
        try:
            font_title = ImageFont.load_default(size=24)
            font_name = ImageFont.load_default(size=36)
            font_sub = ImageFont.load_default(size=18)
        except Exception:
            # Fallback for older Pillow versions
            font_title = ImageFont.load_default()
            font_name = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        draw.text((280, 110), "WELCOME TO THE CHAT", fill=(56, 189, 248, 255), font=font_title)
        draw.text((280, 150), user_name, fill=(255, 255, 255, 255), font=font_name)
        draw.text((280, 210), f"Group: {chat_title}", fill=(148, 163, 184, 255), font=font_sub)
        draw.text((280, 245), "Water Breathing Style: Enforced 🌊", fill=(56, 189, 248, 255), font=font_sub)

        bio = io.BytesIO()
        bio.name = "welcome.png"
        img.save(bio, "PNG")
        bio.seek(0)
        return bio
