import math
import os
import struct
import threading
import wave

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]

MISSION_META = {
    "static_contrast": ("◉", "Ghost Stripes", "Spot the faintest stripes"),
    "static_color": ("◎", "Bullseye Tint", "Redder or bluer center?"),
    "static_rt": ("⚡", "Quick Draw", "Hit SPACE the instant it pops"),
    "collinear": ("═", "Rail Align", "Are the rails aligned?"),
    "brightness": ("◐", "Grey Gambit", "Same grey, tricky rings"),
    "vernier": ("↔", "Nudge Duel", "Which way did it slip?"),
    "subitize": ("⋮⋮", "Dot Blitz", "Count the swarm fast"),
    "hueorder": ("🌈", "Hue Ladder", "Lightest to darkest"),
    "sizematch": ("○", "Twin Discs", "Match the twin"),
    "masked": ("👁", "Flash Mask", "Catch the blink"),
    "contrast": ("🌫", "Fog Radar", "Which interval hid it?"),
    "acuity": ("🎯", "Gap Sniper", "Where is the gap?"),
    "color": ("🎨", "Tint Twins", "Which pair differs?"),
}

SOUND_SPECS = {
    "correct": [(880.0, 0.09), (1318.5, 0.12)],
    "wrong": [(220.0, 0.15), (155.0, 0.18)],
    "levelup": [(523.25, 0.1), (659.25, 0.1), (783.99, 0.1), (1046.5, 0.2)],
    "click": [(660.0, 0.05)],
    "streak": [(987.77, 0.08), (1174.66, 0.08), (1318.5, 0.14)],
}

_AVATAR_COLORS = [
    (46, 125, 50), (21, 101, 192), (123, 31, 162), (239, 108, 0),
    (0, 131, 143), (198, 40, 40), (69, 90, 100),
]


def asset_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "assets")


def _write_tone(path, notes, rate=22050):
    frames = bytearray()
    for freq, dur in notes:
        n = max(1, int(rate * dur))
        for i in range(n):
            env = 1.0 - (i / n)
            s = int(32767 * 0.5 * env * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", max(-32768, min(32767, s)))
        gap = int(rate * 0.02)
        frames += b"\x00\x00" * gap
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def _write_avatar(path, seed=0, size=64):
    if Image is None:
        return False
    color = _AVATAR_COLORS[seed % len(_AVATAR_COLORS)]
    img = Image.new("RGB", (size, size), (30, 30, 34))
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, size - 6, size - 6], fill=color)
    cx0 = size // 2
    d.ellipse([cx0 - 10, cx0 - 14, cx0 + 10, cx0 + 6], fill=(245, 245, 245))
    d.ellipse([cx0 - 4, cx0 - 10, cx0 + 4, cx0 - 2], fill=(20, 20, 20))
    d.arc([cx0 - 14, cx0 - 2, cx0 + 14, cx0 + 16], 20, 160,
          fill=(245, 245, 245), width=3)
    img.save(path)
    return True


def _write_badge(path, kind="star", size=48):
    if Image is None:
        return False
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    r = size // 2 - 3
    pts = []
    import math as _m
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -_m.pi / 2 + i * _m.pi / 5
        pts.append((cx + rr * _m.cos(a), cy + rr * _m.sin(a)))
    d.polygon(pts, fill=(255, 193, 7, 255), outline=(120, 70, 0, 255))
    img.convert("RGB").save(path)
    return True


def ensure_assets():
    d = asset_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return d
    for name, notes in SOUND_SPECS.items():
        p = os.path.join(d, name + ".wav")
        try:
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                _write_tone(p, notes)
        except OSError:
            pass
    try:
        for i in range(4):
            p = os.path.join(d, f"avatar_{i}.png")
            if not os.path.exists(p):
                _write_avatar(p, seed=i)
        p = os.path.join(d, "badge_star.png")
        if not os.path.exists(p):
            _write_badge(p)
    except OSError:
        pass
    return d


def sound_path(name):
    p = os.path.join(asset_dir(), name + ".wav")
    return p if os.path.exists(p) else None


def _play_sync(path):
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except ImportError:
        pass
    except Exception:
        return False
    import shutil
    import subprocess
    for cmd in (["aplay", "-q", path], ["paplay", path], ["afplay", path]):
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
    return False


def play_sound(name, widget=None):
    p = sound_path(name)
    if p is None:
        if widget is not None:
            try:
                widget.bell()
            except Exception:
                pass
        return False
    ok = _play_sync(p)
    if not ok and widget is not None:
        try:
            widget.bell()
        except Exception:
            pass
    return ok


def play_async(name, widget=None):
    t = threading.Thread(target=play_sound, args=(name, widget), daemon=True)
    t.start()
    return t


def mission_meta(kind):
    return MISSION_META.get(kind, ("•", kind, ""))


def avatar_path(index=0):
    p = os.path.join(asset_dir(), f"avatar_{int(index) % 4}.png")
    return p if os.path.exists(p) else None


def photo_image(path, size=None):
    try:
        from PIL import Image as _I
        try:
            from PIL import ImageTk as _Tk
        except ImportError:
            return None
        img = _I.open(path)
        if size is not None:
            img = img.resize((int(size[0]), int(size[1])))
        return _Tk.PhotoImage(img)
    except Exception:
        return None
