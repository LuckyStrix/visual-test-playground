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
    "brightness": ("◐", "Grey Gambit", "Same grey, tricky rings"),
    "vernier": ("↔", "Nudge Duel", "Which way did it slip?"),
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
    (46, 125, 50),
    (21, 101, 192),
    (123, 31, 162),
    (239, 108, 0),
    (0, 131, 143),
    (198, 40, 40),
    (69, 90, 100),
]


def asset_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "assets")


def _write_tone(path, notes, rate=22050):
    try:
        rate = int(rate)
    except (TypeError, ValueError, OverflowError):
        return False
    if rate <= 0 or rate > 192000:
        return False
    frames = bytearray()
    try:
        for freq, dur in notes:
            try:
                f = float(freq)
                d = float(dur)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(f) or not math.isfinite(d):
                continue
            f = max(20.0, min(20000.0, f))
            d = max(0.005, min(5.0, d))
            n = max(1, min(int(rate * d), rate * 5))
            for i in range(n):
                env = 1.0 - (i / n)
                s = int(32767 * 0.5 * env * math.sin(2 * math.pi * f * i / rate))
                frames += struct.pack("<h", max(-32768, min(32767, s)))
            gap = int(rate * 0.02)
            frames += b"\x00\x00" * gap
    except (TypeError, ValueError, OverflowError):
        return False
    if not frames:
        return False
    try:
        tmp = path + ".tmp"
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        os.replace(tmp, path)
    except (OSError, wave.Error):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
    return True


def _write_avatar(path, seed=0, size=64):
    if Image is None:
        return False
    try:
        slot = int(seed) % len(_AVATAR_COLORS)
    except (TypeError, ValueError, OverflowError):
        slot = 0
    color = _AVATAR_COLORS[slot]
    tmp = None
    try:
        img = Image.new("RGB", (size, size), (30, 30, 34))
        d = ImageDraw.Draw(img)
        d.ellipse([6, 6, size - 6, size - 6], fill=color)
        cx0 = size // 2
        d.ellipse([cx0 - 10, cx0 - 14, cx0 + 10, cx0 + 6], fill=(245, 245, 245))
        d.ellipse([cx0 - 4, cx0 - 10, cx0 + 4, cx0 - 2], fill=(20, 20, 20))
        d.arc([cx0 - 14, cx0 - 2, cx0 + 14, cx0 + 16], 20, 160, fill=(245, 245, 245), width=3)
        tmp = path + ".tmp"
        img.save(tmp, "PNG")
        os.replace(tmp, path)
    except (OSError, ValueError):
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
    return True


def _write_badge(path, kind="star", size=48):
    if Image is None:
        return False
    tmp = None
    try:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = cy = size // 2
        r = size // 2 - 3
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=(255, 193, 7, 255), outline=(120, 70, 0, 255))
        tmp = path + ".tmp"
        img.convert("RGB").save(tmp, "PNG")
        os.replace(tmp, path)
    except (OSError, ValueError):
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
    return True


def _wav_ok(path):
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        with wave.open(path, "rb") as w:
            return w.getnchannels() > 0 and w.getnframes() > 0
    except Exception:
        return False


def _img_ok(path):
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        if Image is None:
            return True
        from PIL import Image as _I

        with _I.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def ensure_assets():
    d = asset_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return d
    for name, notes in SOUND_SPECS.items():
        p = os.path.join(d, name + ".wav")
        try:
            if not _wav_ok(p):
                _write_tone(p, notes)
        except OSError:
            pass
    try:
        for i in range(len(_AVATAR_COLORS)):
            p = os.path.join(d, f"avatar_{i}.png")
            if not _img_ok(p):
                _write_avatar(p, seed=i)
        p = os.path.join(d, "badge_star.png")
        if not _img_ok(p):
            _write_badge(p)
    except OSError:
        pass
    return d


def sound_path(name):
    if not isinstance(name, str) or name not in SOUND_SPECS:
        return None
    p = os.path.join(asset_dir(), name + ".wav")
    return p if os.path.exists(p) else None


_PLAYER: list | None = None


def _find_player():
    global _PLAYER
    if _PLAYER is None:
        import shutil

        for cmd in (["aplay", "-q"], ["paplay"], ["afplay"]):
            if shutil.which(cmd[0]):
                _PLAYER = cmd
                break
        else:
            _PLAYER = []
    return _PLAYER


def _play_sync(path):
    try:
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except ImportError:
        pass
    except Exception:
        return False
    import subprocess

    cmd = _find_player()
    if not cmd:
        return False
    try:
        proc = subprocess.Popen(
            [*cmd, path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        return False
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        return False
    return proc.returncode == 0


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


def _can_play():
    try:
        import importlib.util

        if importlib.util.find_spec("winsound") is not None:
            return True
    except Exception:
        pass
    try:
        return bool(_find_player())
    except Exception:
        return False


_ACTIVE_SOUNDS: set = set()
_SOUND_LOCK = threading.Lock()


def _play_guarded(name, path):
    try:
        _play_sync(path)
    finally:
        try:
            with _SOUND_LOCK:
                _ACTIVE_SOUNDS.discard(name)
        except Exception:
            pass


def play_async(name, widget=None):
    p = sound_path(name)
    if p is None or not _can_play():
        if widget is not None:
            try:
                widget.bell()
            except Exception:
                pass
        return None
    try:
        with _SOUND_LOCK:
            if name in _ACTIVE_SOUNDS:
                return None
            _ACTIVE_SOUNDS.add(name)
    except Exception:
        return None
    try:
        t = threading.Thread(target=_play_guarded, args=(name, p), daemon=True)
        t.start()
    except Exception:
        try:
            with _SOUND_LOCK:
                _ACTIVE_SOUNDS.discard(name)
        except Exception:
            pass
        return None
    return t


def mission_meta(kind):
    try:
        return MISSION_META.get(kind, ("•", kind, ""))
    except TypeError:
        return ("•", str(kind), "")


def avatar_path(index=0):
    try:
        slot = int(index) % len(_AVATAR_COLORS)
    except (TypeError, ValueError, OverflowError):
        slot = 0
    p = os.path.join(asset_dir(), f"avatar_{slot}.png")
    return p if os.path.exists(p) else None


def photo_image(path, size=None):
    try:
        from PIL import Image as _I

        try:
            from PIL import ImageTk as _Tk
        except ImportError:
            return None
        with _I.open(path) as src:
            img = src.convert("RGB")
            if size is not None:
                try:
                    w = max(1, min(int(float(size[0])), 512))
                    h = max(1, min(int(float(size[1])), 512))
                except (TypeError, ValueError, OverflowError):
                    return None
                img = img.resize((w, h))
            return _Tk.PhotoImage(img)
    except Exception:
        return None
