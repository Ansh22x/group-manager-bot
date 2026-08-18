import io
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class WelcomeCard:
    @staticmethod
    def generate(avatar_bytes: bytes, user_name: str, chat_title: str) -> io.BytesIO:
        """Generates a dynamic 800x400 welcome image card with user avatar and text overlays"""
        width, height = 800, 400
        
        # Base slate background canvas
        img = Image.new("RGBA", (width, height), (15, 23, 42, 255))
        draw = ImageDraw.Draw(img)

        # Draw decorative background arcs (Water Breathing highlights)
        draw.ellipse([(-80, -80), (320, 320)], fill=(30, 41, 59, 255))
        draw.ellipse([(580, 180), (900, 500)], fill=(30, 41, 59, 255))

        avatar_size = 180
        # Draw user avatar
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
                
                # Draw circular cyan outline border
                draw.ellipse(
                    [(56, 106), (56 + avatar_size + 8, 106 + avatar_size + 8)], 
                    outline=(56, 189, 248, 255), 
                    width=4
                )
            except Exception as e:
                logger.error(f"WelcomeCard: Error processing profile photo: {e}")
                # Fallback blue circle
                draw.ellipse([(60, 110), (60 + avatar_size, 110 + avatar_size)], fill=(56, 189, 248, 255))
        else:
            # Fallback blue circle
            draw.ellipse([(60, 110), (60 + avatar_size, 110 + avatar_size)], fill=(56, 189, 248, 255))

        # Load dynamic sizing defaults
        try:
            font_title = ImageFont.load_default(size=24)
            font_name = ImageFont.load_default(size=36)
            font_sub = ImageFont.load_default(size=18)
        except Exception:
            # Fallback for older Pillow versions
            font_title = ImageFont.load_default()
            font_name = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # Render styled text labels
        draw.text((280, 110), "WELCOME TO THE CHAT", fill=(56, 189, 248, 255), font=font_title)
        draw.text((280, 150), user_name, fill=(255, 255, 255, 255), font=font_name)
        draw.text((280, 210), f"Group: {chat_title}", fill=(148, 163, 184, 255), font=font_sub)
        draw.text((280, 245), "Water Breathing Style: Enforced 🌊", fill=(56, 189, 248, 255), font=font_sub)

        bio = io.BytesIO()
        bio.name = "welcome.png"
        img.save(bio, "PNG")
        bio.seek(0)
        return bio
