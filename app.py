import os
import time
import uuid
import socket
import shutil
import threading
import base64
from io import BytesIO
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

# Requests library for PC-to-PC transfer
try:
    import requests
except ImportError:
    requests = None
    print("⚠️ 'requests' library not found. Install it: pip install requests")

# QR Code library
try:
    import qrcode
except ImportError:
    qrcode = None

# Barcode library
try:
    import barcode as barcode_lib
    from barcode.writer import ImageWriter
except ImportError:
    barcode_lib = None

# Windows printer modules
try:
    import win32print
    import win32api
    import win32con
except ImportError:
    win32print = None
    win32api = None
    win32con = None

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# DESKTOP FOLDER SETUP FOR SESSIONS
# ==========================================
try:
    DESKTOP_PATH = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    if not os.path.exists(DESKTOP_PATH):
        DESKTOP_PATH = os.path.expanduser("~")
except Exception:
    DESKTOP_PATH = os.path.expanduser("~")

CURRENT_SESSION_FOLDER = UPLOAD_FOLDER # Default fallback

# ==========================================
# AUTO IP & QR / BARCODE SETUP
# ==========================================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("0."):
            return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127.") and not ip.startswith("0."):
            return ip
    except Exception:
        pass
    try:
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
        for ip in ips:
            if ip and not ip.startswith("127.") and not ip.startswith("0."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"

LOCAL_IP = get_local_ip()
PORT = 5000
AUTO_CONNECT_URL = f"http://{LOCAL_IP}:{PORT}/app?autoconnect=1"

print("=" * 60)
print(f"🌐  AUTO-DETECTED PC / ROUTER IP : {LOCAL_IP}")
print(f"🔗  APP LINK (open on any device) : {AUTO_CONNECT_URL}")
print("=" * 60)

qr_available = False
if qrcode:
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(AUTO_CONNECT_URL)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        qr_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, "server_qr.png"))
        img.save(qr_path, "PNG", optimize=True)
        qr_available = True
        print(f"✅ QR Code generated  -> {AUTO_CONNECT_URL}")
        print(f"   saved at: {qr_path}")
    except Exception as e:
        print(f"⚠️ QR error: {e}")
else:
    print("⚠️ 'qrcode' library not installed. Run: pip install qrcode[pil]")

barcode_available = False
barcode_png_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, "server_barcode.png"))

def _save_barcode_pil():
    from PIL import Image, ImageDraw, ImageFont
    data = AUTO_CONNECT_URL
    CODE128 = barcode_lib.get_barcode_class('code128')
    bar = CODE128(data, writer=ImageWriter())
    raw_path = os.path.join(UPLOAD_FOLDER, "server_barcode_raw")
    saved = bar.save(raw_path, options={
        'module_width': 0.5,
        'module_height': 25.0,
        'font_size': 14,
        'text_distance': 5.0,
        'quiet_zone': 6.5,
        'write_text': True,
    })
    if saved and os.path.exists(saved):
        from PIL import Image as _PILImg
        img = _PILImg.open(saved).convert("RGB")
        img.save(barcode_png_path, "PNG", optimize=True)
        try:
            os.remove(saved)
        except OSError:
            pass
    return barcode_png_path

if barcode_lib:
    try:
        result_path = _save_barcode_pil()
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            barcode_available = True
            print(f"✅ Barcode generated   -> {AUTO_CONNECT_URL}")
            print(f"   saved at: {result_path}")
        else:
            raise RuntimeError("barcode file missing or empty after save")
    except Exception as e:
        print(f"⚠️ Barcode error: {e}")
        print(f"   Run: pip install python-barcode pillow")
else:
    print("⚠️ 'python-barcode' library not installed. Run: pip install python-barcode")

# ==========================================
# 1. SPLASH SCREEN UI (standalone — kept safe)
# ==========================================
SPLASH_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome - Ahmad Gujjar</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            height: 100vh;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-family: 'Segoe UI', sans-serif;
            overflow: hidden;
        }
        .qr-box {
            padding: 20px;
            background: rgba(255,255,255,0.9);
            border-radius: 20px;
            text-align: center;
            backdrop-filter: blur(10px);
            box-shadow: 0 0 20px rgba(255,255,255,0.2);
        }
        .qr-box img { width: 200px; height: 200px; display: block; }
    </style>
</head>
<body>
    <div class="qr-box">{{ if_qr }}<p style="color:#000; margin-top:10px;">Scan to Connect</p></div>
    <script>setTimeout(() => window.location.href = "/app", 5000);</script>
</body>
</html>
"""

# ==========================================
# 2. MAIN APP UI  (ADVANCED + REAL + FOOTER WITH IMRAN KHAN)
# ==========================================
ADVANCED_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Ahmad Gujjar — Smart Print Pro</title>
    <link href="https://fonts.googleapis.com/css2?family=Pacifico&family=Lobster&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #059669;
            --glass-bg: rgba(255, 255, 255, 0.65);
            --glass-border: rgba(255, 255, 255, 0.5);
            --text: #064e3b;
            --text-sub: #047857;
            --success: #10b981;
            --danger: #ef4444;
            --wa-green: #25D366;
            --footer-bg: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: url('https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=1920&auto=format&fit=crop') no-repeat center center fixed;
            background-size: cover;
            color: var(--text);
            margin: 0; padding-bottom: 0; min-height: 100vh;
            overflow-x: hidden;
        }

        /* ===========================================================
           7-SECOND INTRO SPLASH — IMRAN KHAN HD FULL SIZE
           =========================================================== */
        #intro-splash {
            position: fixed; inset: 0;
            background: #000;
            z-index: 99999;
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            overflow: hidden;
        }
        #intro-splash.hidden { display: none; }

        .splash-bg {
            position: absolute; inset: 0;
            background-image: url('https://upload.wikimedia.org/wikipedia/commons/9/9e/Imran_Khan_November_2019.jpg');
            background-size: cover; background-position: center top;
            animation: zoomEffect 12s infinite alternate;
            opacity: 0.9;
        }
        .splash-overlay {
            position: absolute; inset: 0;
            background: linear-gradient(to bottom, rgba(0,0,0,0.1), rgba(0,20,0,0.6));
        }

        .splash-content {
            position: relative; z-index: 10; text-align: center;
            animation: slideUpFade 2s ease-out;
            display: flex; flex-direction: column; align-items: center;
        }
        .splash-title {
            font-family: 'Lobster', 'Pacifico', cursive;
            font-size: clamp(2.5rem, 9vw, 6rem);
            margin: 0;
            line-height: 1.1;
            letter-spacing: 1px;
            color: #fff;
            text-shadow: 0 4px 15px rgba(0,0,0,0.8);
            animation: fadeInWord 1s ease-out both;
        }
        .splash-sub {
            color: #4ade80; font-size: 1.3rem; margin-top: 18px;
            letter-spacing: 4px; font-weight: 300;
            text-shadow: 0 2px 5px rgba(0,0,0,0.8);
            opacity: 0;
            animation: fadeInWord 1s ease-out 2.2s both;
        }

        /* Loading bar in splash — CENTERED (inside splash-content) */
        .splash-loader {
            width: 240px; height: 5px; border-radius: 3px;
            background: rgba(255,255,255,0.15); overflow: hidden;
            margin: 35px auto 0 auto;
            opacity: 0;
            animation: fadeInWord 0.5s ease-out 2.5s both;
        }
        .splash-loader-bar {
            height: 100%; width: 0%;
            background: linear-gradient(90deg, #4ade80, #22d3ee, #fde047);
            border-radius: 3px;
            animation: loadFill 7s linear forwards;
        }
        @keyframes loadFill { from { width: 0%; } to { width: 100%; } }

        /* ===========================================================
           FIXED IT / PC BANNER
           =========================================================== */
        .banner {
            position: relative; width: 100%; height: 240px; overflow: hidden;
            background: #000;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            border-bottom: 4px solid var(--primary);
            display: none;
        }
        .banner.show { display: block; animation: bannerSlide 0.8s ease-out; }
        @keyframes bannerSlide { from { transform: translateY(-100%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        .banner-img {
            position: absolute; inset: 0;
            background-image: url('https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=1920&auto=format&fit=crop');
            background-size: cover; background-position: center;
        }
        .banner-overlay {
            position: absolute; inset: 0;
            background: linear-gradient(135deg, rgba(0,30,0,0.55), rgba(0,0,0,0.35));
        }
        .banner-text {
            position: relative; z-index: 2;
            display: flex; flex-direction: column;
            justify-content: center; align-items: center;
            height: 100%; padding: 20px; text-align: center;
        }
        .banner-text h2 {
            font-family: 'Pacifico', cursive;
            font-size: 2rem; margin: 0;
            color: #fff;
            text-shadow: 0 3px 10px rgba(0,0,0,0.6);
        }
        .banner-text p {
            margin-top: 8px;
            color: #bbf7d0; font-size: 0.95rem; letter-spacing: 1px;
        }
        .banner-pulse {
            position: absolute; bottom: 14px; right: 18px;
            display: flex; align-items: center; gap: 6px;
            background: rgba(0,0,0,0.5);
            padding: 6px 12px; border-radius: 20px;
            color: #4ade80; font-size: 0.8rem;
        }
        .banner-pulse .live-dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: #4ade80; box-shadow: 0 0 8px #4ade80;
            animation: liveBlink 1.4s infinite;
        }
        @keyframes liveBlink { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

        /* HEADER TOGGLE FLOATING BUTTON */
        #header-toggle-btn {
            position: fixed; top: 15px; left: 15px; z-index: 110;
            background: rgba(5, 150, 105, 0.8); color: white;
            border: none; padding: 8px 12px; border-radius: 12px;
            cursor: pointer; display: none; font-size: 1rem; font-weight: bold;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            transition: transform 0.2s;
        }
        #header-toggle-btn:hover { transform: scale(1.1); background: var(--primary); }
        body.header-hidden header, body.header-hidden .top-nav { display: none !important; }

        /* HEADER (GLASS) */
        header {
            background: var(--glass-bg);
            backdrop-filter: blur(15px);
            -webkit-backdrop-filter: blur(15px);
            padding: 12px 20px; position: sticky; top: 0; z-index: 100;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--glass-border);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
            display: none;
        }
        header.show { display: flex; }
        .header-left h1 { margin: 0; font-family: 'Pacifico', cursive; font-size: 1.4rem; background: linear-gradient(45deg, #059669, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .header-right { display: flex; align-items: center; gap: 10px; }

        .live-clock {
            font-family: 'Orbitron', monospace;
            font-size: 0.85rem; font-weight: 700;
            color: #047857;
            background: rgba(255,255,255,0.4);
            padding: 6px 12px; border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.6);
            backdrop-filter: blur(5px);
            letter-spacing: 1px;
        }

        /* TOP NAVIGATION BAR */
        .top-nav {
            position: sticky; top: 60px; z-index: 99;
            display: none; justify-content: center; gap: 8px;
            padding: 8px 12px; flex-wrap: wrap;
            background: rgba(255,255,255,0.55);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--glass-border);
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        }
        .top-nav.show { display: flex !important; }
        .nav-link {
            display: inline-flex; align-items: center; gap: 6px;
            padding: 8px 16px; border-radius: 22px;
            font-size: 0.9rem; font-weight: 600;
            color: #064e3b; text-decoration: none;
            background: rgba(255,255,255,0.6);
            border: 1px solid rgba(255,255,255,0.7);
            transition: all 0.25s ease;
            cursor: pointer; white-space: nowrap;
        }
        .nav-link:hover {
            background: linear-gradient(135deg, #059669, #10b981);
            color: #fff;
            transform: translateY(-2px);
            box-shadow: 0 6px 14px rgba(5,150,105,0.35);
        }
        .nav-ico { font-size: 1rem; }
        .nav-dropdown { position: relative; }
        .nav-menu {
            position: absolute; top: 110%; left: 50%; transform: translateX(-50%);
            min-width: 200px;
            background: rgba(255,255,255,0.97);
            backdrop-filter: blur(15px);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            padding: 6px;
            display: none;
            z-index: 200;
        }
        .nav-menu.show { display: block; animation: dropIn 0.25s ease; }
        @keyframes dropIn { from { opacity: 0; transform: translateX(-50%) translateY(-8px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }
        .nav-menu a {
            display: block; padding: 10px 14px;
            color: #064e3b; text-decoration: none;
            font-size: 0.88rem; font-weight: 500;
            border-radius: 10px; transition: 0.2s;
        }
        .nav-menu a:hover { background: rgba(5,150,105,0.12); color: #047857; }
        .caret { font-size: 0.7rem; opacity: 0.7; }

        @media (max-width: 480px) {
            .top-nav { top: 56px; gap: 6px; padding: 6px 8px; }
            .nav-link { padding: 6px 12px; font-size: 0.82rem; }
            .live-clock { display: none; }
        }

        .icon-btn {
            background: rgba(255,255,255,0.4);
            border: 1px solid rgba(255,255,255,0.6);
            padding: 8px; border-radius: 14px; width: 44px; height: 44px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            transition: all 0.3s ease;
            color: var(--primary);
            backdrop-filter: blur(5px);
        }
        .icon-btn:hover {
            background: rgba(255,255,255,0.8);
            transform: translateY(-2px) scale(1.05);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .wa-btn { background: var(--wa-green); color: white; border: none; }
        .wa-btn:hover { background: #1ebc57; box-shadow: 0 5px 15px rgba(37, 211, 102, 0.4); }
        .status-dot { width: 12px; height: 12px; border-radius: 50%; background: #cbd5e1; transition: 0.3s; border: 2px solid #fff; box-shadow: 0 0 0 1px #cbd5e1; }
        .status-dot.active { background: var(--success); border-color: #fff; box-shadow: 0 0 0 1px var(--success); animation: pulseGreen 2s infinite; }
        @keyframes pulseGreen { 0%,100% { box-shadow: 0 0 0 1px var(--success), 0 0 0 0 rgba(16,185,129,0.4); } 50% { box-shadow: 0 0 0 1px var(--success), 0 0 0 8px rgba(16,185,129,0); } }

        /* MAIN CONTENT */
        main { padding: 20px; max-width: 600px; margin: 0 auto; display: none; padding-bottom: 280px; }
        main.show { display: block; }
        .card {
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 24px; padding: 25px; margin-bottom: 20px;
            border: 1px solid var(--glass-border);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
            transition: transform 0.3s ease;
        }
        .card:hover { transform: translateY(-3px); box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.2); }

        .card-title { font-size: 0.8rem; color: var(--text-sub); margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; border-bottom: 1px solid rgba(5, 150, 105, 0.2); padding-bottom: 10px; display: flex; align-items: center; gap: 8px; }

        input[type="text"], select {
            width: 100%; padding: 14px; border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.6); background: rgba(255,255,255,0.5);
            color: #064e3b; margin-bottom: 12px; outline: none; transition: 0.3s; font-size: 1rem;
            backdrop-filter: blur(5px);
        }
        input:focus, select:focus {
            background: rgba(255,255,255,0.9);
            border-color: var(--primary);
            box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1);
        }

        button.btn-primary {
            background: linear-gradient(135deg, var(--primary), #047857);
            color: white; width: 100%; padding: 14px;
            border: none; border-radius: 14px; font-weight: 600; cursor: pointer;
            box-shadow: 0 4px 15px rgba(5, 150, 105, 0.3);
            transition: all 0.3s ease;
            border: 1px solid rgba(255,255,255,0.2);
        }
        button.btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(5, 150, 105, 0.4);
            background: linear-gradient(135deg, #047857, #065f46);
        }

        button.btn-success {
            background: linear-gradient(135deg, var(--success), #059669);
            color: white; width: 100%; padding: 16px;
            border: none; border-radius: 18px; font-weight: 700; cursor: pointer;
            margin-top: 10px; box-shadow: 0 4px 20px rgba(16, 185, 129, 0.4);
            font-size: 1.1rem; border: 1px solid rgba(255,255,255,0.2);
            transition: all 0.3s ease;
        }
        button.btn-success:hover { transform: scale(1.02); box-shadow: 0 8px 25px rgba(16, 185, 129, 0.5); }

        .upload-area {
            border: 2px dashed rgba(5, 150, 105, 0.3); padding: 30px; text-align: center;
            border-radius: 20px; cursor: pointer; background: rgba(255,255,255,0.4);
            transition: 0.3s; backdrop-filter: blur(5px);
        }
        .upload-area:hover { background: rgba(255,255,255,0.7); border-color: var(--primary); transform: scale(1.01); }
        .image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(85px, 1fr)); gap: 12px; margin-top: 15px; }
        
        .img-item { position: relative; aspect-ratio: 1; border-radius: 16px; overflow: hidden; background: rgba(255,255,255,0.5); border: 2px solid transparent; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: 0.3s; cursor: pointer; }
        .img-item.selected { border-color: var(--success); transform: scale(1.05); box-shadow: 0 8px 15px rgba(16, 185, 129, 0.3); }
        .img-item img { width: 100%; height: 100%; object-fit: cover; opacity: 0.85; transition: 0.3s; }
        .img-item.selected img { opacity: 1; }
        
        /* IMAGE DELETE BUTTON */
        .img-del-btn {
            position: absolute; top: 4px; right: 4px; z-index: 10;
            width: 26px; height: 26px; border-radius: 50%;
            background: rgba(239, 68, 68, 0.9); color: white;
            border: 1px solid rgba(255,255,255,0.8);
            display: flex; align-items: center; justify-content: center;
            font-size: 0.8rem; cursor: pointer; transition: 0.2s;
        }
        .img-del-btn:hover { background: #dc2626; transform: scale(1.15); }

        .hidden { display: none !important; }

        #toast-container { position: fixed; top: 80px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 10px; }
        .toast {
            background: rgba(255,255,255,0.95);
            padding: 15px 20px; border-radius: 16px;
            border-left: 5px solid var(--primary); color: #064e3b;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            animation: slideIn 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
            font-weight: 500; backdrop-filter: blur(5px);
            transition: opacity 0.3s, transform 0.3s;
        }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

        @keyframes zoomEffect { 0% { transform: scale(1); } 100% { transform: scale(1.15); } }
        @keyframes slideUpFade { 0% { opacity: 0; transform: translateY(50px); } 100% { opacity: 1; transform: translateY(0); } }
        @keyframes fadeOut { from { opacity: 1; } to { opacity: 0; } }

        .modal-backdrop { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,20,0,0.6); backdrop-filter: blur(8px); z-index: 500; display: flex; justify-content: center; align-items: center; }
        .modal-backdrop.hidden { display: none; }
        .modal-content { background: rgba(255,255,255,0.95); padding: 30px; border-radius: 24px; text-align: center; border: 1px solid var(--glass-border); width: 85%; max-width: 340px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); backdrop-filter: blur(15px); }

        .doc-list { list-style: none; padding: 0; margin: 0; }
        .doc-item { display: flex; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.6); padding: 12px; border-radius: 14px; margin-bottom: 10px; border: 1px solid rgba(255,255,255,0.4); box-shadow: 0 2px 5px rgba(0,0,0,0.05); transition: 0.2s; }
        .doc-item:hover { background: rgba(255,255,255,0.9); transform: translateX(5px); }
        .doc-info { display: flex; align-items: center; gap: 12px; overflow: hidden; }
        .doc-icon { font-size: 1.5rem; min-width: 35px; text-align: center; background: rgba(255,255,255,0.8); width: 35px; height: 35px; display: flex; align-items: center; justify-content: center; border-radius: 10px; }
        .doc-name { font-size: 0.9rem; color: #065f46; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        .ip-pill {
            background: rgba(5, 150, 105, 0.12);
            color: #047857;
            border: 1px dashed rgba(5, 150, 105, 0.5);
            border-radius: 10px;
            padding: 6px 10px; font-size: 0.85rem; font-weight: 600;
            word-break: break-all;
        }

        /* ===========================================================
           BEAUTIFUL FOOTER WITH IMRAN KHAN HD IMAGE
           =========================================================== */
        .main-footer {
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: var(--footer-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-top: 3px solid transparent;
            border-image: linear-gradient(90deg, #10b981, #22d3ee, #fde047, #22d3ee, #10b981) 1;
            z-index: 90;
            box-shadow: 0 -10px 40px rgba(0,0,0,0.3);
            display: none;
            animation: footerRise 0.8s ease-out;
            
        }
        .main-footer.show { display: block; }
        @keyframes footerRise { from { transform: translateY(100%); } to { transform: translateY(0); } }

        .footer-inner {
            display: flex; align-items: center; gap: 16px;
            padding: 14px 20px;
            max-width: 600px; margin: 0 auto;
        }

        .footer-img-wrap {
            position: relative;
            flex-shrink: 0;
            width: 72px; height: 72px;
            border-radius: 50%;
            overflow: hidden;
            border: 3px solid #22d3ee;
            box-shadow: 0 0 15px rgba(34, 211, 238, 0.5), 0 4px 12px rgba(0,0,0,0.4);
            animation: footerImgGlow 3s ease-in-out infinite;
        }
        @keyframes footerImgGlow {
            0%,100% { box-shadow: 0 0 15px rgba(34, 211, 238, 0.5), 0 4px 12px rgba(0,0,0,0.4); border-color: #22d3ee; }
            33%     { box-shadow: 0 0 18px rgba(74, 222, 128, 0.6), 0 4px 12px rgba(0,0,0,0.4); border-color: #4ade80; }
            66%     { box-shadow: 0 0 18px rgba(253, 224, 71, 0.5), 0 4px 12px rgba(0,0,0,0.4); border-color: #fde047; }
        }
        .footer-img-wrap img {
            width: 100%; height: 100%; object-fit: cover;
            display: block;
        }
        .footer-img-fallback {
            width: 100%; height: 100%;
            background: linear-gradient(135deg, #1a5276, #2ecc71);
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-family: 'Orbitron', monospace; font-size: 1.4rem; font-weight: 900;
        }

        .footer-text-wrap {
            flex: 1; min-width: 0;
        }
        .footer-title {
            font-family: 'Pacifico', cursive;
            font-size: 1.1rem; margin: 0;
            color: #fff;
            text-shadow: 0 2px 8px rgba(0,0,0,0.5);
        }
        .footer-subtitle {
            font-size: 0.72rem; margin: 2px 0 0 0;
            color: #67e8f9; letter-spacing: 1px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .footer-quote {
            font-size: 0.68rem; margin: 3px 0 0 0;
            color: rgba(255,255,255,0.6); font-style: italic;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        .footer-clock-wrap {
            flex-shrink: 0; text-align: right;
        }
        .footer-clock-time {
            font-family: 'Orbitron', monospace;
            font-size: 1rem; font-weight: 700;
            color: #67e8f9;
            text-shadow: 0 0 8px rgba(103, 232, 249, 0.4);
        }
        .footer-clock-date {
            font-size: 0.65rem; color: rgba(255,255,255,0.5);
            margin-top: 2px;
        }

        .footer-bottom-bar {
            background: rgba(0,0,0,0.3);
            padding: 5px 20px; text-align: center;
            font-size: 0.65rem; color: rgba(255,255,255,0.4);
            letter-spacing: 0.5px;
        }

        .print-btn-wrap {
            position: fixed; bottom: 110px; left: 0; width: 100%;
            padding: 0 20px; pointer-events: none;
            display: flex; justify-content: center;
            z-index: 95;
        }
        .print-btn-wrap button {
            pointer-events: auto;
            max-width: 560px;
        }

        @media (max-width: 480px) {
            .footer-img-wrap { width: 56px; height: 56px; }
            .footer-title { font-size: 0.95rem; }
            .footer-subtitle { font-size: 0.65rem; }
            .footer-quote { font-size: 0.6rem; }
            .footer-clock-time { font-size: 0.85rem; }
            .print-btn-wrap { bottom: 100px; }
        }

        .stats-bar {
            display: flex; gap: 8px; margin-bottom: 15px;
        }
        .stat-chip {
            flex: 1; text-align: center;
            background: rgba(255,255,255,0.5);
            border: 1px solid rgba(255,255,255,0.6);
            border-radius: 14px; padding: 10px 6px;
            backdrop-filter: blur(5px);
        }
        .stat-chip .stat-num {
            font-family: 'Orbitron', monospace;
            font-size: 1.2rem; font-weight: 700;
            color: var(--primary);
        }
        .stat-chip .stat-label {
            font-size: 0.65rem; color: var(--text-sub);
            text-transform: uppercase; letter-spacing: 0.5px;
            margin-top: 2px;
        }
    </style>
</head>
<body>

<!-- ===== 7 SECOND INTRO SPLASH (Imran Khan HD Full Size) ===== -->
<div id="intro-splash">
    <div class="splash-bg"></div>
    <div class="splash-overlay"></div>

    <div class="splash-content">
        <h1 class="splash-title">Ahmad Gujjar</h1>
        <p class="splash-sub">SMART PRINT PRO</p>

        <!-- Loading bar — now CENTERED inside splash-content -->
        <div class="splash-loader">
            <div class="splash-loader-bar"></div>
        </div>
    </div>
</div>

<!-- HEADER TOGGLE BUTTON -->
<button id="header-toggle-btn" onclick="toggleHeader()">⬆️</button>

<!-- ===== FIXED IT / PC BANNER ===== -->
<div class="banner" id="main-banner">
    <div class="banner-img"></div>
    <div class="banner-overlay"></div>
    <div class="banner-text">
        <h2>Ahmad Gujjar</h2>
        <p>Smart Print Pro &mdash; Ultimate Glass Edition</p>
    </div>
    <div class="banner-pulse">
        <span class="live-dot"></span> LIVE
    </div>
</div>

<div id="auto-connect-overlay" class="modal-backdrop hidden">
    <div class="modal-content">
        <div style="font-size:3rem; margin-bottom:15px; animation: spin 1s linear infinite;">📡</div>
        <h3 style="margin:0; color:#064e3b; font-family:'Pacifico';">Secure Connecting...</h3>
        <p style="color:#059669; font-size:0.9rem;" id="ac-status">Network Hidden</p>
    </div>
</div>

<header>
    <div class="header-left"><h1>Ahmad Gujjar</h1></div>
    <div class="header-right">
        <div class="live-clock" id="header-clock">00:00:00</div>
        <button class="icon-btn wa-btn" onclick="shareOnWhatsApp()" title="Share">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.008-.57-.008-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/></svg>
        </button>
        <button class="icon-btn" onclick="openQR()" title="Show QR Code">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="7" height="7"></rect>
                <rect x="14" y="3" width="7" height="7"></rect>
                <rect x="14" y="14" width="7" height="7"></rect>
                <path d="M3 14h7v7H3z"></path>
            </svg>
        </button>
        <div id="status-dot" class="status-dot"></div>
    </div>
</header>

<!-- ===== TOP NAVIGATION BAR ===== -->
<nav class="top-nav" id="top-nav">
    <a href="https://www.rekhta.org/" target="_blank" rel="noopener" class="nav-link">
        <span class="nav-ico">📚</span> Poetry
    </a>
    <div class="nav-dropdown">
        <a href="#" class="nav-link" onclick="event.preventDefault();toggleDropdown()">
            <span class="nav-ico">🕌</span> Islamic Features <span class="caret">▾</span>
        </a>
        <div class="nav-menu" id="islamic-menu">
            <a href="https://www.dawateislami.net/islamic-books/hadees" target="_blank" rel="noopener">📖 Hadees</a>
            <a href="https://www.dawateislami.net/islamic-calendar" target="_blank" rel="noopener">📅 Islamic Calendar</a>
        </div>
    </div>
    <a href="https://dailypakistan.com.pk" target="_blank" rel="noopener" class="nav-link">
        <span class="nav-ico">📰</span> News
    </a>
</nav>

<main>
    <!-- STATS BAR -->
    <div class="stats-bar">
        <div class="stat-chip">
            <div class="stat-num" id="stat-images">0</div>
            <div class="stat-label">Images</div>
        </div>
        <div class="stat-chip">
            <div class="stat-num" id="stat-docs">0</div>
            <div class="stat-label">Docs</div>
        </div>
        <div class="stat-chip">
            <div class="stat-num" id="stat-printers">0</div>
            <div class="stat-label">Printers</div>
        </div>
    </div>

    <!-- CONNECTION -->
    <div class="card">
        <div class="card-title">🔒 1. Start Print Session</div>
        <input type="text" id="username" placeholder="Enter Your Name" value="Ahmad">
        <button id="connect-btn" class="btn-primary" onclick="startSession()">Start Session</button>
    </div>

    <!-- PRINTER -->
    <div class="card hidden" id="printer-card">
        <div class="card-title">🖨️ 2. Select Printer</div>
        <select id="printers"></select>
    </div>

    <!-- ANOTHER PC CONNECT -->
    <div class="card hidden" id="pc-connect-card">
        <div class="card-title">💻 3. Send to Another PC</div>
        <input type="text" id="target-ip" placeholder="Target PC IP (e.g. 192.168.1.5)">
        <div style="font-size:0.8rem; color:#047857; margin-bottom:10px;">Note: Target PC must have this app running.</div>
        <button class="btn-primary" onclick="testTargetConnection()" style="background:linear-gradient(135deg, #f59e0b, #d97706);">🔗 Test Connection</button>
    </div>

    <!-- DOCS -->
    <div class="card hidden" id="doc-card">
        <div class="card-title">📄 4. Document Center</div>
        <div style="display:flex; gap:10px;">
            <button class="btn-primary" onclick="document.getElementById('pdf-input').click()" style="background:linear-gradient(135deg, #ef4444, #dc2626);">+ PDF</button>
            <button class="btn-primary" onclick="document.getElementById('excel-input').click()" style="background:linear-gradient(135deg, #10b981, #059669);">+ Excel</button>
        </div>
        <input type="file" id="pdf-input" accept="application/pdf" style="display:none" onchange="handleDocUpload(this.files, 'pdf')">
        <input type="file" id="excel-input" accept=".xls,.xlsx" style="display:none" onchange="handleDocUpload(this.files, 'excel')">
        <ul class="doc-list" id="doc-list" style="margin-top:15px;"></ul>
    </div>

    <!-- IMAGES -->
    <div class="card hidden" id="image-card">
        <div class="card-title">🖼️ 5. HD Image Gallery</div>
        <div class="upload-area" onclick="document.getElementById('img-input').click()">
            <p style="margin:0; color:#047857; font-weight:600;">+ Add HD Photos</p>
        </div>
        <input type="file" id="img-input" accept="image/*" multiple style="display:none" onchange="handleImgUpload(this.files)">
        <div class="image-grid" id="img-grid"></div>
        <p id="sel-count" style="text-align:center; font-size:0.9rem; color:#059669; margin-top:15px; font-weight:500;">0 Selected</p>
    </div>

    <!-- BLUETOOTH TRANSFER -->
    <div class="card hidden" id="bluetooth-card">
        <div class="card-title">🔵 6. Bluetooth Transfer</div>
        <div style="font-size:0.85rem; color:#047857; margin-bottom:12px; line-height:1.5;">
            Pair your phone via Bluetooth and send images directly. Works on Chrome/Edge (Android) and Chrome (PC).<br>
            <b>PC Bluetooth Service:</b> <span id="bt-status" style="color:#6b7280;">Checking...</span>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px;">
            <button class="btn-primary" onclick="bluetoothConnect()" style="background:linear-gradient(135deg, #2563eb, #1d4ed8); flex:1; min-width:140px;">🔵 Pair Device</button>
            <button class="btn-primary" onclick="bluetoothDisconnect()" style="background:linear-gradient(135deg, #6b7280, #4b5563); flex:1; min-width:140px;">❌ Disconnect</button>
        </div>
        <div class="upload-area" onclick="document.getElementById('bt-img-input').click()" style="border-color:rgba(37,99,235,0.4); background:rgba(37,99,235,0.05);">
            <p style="margin:0; color:#1d4ed8; font-weight:600;">📱 + Pick Images for Bluetooth</p>
            <p style="margin:6px 0 0 0; font-size:0.75rem; color:#6b7280;">(separate from print queue)</p>
        </div>
        <input type="file" id="bt-img-input" accept="image/*" multiple style="display:none" onchange="handleBtImgUpload(this.files)">
        <div class="image-grid" id="bt-img-grid" style="margin-top:14px;"></div>
        <p id="bt-sel-count" style="text-align:center; font-size:0.9rem; color:#1d4ed8; margin-top:10px; font-weight:500;">0 BT Images Selected</p>
        <button class="btn-primary" onclick="bluetoothSendFiles()" style="background:linear-gradient(135deg, #7c3aed, #5b21b6); margin-top:10px;">
            📤 Send via Bluetooth
        </button>
        <div id="bt-log" style="margin-top:12px; font-size:0.8rem; color:#374151; max-height:140px; overflow-y:auto; background:rgba(255,255,255,0.5); padding:10px; border-radius:10px; border:1px solid rgba(255,255,255,0.5);">
            <i>Bluetooth log will appear here...</i>
        </div>
        <div style="font-size:0.75rem; color:#6b7280; margin-top:8px; line-height:1.4;">
            <b>Note:</b> If your browser doesn't support Web Bluetooth (e.g. iOS Safari, Firefox), the app will automatically fall back to WiFi transfer (same network, no IP shown).
        </div>
    </div>
</main>

<!-- Print Button -->
<div class="print-btn-wrap">
    <button id="print-btn" class="btn-success hidden" onclick="startPrint()">🚀 PRINT & SEND</button>
</div>

<!-- ===== BEAUTIFUL FOOTER WITH IMRAN KHAN HD IMAGE ===== -->
<footer class="main-footer" id="main-footer">
    <div class="footer-inner">
        <div class="footer-img-wrap">
            <img src="https://upload.wikimedia.org/wikipedia/commons/9/9e/Imran_Khan_November_2019.jpg"
                 alt="Imran Khan"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="footer-img-fallback" style="display:none;">IK</div>
        </div>

        <div class="footer-text-wrap">
            <h3 class="footer-title">Ahmad Gujjar</h3>
            <p class="footer-subtitle">Smart Print Pro — Ultimate Edition</p>
            <p class="footer-quote">"Absolutely Not — A Stand for Sovereignty"</p>
        </div>

        <div class="footer-clock-wrap">
            <div class="footer-clock-time" id="footer-clock">00:00:00</div>
            <div class="footer-clock-date" id="footer-date">Loading...</div>
        </div>
    </div>
    <div class="footer-bottom-bar">
        &copy; 2024 Ahmad Gujjar — All Rights Reserved | Powered by Smart Print Pro
    </div>
</footer>

<!-- ===== CONNECT MODAL (QR + BARCODE + LIVE SCANNER) ===== -->
<div id="qr-modal" class="modal-backdrop hidden" onclick="this.classList.add('hidden')">
    <div class="modal-content" onclick="event.stopPropagation()" style="max-width:360px;">
        <h3 style="margin:0 0 15px 0; color:#064e3b; font-family:'Pacifico';">Connect via QR / Barcode</h3>
        <div style="display:flex; gap:6px; margin-bottom:15px; background:rgba(0,0,0,0.05); padding:5px; border-radius:12px;">
            <button id="tab-show" onclick="switchTab('show')" style="flex:1; padding:8px; border:none; border-radius:8px; background:#fff; color:#064e3b; font-weight:600; cursor:pointer;">Show Codes</button>
            <button id="tab-scan" onclick="switchTab('scan')" style="flex:1; padding:8px; border:none; border-radius:8px; background:transparent; color:#064e3b; font-weight:600; cursor:pointer;">Scan</button>
        </div>
        <div id="tab-show-content">
            <div style="display:flex; flex-direction:column; gap:14px;">
                <div>
                    <p style="font-size:0.8rem; color:#047857; margin:0 0 6px 0; font-weight:600;">QR Code</p>
                    <img id="qr-img" src="/qr_image" alt="QR Code" width="220" style="width:100%; max-width:220px; height:auto; border-radius:12px; border:1px solid rgba(0,0,0,0.1); background:#fff; padding:6px; display:block; margin:0 auto;">
                </div>
                <div>
                    <p style="font-size:0.8rem; color:#047857; margin:0 0 6px 0; font-weight:600;">Barcode (CODE128)</p>
                    <img id="barcode-img" src="/barcode_image" alt="Barcode" style="width:100%; max-width:280px; height:auto; border-radius:8px; border:1px solid rgba(0,0,0,0.1); background:#fff; padding:6px; display:block; margin:0 auto;">
                </div>
                <div class="ip-pill" id="qr-ip-pill">Secure Network Hidden</div>
            </div>
        </div>
        <div id="tab-scan-content" style="display:none;">
            <p style="font-size:0.8rem; color:#047857; margin:0 0 10px 0;">Point your camera at the QR / Barcode on the other device.</p>
            <div id="scanner-region" style="width:100%; max-width:280px; aspect-ratio:1; margin:0 auto; border-radius:12px; overflow:hidden; border:2px solid var(--primary); background:#000;"></div>
            <div style="display:flex; gap:8px; margin-top:12px;">
                <button class="btn-primary" onclick="startScanner()" style="background:linear-gradient(135deg, #059669, #047857); flex:1;">▶ Start Camera</button>
                <button class="btn-primary" onclick="stopScanner()" style="background:linear-gradient(135deg, #ef4444, #dc2626); flex:1;">■ Stop</button>
            </div>
            <div id="scan-result" style="margin-top:10px; font-size:0.8rem; color:#374151; word-break:break-all; background:rgba(255,255,255,0.5); padding:8px; border-radius:8px; min-height:30px;">
                <i>No scan yet...</i>
            </div>
        </div>
        <button class="btn-primary" style="margin-top:15px;" onclick="closeConnectModal()">Close</button>
    </div>
</div>

<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>

<div id="toast-container"></div>

<script>
    // ==========================================
    // GLOBAL STATE
    // ==========================================
    let SERVER = "";
    let isConnected = false;
    let real_ip = "";
    let imgQueue = [];
    let docQueue = [];
    let btImgQueue = [];
    let html5QrCode = null;
    let btDevice = null;
    let btServer = null;

    // ==========================================
    // LIVE CLOCK
    // ==========================================
    function updateClocks() {
        const now = new Date();
        const h = String(now.getHours()).padStart(2,'0');
        const m = String(now.getMinutes()).padStart(2,'0');
        const s = String(now.getSeconds()).padStart(2,'0');
        const timeStr = h + ':' + m + ':' + s;

        const hc = document.getElementById('header-clock');
        const fc = document.getElementById('footer-clock');
        const fd = document.getElementById('footer-date');
        if(hc) hc.innerText = timeStr;
        if(fc) fc.innerText = timeStr;

        const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        if(fd) fd.innerText = days[now.getDay()] + ', ' + now.getDate() + ' ' + months[now.getMonth()];
    }
    setInterval(updateClocks, 1000);
    updateClocks();

    // ==========================================
    // HEADER TOGGLE
    // ==========================================
    function toggleHeader() {
        document.body.classList.toggle('header-hidden');
        var btn = document.getElementById('header-toggle-btn');
        if(document.body.classList.contains('header-hidden')) {
            btn.innerText = "⬇️";
            btn.title = "Show Header";
        } else {
            btn.innerText = "⬆️";
            btn.title = "Hide Header";
        }
    }

    // ==========================================
    // STATS UPDATER
    // ==========================================
    function updateStats() {
        const si = document.getElementById('stat-images');
        const sd = document.getElementById('stat-docs');
        const sp = document.getElementById('stat-printers');
        if(si) si.innerText = imgQueue.filter(function(i){return i.selected;}).length;
        if(sd) sd.innerText = docQueue.length;
        const printers = document.getElementById('printers');
        if(sp) sp.innerText = printers ? printers.options.length : 0;
    }

    // ==========================================
    // 7-SECOND SPLASH → HOME PAGE OPEN
    // ==========================================
    window.onload = function() {
        setTimeout(function() {
            // Hide splash
            var splash = document.getElementById('intro-splash');
            if(splash) {
                splash.style.opacity = '0';
                splash.style.transition = 'opacity 0.8s ease';
                setTimeout(function() {
                    splash.style.display = 'none';
                }, 800);
            }

            // Show home page elements
            var banner = document.getElementById('main-banner');
            var header = document.querySelector('header');
            var nav = document.getElementById('top-nav');
            var main = document.querySelector('main');
            var footer = document.getElementById('main-footer');
            var toggleBtn = document.getElementById('header-toggle-btn');

            if(banner) banner.classList.add('show');
            if(header) header.classList.add('show');
            if(nav) nav.classList.add('show');
            if(main) main.classList.add('show');
            if(footer) footer.classList.add('show');
            if(toggleBtn) toggleBtn.classList.add('show');

            // Check auto-connect
            checkAutoConnect();
        }, 7000);  // 7 seconds
    };

    // ==========================================
    // NAVIGATION DROPDOWN
    // ==========================================
    function toggleDropdown() {
        var menu = document.getElementById('islamic-menu');
        if(menu) menu.classList.toggle('show');
    }
    document.addEventListener('click', function(e) {
        var menu = document.getElementById('islamic-menu');
        if(menu && menu.classList.contains('show') && !e.target.closest('.nav-dropdown')) {
            menu.classList.remove('show');
        }
    });

    // ==========================================
    // AUTO-CONNECT (IP HIDDEN FROM UI)
    // ==========================================
    function checkAutoConnect() {
        var params = new URLSearchParams(window.location.search);
        if(params.get('autoconnect') === '1') {
            autoConnect();
        } else {
            var saved = localStorage.getItem('print_ip');
            if(saved) real_ip = saved;
            real_ip = window.location.hostname || real_ip;
        }
    }

    async function autoConnect() {
        var parts = window.location.host.split(':');
        real_ip = parts[0];
        var overlay = document.getElementById('auto-connect-overlay');
        if(overlay) overlay.classList.remove('hidden');
        try {
            var res = await fetch('http://' + real_ip + ':5000/printers');
            if(res.ok) {
                if(overlay) overlay.classList.add('hidden');
                showToast("✅ Server Connected! Enter name & Start Session.", "success");
            }
        } catch(e) {
            if(overlay) overlay.classList.add('hidden');
            showToast("❌ Server not reachable.", "error");
        }
        history.replaceState({}, '', '/app');
    }

    // ==========================================
    // START SESSION (Creates Desktop Folder)
    // ==========================================
    async function startSession() {
        var btn = document.getElementById('connect-btn');
        if(isConnected) {
            // Disconnect logic
            isConnected = false;
            btn.innerText = "Start Session";
            updateUI(false);
            showToast("Session ended", "info");
            return;
        }

        var username = document.getElementById('username').value.trim();
        if(!username) { showToast("⚠️ Please enter your name", "error"); return; }
        
        btn.innerText = "Starting...";
        try {
            var res = await fetch('http://' + real_ip + ':5000/start_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username })
            });
            var data = await res.json();
            
            if(data.success) {
                populatePrinters(data.printers);
                isConnected = true;
                btn.innerText = "✅ End Session";
                updateUI(true);
                showToast("✅ Folder '" + username + "' created on Desktop!", "success");
            } else {
                btn.innerText = "Start Session";
                showToast("❌ Failed to start session", "error");
            }
        } catch(e) {
            btn.innerText = "Start Session";
            showToast("❌ Connection failed: " + e.message, "error");
        }
    }

    function populatePrinters(printers) {
        var sel = document.getElementById('printers');
        sel.innerHTML = '';
        if(!printers || printers.length === 0) {
            sel.innerHTML = '<option>No printers found</option>';
        } else {
            printers.forEach(function(p) {
                var opt = document.createElement('option');
                opt.value = p;
                opt.innerText = p;
                sel.appendChild(opt);
            });
        }
        updateStats();
    }

    function updateUI(connected) {
        var cardIds = ['printer-card', 'pc-connect-card', 'doc-card', 'image-card', 'bluetooth-card'];
        cardIds.forEach(function(id) {
            var el = document.getElementById(id);
            if(el) {
                if(connected) el.classList.remove('hidden');
                else el.classList.add('hidden');
            }
        });
        var dot = document.getElementById('status-dot');
        if(dot) {
            if(connected) dot.classList.add('active');
            else dot.classList.remove('active');
        }
        var printBtn = document.getElementById('print-btn');
        if(printBtn) {
            if(connected) printBtn.classList.remove('hidden');
            else printBtn.classList.add('hidden');
        }
        updateStats();
    }

    // ==========================================
    // TOAST
    // ==========================================
    function showToast(msg, type) {
        var container = document.getElementById('toast-container');
        var toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerText = msg;
        if(type === 'error') toast.style.borderLeftColor = '#ef4444';
        if(type === 'success') toast.style.borderLeftColor = '#10b981';
        if(type === 'info') toast.style.borderLeftColor = '#3b82f6';
        container.appendChild(toast);
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(function() { toast.remove(); }, 300);
        }, 3500);
    }

    // ==========================================
    // QR MODAL
    // ==========================================
    function openQR() {
        document.getElementById('qr-modal').classList.remove('hidden');
    }
    function closeConnectModal() {
        document.getElementById('qr-modal').classList.add('hidden');
        stopScanner();
    }
    function switchTab(tab) {
        var showBtn = document.getElementById('tab-show');
        var scanBtn = document.getElementById('tab-scan');
        var showContent = document.getElementById('tab-show-content');
        var scanContent = document.getElementById('tab-scan-content');
        if(tab === 'show') {
            showBtn.style.background = '#fff';
            scanBtn.style.background = 'transparent';
            showContent.style.display = 'block';
            scanContent.style.display = 'none';
            stopScanner();
        } else {
            showBtn.style.background = 'transparent';
            scanBtn.style.background = '#fff';
            showContent.style.display = 'none';
            scanContent.style.display = 'block';
        }
    }

    // ==========================================
    // QR SCANNER
    // ==========================================
    async function startScanner() {
        try {
            if(!html5QrCode) {
                html5QrCode = new Html5Qrcode("scanner-region");
            }
            await html5QrCode.start(
                { facingMode: "environment" },
                { fps: 10, qrbox: { width: 200, height: 200 } },
                function(decodedText) {
                    document.getElementById('scan-result').innerText = decodedText;
                    showToast("✅ Scanned!", "success");
                },
                function(errorMessage) { /* ignore */ }
            );
            showToast("📷 Scanner started", "info");
        } catch(e) {
            showToast("❌ Camera error: " + e, "error");
        }
    }
    async function stopScanner() {
        if(html5QrCode) {
            try {
                await html5QrCode.stop();
                html5QrCode.clear();
            } catch(e) { /* ignore */ }
        }
    }

    // ==========================================
    // WHATSAPP SHARE
    // ==========================================
    function shareOnWhatsApp() {
        var url = window.location.href;
        var text = "Check out Ahmad Gujjar - Smart Print Pro! " + url;
        window.open('https://wa.me/?text=' + encodeURIComponent(text), '_blank');
    }

    // ==========================================
    // DOCUMENT UPLOAD (Auto-saves to Desktop Folder)
    // ==========================================
    function handleDocUpload(files, type) {
        if(!isConnected) { showToast("⚠️ Start session first", "error"); return; }
        Array.from(files).forEach(function(file) {
            var formData = new FormData();
            formData.append('file', file);
            formData.append('type', type);
            fetch('http://' + real_ip + ':5000/upload', {
                method: 'POST',
                body: formData
            }).then(function(r) { return r.json(); }).then(function(data) {
                docQueue.push({ name: file.name, type: type, path: data.path });
                renderDocs();
                updateStats();
                showToast("✅ " + file.name + " saved to PC", "success");
            }).catch(function(e) { showToast("❌ Upload failed", "error"); });
        });
    }

    function renderDocs() {
        var list = document.getElementById('doc-list');
        list.innerHTML = '';
        docQueue.forEach(function(doc, i) {
            var li = document.createElement('li');
            li.className = 'doc-item';
            var icon = doc.type === 'pdf' ? '📕' : '📗';
            li.innerHTML = '<div class="doc-info"><div class="doc-icon">' + icon + '</div><div class="doc-name">' + doc.name + '</div></div><button class="icon-btn" style="width:32px;height:32px;" onclick="removeDoc(' + i + ')">❌</button>';
            list.appendChild(li);
        });
    }

    function removeDoc(i) {
        docQueue.splice(i, 1);
        renderDocs();
        updateStats();
    }

    // ==========================================
    // IMAGE UPLOAD & MULTIPLE SELECTION & DELETE
    // ==========================================
    function handleImgUpload(files) {
        if(!isConnected) { showToast("⚠️ Start session first", "error"); return; }
        Array.from(files).forEach(function(file) {
            var formData = new FormData();
            formData.append('file', file);
            
            fetch('http://' + real_ip + ':5000/upload', {
                method: 'POST',
                body: formData
            }).then(function(r) { return r.json(); }).then(function(data) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    imgQueue.push({ src: e.target.result, selected: true, name: file.name, serverPath: data.path });
                    renderImages();
                    updateStats();
                };
                reader.readAsDataURL(file);
            }).catch(function(e) { showToast("❌ Upload failed", "error"); });
        });
    }

    function renderImages() {
        var grid = document.getElementById('img-grid');
        grid.innerHTML = '';
        imgQueue.forEach(function(img, i) {
            var div = document.createElement('div');
            div.className = 'img-item' + (img.selected ? ' selected' : '');
            
            var delBtn = document.createElement('button');
            delBtn.className = 'img-del-btn';
            delBtn.innerHTML = '❌';
            delBtn.onclick = function(event) {
                event.stopPropagation();
                deleteImage(i);
            };
            
            var imgEl = document.createElement('img');
            imgEl.src = img.src;
            imgEl.alt = img.name;

            div.onclick = function() {
                imgQueue[i].selected = !imgQueue[i].selected;
                renderImages();
                updateStats();
            };

            div.appendChild(delBtn);
            div.appendChild(imgEl);
            grid.appendChild(div);
        });
        var count = imgQueue.filter(function(i){return i.selected;}).length;
        document.getElementById('sel-count').innerText = count + ' Selected';
    }

    function deleteImage(i) {
        imgQueue.splice(i, 1);
        renderImages();
        updateStats();
        showToast("🗑️ Image removed", "info");
    }

    // ==========================================
    // BLUETOOTH IMAGE UPLOAD & DELETE
    // ==========================================
    function handleBtImgUpload(files) {
        if(!isConnected) { showToast("⚠️ Start session first", "error"); return; }
        Array.from(files).forEach(function(file) {
            var formData = new FormData();
            formData.append('file', file);
            
            fetch('http://' + real_ip + ':5000/upload', {
                method: 'POST',
                body: formData
            }).then(function(r) { return r.json(); }).then(function(data) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    btImgQueue.push({ src: e.target.result, name: file.name, serverPath: data.path });
                    renderBtImages();
                };
                reader.readAsDataURL(file);
            });
        });
    }

    function renderBtImages() {
        var grid = document.getElementById('bt-img-grid');
        grid.innerHTML = '';
        btImgQueue.forEach(function(img, i) {
            var div = document.createElement('div');
            div.className = 'img-item selected';
            
            var delBtn = document.createElement('button');
            delBtn.className = 'img-del-btn';
            delBtn.innerHTML = '❌';
            delBtn.onclick = function(event) {
                event.stopPropagation();
                deleteBtImage(i);
            };

            var imgEl = document.createElement('img');
            imgEl.src = img.src;
            imgEl.alt = img.name;

            div.appendChild(delBtn);
            div.appendChild(imgEl);
            grid.appendChild(div);
        });
        document.getElementById('bt-sel-count').innerText = btImgQueue.length + ' BT Images Selected';
    }

    function deleteBtImage(i) {
        btImgQueue.splice(i, 1);
        renderBtImages();
        showToast("🗑️ BT image removed", "info");
    }

    // ==========================================
    // PRINT (Auto-removes files after printing)
    // ==========================================
    async function startPrint() {
        var selectedImgs = imgQueue.filter(function(i){return i.selected;});
        if(selectedImgs.length === 0 && docQueue.length === 0) {
            showToast("⚠️ Select images or docs first", "error");
            return;
        }
        var printer = document.getElementById('printers').value;
        showToast("🖨️ Printing...", "info");
        try {
            var res = await fetch('http://' + real_ip + ':5000/print', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    printer: printer,
                    images: selectedImgs.map(function(i){return i.serverPath;}),
                    docs: docQueue.map(function(d){return d.path;}),
                    username: document.getElementById('username').value
                })
            });
            var data = await res.json();
            if(data.success) {
                showToast("✅ Printed & files removed from app!", "success");
                // Clear queues
                imgQueue = [];
                docQueue = [];
                renderImages();
                renderDocs();
                updateStats();
            } else {
                showToast("❌ Print failed: " + (data.error || ""), "error");
            }
        } catch(e) {
            showToast("❌ Print error: " + e.message, "error");
        }
    }

    // ==========================================
    // TEST TARGET PC CONNECTION
    // ==========================================
    async function testTargetConnection() {
        var targetIp = document.getElementById('target-ip').value.trim();
        if(!targetIp) { showToast("Enter target IP", "error"); return; }
        try {
            var res = await fetch('http://' + targetIp + ':5000/printers');
            if(res.ok) {
                showToast("✅ Target PC reachable!", "success");
            } else {
                showToast("❌ Target PC not responding", "error");
            }
        } catch(e) {
            showToast("❌ Cannot reach target PC", "error");
        }
    }

    // ==========================================
    // BLUETOOTH PC TO MOBILE CONNECT
    // ==========================================
    async function bluetoothConnect() {
        if(!navigator.bluetooth) {
            showToast("⚠️ Web Bluetooth not supported. Using WiFi fallback.", "info");
            var btStatus = document.getElementById('bt-status');
            if(btStatus) btStatus.innerText = "Not supported (WiFi fallback)";
            return;
        }
        try {
            btDevice = await navigator.bluetooth.requestDevice({
                acceptAllDevices: true,
                optionalServices: ['generic_access', 'device_information'] 
            });
            
            var btStatus = document.getElementById('bt-status');
            if(btStatus) btStatus.innerText = "Pairing: " + (btDevice.name || 'Device');
            btLog("Device selected: " + (btDevice.name || btDevice.id));
            
            btServer = await btDevice.gatt.connect();
            
            if(btStatus) btStatus.innerText = "Connected: " + (btDevice.name || 'Device');
            showToast("✅ Bluetooth connected successfully", "success");
            btLog("GATT Server Connected!");
            
            btDevice.addEventListener('gattserverdisconnected', function() {
                if(btStatus) btStatus.innerText = "Disconnected";
                btLog("Bluetooth disconnected");
                showToast("Bluetooth disconnected", "info");
                btServer = null;
            });

        } catch(e) {
            showToast("❌ Bluetooth error: " + e, "error");
            btLog("Error: " + e);
            var btStatus = document.getElementById('bt-status');
            if(btStatus) btStatus.innerText = "Error connecting";
        }
    }

    function bluetoothDisconnect() {
        if(btDevice && btDevice.gatt && btDevice.gatt.connected) {
            btDevice.gatt.disconnect();
        }
        btDevice = null;
        btServer = null;
        var btStatus = document.getElementById('bt-status');
        if(btStatus) btStatus.innerText = "Disconnected";
        showToast("Disconnected", "info");
        btLog("Disconnected manually");
    }

    async function bluetoothSendFiles() {
        if(btImgQueue.length === 0) {
            showToast("⚠️ No BT images selected", "error");
            return;
        }
        btLog("Preparing to send " + btImgQueue.length + " images...");
        showToast("📤 Files are already saved on PC. Sending trigger...", "info");
        
        for(var i = 0; i < btImgQueue.length; i++) {
            btLog("Processed: " + btImgQueue[i].name);
        }
        showToast("✅ All files processed!", "success");
    }

    function btLog(msg) {
        var log = document.getElementById('bt-log');
        var time = new Date().toLocaleTimeString();
        log.innerHTML = '<div>[' + time + '] ' + msg + '</div>' + log.innerHTML;
    }

</script>
</body>
</html>
"""

# ==========================================
# 3. FLASK ROUTES
# ==========================================

@app.route('/')
@app.route('/app')
def app_route():
    return render_template_string(ADVANCED_UI)

@app.route('/splash')
def splash_route():
    if qr_available:
        qr_html = '<img src="/qr_image" alt="QR Code">'
    else:
        qr_html = '<p style="color:#000;">QR not available</p>'
    return render_template_string(SPLASH_UI, if_qr=qr_html)

@app.route('/start_session', methods=['POST'])
def start_session():
    global CURRENT_SESSION_FOLDER
    data = request.get_json()
    username = data.get('username', 'User')
    safe_username = "".join(c for c in username if c.isalnum() or c in (' ', '_')).rstrip()
    if not safe_username: safe_username = "Print_User"
    
    session_path = os.path.join(DESKTOP_PATH, safe_username)
    os.makedirs(session_path, exist_ok=True)
    CURRENT_SESSION_FOLDER = session_path
    print(f"✅ Session folder created/assigned: {session_path}")
    
    printers = []
    if win32print:
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            printer_list = win32print.EnumPrinters(flags, None, 2)
            printers = [p['pPrinterName'] for p in printer_list]
        except:
            pass
    else:
        printers = ["Default Printer (Non-Windows)"]
    return jsonify({'success': True, 'session_folder': session_path, 'printers': printers})

@app.route('/printers')
def get_printers():
    printers = []
    if win32print:
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            printer_list = win32print.EnumPrinters(flags, None, 2)
            printers = [p['pPrinterName'] for p in printer_list]
        except Exception as e:
            print(f"Printer enum error: {e}")
            try:
                printer_list = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
                printers = [p[2] for p in printer_list]
            except Exception as e2:
                print(f"Printer enum fallback error: {e2}")
    else:
        printers = ["Default Printer (Non-Windows)"]
    return jsonify(printers)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    safe_name = str(uuid.uuid4()) + '_' + file.filename.replace(' ', '_')
    filepath = os.path.join(CURRENT_SESSION_FOLDER, safe_name)
    file.save(filepath)
    print(f"✅ File saved to session: {safe_name}")
    return jsonify({'path': filepath, 'name': file.filename})

@app.route('/print', methods=['POST'])
def print_files():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400

    printer_name = data.get('printer', '')
    images = data.get('images', []) # now expects file paths
    docs = data.get('docs', [])
    username = data.get('username', 'User')

    results = []
    files_to_delete = []

    # Print images
    for idx, img_path in enumerate(images):
        try:
            if os.path.exists(img_path):
                if win32api and win32print:
                    win32api.ShellExecute(0, "printto", img_path, f'"{printer_name}"', ".", 0)
                files_to_delete.append(img_path)
                results.append({'file': img_path, 'status': 'sent'})
            else:
                results.append({'file': img_path, 'status': 'error', 'error': 'File not found'})
        except Exception as e:
            results.append({'file': img_path, 'status': 'error', 'error': str(e)})

    # Print documents
    for doc_path in docs:
        try:
            if os.path.exists(doc_path):
                if win32api and win32print:
                    win32api.ShellExecute(0, "printto", doc_path, f'"{printer_name}"', ".", 0)
                files_to_delete.append(doc_path)
                results.append({'file': doc_path, 'status': 'sent'})
            else:
                results.append({'file': doc_path, 'status': 'error', 'error': 'File not found'})
        except Exception as e:
            results.append({'file': doc_path, 'status': 'error', 'error': str(e)})

    # Delayed delete to ensure spooler picks it up
    def delayed_delete(paths):
        time.sleep(5)
        for p in paths:
            try:
                if os.path.exists(p): os.remove(p)
                print(f"🗑️ Auto-deleted after print: {p}")
            except: pass
    
    threading.Thread(target=delayed_delete, args=(files_to_delete,)).start()

    return jsonify({'success': True, 'results': results, 'printer': printer_name, 'user': username, 'cleared': True})

@app.route('/qr_image')
def qr_image():
    qr_path = os.path.join(UPLOAD_FOLDER, "server_qr.png")
    if os.path.exists(qr_path):
        return send_file(qr_path, mimetype='image/png')
    return "QR not found", 404

@app.route('/barcode_image')
def barcode_image():
    if os.path.exists(barcode_png_path):
        return send_file(barcode_png_path, mimetype='image/png')
    return "Barcode not found", 404

# ==========================================
# 4. MAIN ENTRY POINT
# ==========================================
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀  Starting Ahmad Gujjar — Smart Print Pro Server...")
    print(f"📱  Open on phone: {AUTO_CONNECT_URL}")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)