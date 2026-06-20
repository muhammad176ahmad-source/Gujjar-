import streamlit as st
import os
import time
import socket
import shutil
import threading
import base64
from io import BytesIO
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
    print("⚠️ 'qrcode' library not installed. Run: pip install qrcode[pil]")

# Barcode library
try:
    import barcode as barcode_lib
    from barcode.writer import ImageWriter
except ImportError:
    barcode_lib = None
    print("⚠️ 'python-barcode' library not installed. Run: pip install python-barcode")

# Windows printer modules
try:
    import win32print
    import win32api
    import win32con
except ImportError:
    win32print = None
    win32api = None
    win32con = None

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Ahmad Gujjar — Smart Print Pro", page_icon="🔥", layout="centered")

# ==========================================
# UPLOAD FOLDER
# ==========================================
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

CURRENT_SESSION_FOLDER = UPLOAD_FOLDER

# ==========================================
# AUTO IP DETECTION
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
PORT = 8501
AUTO_CONNECT_URL = f"http://{LOCAL_IP}:{PORT}"

print("=" * 60)
print(f"🌐  AUTO-DETECTED PC / ROUTER IP : {LOCAL_IP}")
print(f"🔗  APP LINK (open on any device) : {AUTO_CONNECT_URL}")
print("=" * 60)

# ==========================================
# QR CODE GENERATION
# ==========================================
def generate_qr_code(data):
    if not qrcode:
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return buffered.getvalue()
    except Exception as e:
        print(f"⚠️ QR error: {e}")
        return None

# ==========================================
# BARCODE GENERATION
# ==========================================
def generate_barcode(data):
    if not barcode_lib:
        return None
    try:
        CODE128 = barcode_lib.get_barcode_class('code128')
        bar = CODE128(data, writer=ImageWriter())
        temp_path = os.path.join(UPLOAD_FOLDER, "temp_barcode_streamlit")
        saved = bar.save(temp_path, options={
            'module_width': 0.5,
            'module_height': 25.0,
            'font_size': 14,
            'text_distance': 5.0,
            'quiet_zone': 6.5,
            'write_text': True,
        })
        with open(saved, 'rb') as f:
            img_data = f.read()
        try:
            os.remove(saved)
        except OSError:
            pass
        return img_data
    except Exception as e:
        print(f"⚠️ Barcode error: {e}")
        return None

# ==========================================
# GET PRINTERS (Windows)
# ==========================================
def get_printers():
    if not win32print:
        return []
    try:
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return [printer[2] for printer in printers]
    except Exception as e:
        print(f"⚠️ Printer enum error: {e}")
        return []

# ==========================================
# TEST TARGET PC CONNECTION
# ==========================================
def test_target_connection(target_ip):
    if not requests:
        return False, "'requests' library not installed"
    try:
        url = f"http://{target_ip}:{PORT}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return True, "Connection successful!"
        else:
            return False, f"Status code: {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused — target PC app may not be running"
    except requests.exceptions.Timeout:
        return False, "Connection timed out"
    except Exception as e:
        return False, str(e)

# ==========================================
# SEND FILES TO TARGET PC
# ==========================================
def send_files_to_pc(target_ip, file_paths):
    if not requests:
        return False, "'requests' library not installed"
    try:
        url = f"http://{target_ip}:{PORT}/receive"
        files = []
        for fp in file_paths:
            files.append(('files', (os.path.basename(fp), open(fp, 'rb'))))
        resp = requests.post(url, files=files, timeout=30)
        for _, (_, f) in files:
            f.close()
        if resp.status_code == 200:
            return True, "Files sent successfully!"
        else:
            return False, f"Error: {resp.status_code}"
    except Exception as e:
        return False, str(e)

# ==========================================
# PRINT IMAGE USING WINDOWS PRINTER
# ==========================================
def print_image_win(image_path, printer_name=None):
    if not win32print or not win32api:
        return False, "Windows printing not available (pywin32 not installed)"
    try:
        if printer_name is None:
            printer_name = win32print.GetDefaultPrinter()
        printer_dc = win32print.CreateDC("WINSPOOL", printer_name, None, None)
        dc = win32api.CreateCompatibleDC(printer_dc)
        img = Image.open(image_path)
        img = img.convert("RGB")
        printable_width = win32print.GetDeviceCaps(printer_dc, win32con.PHYSICALWIDTH)
        printable_height = win32print.GetDeviceCaps(printer_dc, win32con.PHYSICALHEIGHT)
        scale = min(printable_width / img.width, printable_height / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        dib = ImageWin.Dib(img)
        dib.draw(dc, (0, 0, new_w, new_h))
        win32api.DeleteDC(dc)
        win32print.DeleteDC(printer_dc)
        return True, f"Printed to {printer_name}"
    except Exception as e:
        return False, str(e)

# ==========================================
# SESSION STATE INIT
# ==========================================
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'username' not in st.session_state:
    st.session_state.username = "Ahmad"
if 'images' not in st.session_state:
    st.session_state.images = []
if 'docs' not in st.session_state:
    st.session_state.docs = []
if 'selected_printer' not in st.session_state:
    st.session_state.selected_printer = None
if 'splash_done' not in st.session_state:
    st.session_state.splash_done = False

# ==========================================
# INJECT ALL CSS — REAL BUTTONS, NO GLASS ON BUTTONS
# ==========================================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Pacifico&family=Lobster&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
    :root {
        --primary: #059669;
        --primary-dark: #047857;
        --primary-darker: #065f46;
        --glass-bg: rgba(255, 255, 255, 0.65);
        --glass-border: rgba(255, 255, 255, 0.5);
        --text: #064e3b;
        --text-sub: #047857;
        --success: #10b981;
        --danger: #ef4444;
        --wa-green: #25D366;
        --footer-bg: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    }

    /* ===== BACKGROUND ===== */
    .stApp {
        background: url('https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=1920&auto=format&fit=crop') no-repeat center center fixed;
        background-size: cover;
    }

    /* ===== SIDEBAR ===== */
    section[data-testid="stSidebar"] {
        background: rgba(255,255,255,0.85) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-right: 2px solid rgba(5,150,105,0.3) !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        width: 100% !important;
    }

    /* ===== INPUTS & LABELS ===== */
    div[data-testid="stTextInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stFileUploader"] label {
        color: #064e3b !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
    }
    div[data-testid="stTextInput"] input,
    div[data-testid="stSelectbox"] select {
        background: #ffffff !important;
        border: 2px solid #d1d5db !important;
        border-radius: 14px !important;
        color: #064e3b !important;
        font-size: 1rem !important;
        padding: 14px 16px !important;
        min-height: 50px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
        transition: border-color 0.2s, box-shadow 0.2s !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stSelectbox"] select:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 4px rgba(5,150,105,0.15) !important;
        outline: none !important;
    }
    div[data-testid="stFileUploader"] section {
        background: #ffffff !important;
        border: 2px dashed #a7f3d0 !important;
        border-radius: 18px !important;
        padding: 28px 16px !important;
        transition: all 0.25s ease !important;
    }
    div[data-testid="stFileUploader"] section:hover {
        border-color: var(--primary) !important;
        background: #f0fdf4 !important;
    }

    /* =========================================================
       REAL SOLID BUTTONS — NO GLASS, PROPER LOOKING
       ========================================================= */
    .stButton > button {
        /* Remove all glass/blur from buttons */
        background: transparent !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        position: relative !important;
        overflow: hidden !important;
    }

    /* Primary green button */
    .stButton > button[kind="primary"],
    .stButton > button[kind="primaryFormSubmit"] {
        background: linear-gradient(135deg, #059669, #047857) !important;
        color: #ffffff !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        padding: 16px 32px !important;
        border-radius: 16px !important;
        border: 2px solid #047857 !important;
        box-shadow: 0 6px 20px rgba(5,150,105,0.35), inset 0 1px 0 rgba(255,255,255,0.2) !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
        letter-spacing: 0.5px !important;
        cursor: pointer !important;
        transition: all 0.25s ease !important;
        min-height: 54px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[kind="primaryFormSubmit"]:hover {
        background: linear-gradient(135deg, #047857, #065f46) !important;
        border-color: #065f46 !important;
        box-shadow: 0 10px 28px rgba(5,150,105,0.45), inset 0 1px 0 rgba(255,255,255,0.2) !important;
        transform: translateY(-2px) !important;
    }
    .stButton > button[kind="primary"]:active,
    .stButton > button[kind="primaryFormSubmit"]:active {
        transform: translateY(0) !important;
        box-shadow: 0 4px 12px rgba(5,150,105,0.3) !important;
    }

    /* Secondary / default button */
    .stButton > button[kind="secondary"] {
        background: #ffffff !important;
        color: #064e3b !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        padding: 14px 28px !important;
        border-radius: 14px !important;
        border: 2px solid #d1d5db !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
        cursor: pointer !important;
        transition: all 0.25s ease !important;
        min-height: 50px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #f0fdf4 !important;
        border-color: var(--primary) !important;
        color: var(--primary-dark) !important;
        box-shadow: 0 6px 18px rgba(5,150,105,0.15) !important;
        transform: translateY(-2px) !important;
    }
    .stButton > button[kind="secondary"]:active {
        transform: translateY(0) !important;
    }

    /* Small delete / icon buttons inside grids */
    div[data-testid="stVerticalBlock"] > div > div > div.stButton > button,
    .small-del-btn button {
        background: #f3f4f6 !important;
        color: #374151 !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        padding: 10px 16px !important;
        border-radius: 12px !important;
        border: 2px solid #e5e7eb !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06) !important;
        min-height: 42px !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stVerticalBlock"] > div > div > div.stButton > button:hover,
    .small-del-btn button:hover {
        background: #fef2f2 !important;
        border-color: #fca5a5 !important;
        color: #dc2626 !important;
        box-shadow: 0 4px 10px rgba(239,68,68,0.15) !important;
        transform: translateY(-1px) !important;
    }

    /* ===== GLASS CARDS (only on cards, NOT on buttons) ===== */
    .glass-card {
        background: var(--glass-bg);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 24px;
        padding: 28px;
        margin-bottom: 22px;
        border: 1px solid var(--glass-border);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.12);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .glass-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.18);
    }

    .card-title {
        font-size: 0.85rem;
        color: var(--text-sub);
        margin-bottom: 18px;
        text-transform: uppercase;
        letter-spacing: 1.8px;
        font-weight: 800;
        border-bottom: 2px solid rgba(5, 150, 105, 0.2);
        padding-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* ===== STATS ===== */
    .stat-chip {
        text-align: center;
        background: #ffffff;
        border: 2px solid #e5e7eb;
        border-radius: 16px;
        padding: 14px 8px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.06);
    }
    .stat-num {
        font-family: 'Orbitron', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--primary);
    }
    .stat-label {
        font-size: 0.7rem;
        color: var(--text-sub);
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 4px;
        font-weight: 600;
    }

    /* ===== IP PILL ===== */
    .ip-pill {
        background: #f0fdf4;
        color: #047857;
        border: 2px solid #a7f3d0;
        border-radius: 12px;
        padding: 10px 14px;
        font-size: 0.9rem;
        font-weight: 700;
        word-break: break-all;
        text-align: center;
        box-shadow: 0 2px 8px rgba(5,150,105,0.1);
    }

    /* ===== DOC ITEMS ===== */
    .doc-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #ffffff;
        padding: 14px 16px;
        border-radius: 14px;
        margin-bottom: 10px;
        border: 2px solid #e5e7eb;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: all 0.2s;
    }
    .doc-item:hover {
        border-color: #a7f3d0;
        box-shadow: 0 4px 14px rgba(5,150,105,0.1);
        transform: translateX(4px);
    }

    /* ===== BANNER ===== */
    .banner {
        position: relative;
        width: 100%;
        height: 220px;
        overflow: hidden;
        background: #000;
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
        border-bottom: 4px solid var(--primary);
        margin-bottom: 20px;
    }
    .banner-img {
        position: absolute;
        inset: 0;
        background-image: url('https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=1920&auto=format&fit=crop');
        background-size: cover;
        background-position: center;
    }
    .banner-overlay {
        position: absolute;
        inset: 0;
        background: linear-gradient(135deg, rgba(0,30,0,0.55), rgba(0,0,0,0.35));
    }
    .banner-text {
        position: relative;
        z-index: 2;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 100%;
        padding: 20px;
        text-align: center;
    }
    .banner-text h2 {
        font-family: 'Pacifico', cursive;
        font-size: 2.2rem;
        margin: 0;
        color: #fff;
        text-shadow: 0 3px 10px rgba(0,0,0,0.6);
    }
    .banner-text p {
        margin-top: 8px;
        color: #bbf7d0;
        font-size: 1rem;
        letter-spacing: 1px;
        font-weight: 500;
    }
    .banner-pulse {
        position: absolute;
        bottom: 14px;
        right: 18px;
        display: flex;
        align-items: center;
        gap: 6px;
        background: rgba(0,0,0,0.6);
        padding: 8px 14px;
        border-radius: 22px;
        color: #4ade80;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid rgba(74,222,128,0.3);
    }
    .live-dot {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: #4ade80;
        box-shadow: 0 0 8px #4ade80;
        animation: liveBlink 1.4s infinite;
    }
    @keyframes liveBlink {
        0%,100% { opacity: 1; }
        50% { opacity: 0.3; }
    }

    /* ===== NAV BAR ===== */
    .nav-bar {
        display: flex;
        justify-content: center;
        gap: 10px;
        padding: 10px 14px;
        flex-wrap: wrap;
        background: rgba(255,255,255,0.6);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--glass-border);
        box-shadow: 0 3px 14px rgba(0,0,0,0.06);
        margin-bottom: 22px;
        border-radius: 16px;
    }
    .nav-link {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 10px 20px;
        border-radius: 24px;
        font-size: 0.92rem;
        font-weight: 700;
        color: #064e3b;
        text-decoration: none;
        background: #ffffff;
        border: 2px solid #e5e7eb;
        transition: all 0.25s ease;
        cursor: pointer;
        white-space: nowrap;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .nav-link:hover {
        background: linear-gradient(135deg, #059669, #047857);
        color: #fff;
        border-color: #047857;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(5,150,105,0.35);
    }

    /* ===== HEADER ===== */
    .app-header {
        background: rgba(255,255,255,0.75);
        backdrop-filter: blur(15px);
        -webkit-backdrop-filter: blur(15px);
        padding: 14px 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid var(--glass-border);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        border-radius: 16px;
        margin-bottom: 12px;
    }
    .header-title {
        font-family: 'Pacifico', cursive;
        font-size: 1.5rem;
        background: linear-gradient(45deg, #059669, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .live-clock {
        font-family: 'Orbitron', monospace;
        font-size: 0.9rem;
        font-weight: 700;
        color: #047857;
        background: #ffffff;
        padding: 8px 14px;
        border-radius: 12px;
        border: 2px solid #d1d5db;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        letter-spacing: 1px;
    }
    .status-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #cbd5e1;
        border: 3px solid #ffffff;
        box-shadow: 0 0 0 1px #cbd5e1, 0 2px 6px rgba(0,0,0,0.1);
        display: inline-block;
        transition: all 0.3s;
    }
    .status-dot.active {
        background: var(--success);
        box-shadow: 0 0 0 1px var(--success), 0 0 0 4px rgba(16,185,129,0.2), 0 2px 6px rgba(0,0,0,0.1);
        animation: pulseGreen 2s infinite;
    }
    @keyframes pulseGreen {
        0%,100% { box-shadow: 0 0 0 1px var(--success), 0 0 0 0 rgba(16,185,129,0.4); }
        50% { box-shadow: 0 0 0 1px var(--success), 0 0 0 10px rgba(16,185,129,0); }
    }

    /* ===== SPLASH ===== */
    .splash-screen {
        position: fixed;
        inset: 0;
        background: #000;
        z-index: 99999;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        overflow: hidden;
    }
    .splash-bg {
        position: absolute;
        inset: 0;
        background-image: url('https://upload.wikimedia.org/wikipedia/commons/9/9e/Imran_Khan_November_2019.jpg');
        background-size: cover;
        background-position: center top;
        animation: zoomEffect 12s infinite alternate;
        opacity: 0.9;
    }
    .splash-overlay {
        position: absolute;
        inset: 0;
        background: linear-gradient(to bottom, rgba(0,0,0,0.1), rgba(0,20,0,0.6));
    }
    .splash-content {
        position: relative;
        z-index: 10;
        text-align: center;
        animation: slideUpFade 2s ease-out;
    }
    .splash-title {
        font-family: 'Lobster', 'Pacifico', cursive;
        font-size: clamp(2.5rem, 9vw, 6rem);
        margin: 0;
        line-height: 1.1;
        letter-spacing: 1px;
        color: #fff;
        text-shadow: 0 4px 15px rgba(0,0,0,0.8);
    }
    .splash-sub {
        color: #4ade80;
        font-size: 1.3rem;
        margin-top: 18px;
        letter-spacing: 4px;
        font-weight: 300;
        text-shadow: 0 2px 5px rgba(0,0,0,0.8);
    }
    .splash-loader {
        width: 260px;
        height: 6px;
        border-radius: 3px;
        background: rgba(255,255,255,0.15);
        overflow: hidden;
        margin: 35px auto 0 auto;
    }
    .splash-loader-bar {
        height: 100%;
        width: 0%;
        background: linear-gradient(90deg, #4ade80, #22d3ee, #fde047);
        border-radius: 3px;
        animation: loadFill 4s linear forwards;
    }
    @keyframes loadFill { from { width: 0%; } to { width: 100%; } }
    @keyframes zoomEffect { 0% { transform: scale(1); } 100% { transform: scale(1.15); } }
    @keyframes slideUpFade { 0% { opacity: 0; transform: translateY(50px); } 100% { opacity: 1; transform: translateY(0); } }

    /* ===== FOOTER ===== */
    .main-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        border-top: 3px solid transparent;
        border-image: linear-gradient(90deg, #10b981, #22d3ee, #fde047, #22d3ee, #10b981) 1;
        z-index: 90;
        box-shadow: 0 -10px 40px rgba(0,0,0,0.3);
        animation: footerRise 0.8s ease-out;
    }
    @keyframes footerRise {
        from { transform: translateY(100%); }
        to { transform: translateY(0); }
    }
    .footer-inner {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 16px 24px;
        max-width: 700px;
        margin: 0 auto;
    }
    .footer-img-wrap {
        position: relative;
        flex-shrink: 0;
        width: 68px;
        height: 68px;
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
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .footer-title {
        font-family: 'Pacifico', cursive;
        font-size: 1.15rem;
        margin: 0;
        color: #fff;
        text-shadow: 0 2px 8px rgba(0,0,0,0.5);
    }
    .footer-subtitle {
        font-size: 0.75rem;
        margin: 3px 0 0 0;
        color: #67e8f9;
        letter-spacing: 1px;
    }
    .footer-quote {
        font-size: 0.7rem;
        margin: 4px 0 0 0;
        color: rgba(255,255,255,0.6);
        font-style: italic;
    }
    .footer-clock-time {
        font-family: 'Orbitron', monospace;
        font-size: 1.05rem;
        font-weight: 700;
        color: #67e8f9;
        text-shadow: 0 0 8px rgba(103, 232, 249, 0.4);
    }
    .footer-clock-date {
        font-size: 0.68rem;
        color: rgba(255,255,255,0.5);
        margin-top: 3px;
    }
    .footer-bottom-bar {
        background: rgba(0,0,0,0.3);
        padding: 6px 24px;
        text-align: center;
        font-size: 0.68rem;
        color: rgba(255,255,255,0.4);
        letter-spacing: 0.5px;
    }

    /* ===== WA SHARE BUTTON ===== */
    .wa-share-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 14px 28px;
        border-radius: 16px;
        font-size: 1rem;
        font-weight: 700;
        color: #ffffff;
        background: linear-gradient(135deg, #25D366, #128C7E);
        text-decoration: none;
        border: 2px solid #128C7E;
        box-shadow: 0 6px 20px rgba(37,211,102,0.35);
        transition: all 0.25s ease;
        cursor: pointer;
        width: 100%;
        text-align: center;
    }
    .wa-share-btn:hover {
        background: linear-gradient(135deg, #128C7E, #075E54);
        border-color: #075E54;
        transform: translateY(-2px);
        box-shadow: 0 10px 28px rgba(37,211,102,0.45);
    }

    /* ===== BT LOG ===== */
    .bt-log {
        margin-top: 14px;
        font-size: 0.82rem;
        color: #374151;
        max-height: 150px;
        overflow-y: auto;
        background: #ffffff;
        padding: 14px;
        border-radius: 14px;
        border: 2px solid #e5e7eb;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }

    /* ===== PRINT READY CARD ===== */
    .print-ready-card {
        background: #f0fdf4;
        backdrop-filter: none;
        border: 3px solid #10b981;
        border-radius: 24px;
        padding: 28px;
        margin-bottom: 22px;
        box-shadow: 0 8px 32px rgba(16,185,129,0.15);
    }

    /* ===== RESPONSIVE ===== */
    @media (max-width: 640px) {
        .banner { height: 180px; }
        .banner-text h2 { font-size: 1.6rem; }
        .banner-text p { font-size: 0.85rem; }
        .app-header { padding: 10px 16px; }
        .header-title { font-size: 1.2rem; }
        .live-clock { font-size: 0.78rem; padding: 6px 10px; }
        .nav-bar { gap: 6px; padding: 8px 10px; }
        .nav-link { padding: 8px 14px; font-size: 0.82rem; }
        .glass-card { padding: 20px; border-radius: 20px; }
        .card-title { font-size: 0.78rem; margin-bottom: 14px; }
        .stat-num { font-size: 1.1rem; }
        .footer-inner { padding: 12px 16px; gap: 12px; }
        .footer-img-wrap { width: 52px; height: 52px; }
        .footer-title { font-size: 0.95rem; }
        .footer-subtitle { font-size: 0.65rem; }
        .footer-quote { font-size: 0.6rem; }
        .footer-clock-time { font-size: 0.85rem; }
        
        .stButton > button[kind="primary"],
        .stButton > button[kind="primaryFormSubmit"] {
            font-size: 0.95rem !important;
            padding: 14px 24px !important;
            min-height: 50px !important;
            border-radius: 14px !important;
        }
        .stButton > button[kind="secondary"] {
            font-size: 0.9rem !important;
            padding: 12px 20px !important;
            min-height: 46px !important;
        }
    }

    @media (min-width: 1024px) {
        .banner { height: 260px; }
        .banner-text h2 { font-size: 2.6rem; }
        .glass-card { padding: 32px; }
        .stButton > button[kind="primary"],
        .stButton > button[kind="primaryFormSubmit"] {
            font-size: 1.1rem !important;
            padding: 18px 36px !important;
            min-height: 58px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SPLASH SCREEN
# ==========================================
if not st.session_state.splash_done:
    splash_ph = st.empty()
    with splash_ph.container():
        st.markdown("""
        <div class="splash-screen" id="splash-screen">
            <div class="splash-bg"></div>
            <div class="splash-overlay"></div>
            <div class="splash-content">
                <h1 class="splash-title">Ahmad Gujjar</h1>
                <p class="splash-sub">SMART PRINT PRO</p>
                <div class="splash-loader">
                    <div class="splash-loader-bar"></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    time.sleep(4)
    splash_ph.empty()
    st.session_state.splash_done = True
    st.rerun()

# ==========================================
# BANNER
# ==========================================
st.markdown("""
<div class="banner">
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
""", unsafe_allow_html=True)

# ==========================================
# HEADER
# ==========================================
now = time.localtime()
time_str = time.strftime("%H:%M:%S", now)
status_class = "active" if st.session_state.connected else ""

st.markdown(f"""
<div class="app-header">
    <h1 class="header-title">Ahmad Gujjar</h1>
    <div style="display:flex; align-items:center; gap:12px;">
        <div class="live-clock">{time_str}</div>
        <span class="status-dot {status_class}"></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# NAV BAR
# ==========================================
st.markdown("""
<div class="nav-bar">
    <a href="https://www.rekhta.org/" target="_blank" rel="noopener" class="nav-link">
        <span>📚</span> Poetry
    </a>
    <a href="https://www.dawateislami.net/islamic-books/hadees" target="_blank" rel="noopener" class="nav-link">
        <span>📖</span> Hadees
    </a>
    <a href="https://www.dawateislami.net/islamic-calendar" target="_blank" rel="noopener" class="nav-link">
        <span>📅</span> Islamic Calendar
    </a>
    <a href="https://dailypakistan.com.pk" target="_blank" rel="noopener" class="nav-link">
        <span>📰</span> News
    </a>
</div>
""", unsafe_allow_html=True)

# ==========================================
# STATS BAR
# ==========================================
sel_img_count = len([img for img in st.session_state.images if img['selected']])
printers_list = get_printers()

st.markdown(f"""
<div style="display:flex; gap:10px; margin-bottom:22px;">
    <div class="stat-chip" style="flex:1;">
        <div class="stat-num">{sel_img_count}</div>
        <div class="stat-label">Images</div>
    </div>
    <div class="stat-chip" style="flex:1;">
        <div class="stat-num">{len(st.session_state.docs)}</div>
        <div class="stat-label">Docs</div>
    </div>
    <div class="stat-chip" style="flex:1;">
        <div class="stat-num">{len(printers_list)}</div>
        <div class="stat-label">Printers</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.title("🔥 Menu")
    st.write("---")
    
    st.subheader("📡 Connection Info")
    st.markdown(f'<div class="ip-pill">{AUTO_CONNECT_URL}</div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("📷 QR Code")
    qr_data = generate_qr_code(AUTO_CONNECT_URL)
    if qr_data:
        st.image(qr_data, width=200, caption="Scan to Connect")
    else:
        st.warning("QR Code not available.\nInstall: pip install qrcode[pil]")
    
    st.write("---")
    st.subheader("📊 Barcode")
    bc_data = generate_barcode(AUTO_CONNECT_URL)
    if bc_data:
        st.image(bc_data, width=280, caption="CODE128 Barcode")
    else:
        st.warning("Barcode not available.\nInstall: pip install python-barcode")
    
    st.write("---")
    st.subheader("📤 WhatsApp Share")
    wa_text = f"Ahmad Gujjar Smart Print Pro - Connect here: {AUTO_CONNECT_URL}"
    wa_url = f"https://wa.me/?text={wa_text}"
    st.markdown(f'<a href="{wa_url}" target="_blank" class="wa-share-btn">💬 Share on WhatsApp</a>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader("🖨️ Available Printers")
    if printers_list:
        for p in printers_list:
            st.markdown(f"• `{p}`")
    else:
        st.info("No printers detected.\n(Windows only — needs pywin32)")
    
    st.write("---")
    st.caption("© 2024 Ahmad Gujjar\nAll Rights Reserved")

# ==========================================
# 1. START PRINT SESSION
# ==========================================
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown('<div class="card-title">🔒 1. Start Print Session</div>', unsafe_allow_html=True)

username = st.text_input("Enter Your Name", value=st.session_state.username, key="session_name")
if st.button("🚀 Start Session", use_container_width=True, type="primary"):
    if username.strip():
        st.session_state.username = username.strip()
        st.session_state.connected = True
        st.success(f"✅ Session started for {username.strip()}!")
        st.rerun()
    else:
        st.error("❌ Please enter your name")

st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# ONLY SHOW REST IF CONNECTED
# ==========================================
if st.session_state.connected:

    # ==========================================
    # 2. SELECT PRINTER
    # ==========================================
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🖨️ 2. Select Printer</div>', unsafe_allow_html=True)
    
    if printers_list:
        sel_printer = st.selectbox("Choose Printer", printers_list, index=0, key="printer_select")
        st.session_state.selected_printer = sel_printer
        st.success(f"✅ Selected: {sel_printer}")
    else:
        st.warning("No printers found. You're not on Windows or no printer is installed.")
        st.info("Install pywin32: pip install pywin32")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 3. SEND TO ANOTHER PC
    # ==========================================
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">💻 3. Send to Another PC</div>', unsafe_allow_html=True)
    
    target_ip = st.text_input("Target PC IP (e.g. 192.168.1.5)", key="target_ip_input")
    st.caption("Note: Target PC must have this app running on same network.")
    
    col_test, col_send = st.columns(2)
    with col_test:
        if st.button("🔗 Test Connection", use_container_width=True, type="primary"):
            if target_ip.strip():
                with st.spinner(f"Testing connection to {target_ip.strip()}..."):
                    ok, msg = test_target_connection(target_ip.strip())
                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")
            else:
                st.error("❌ Enter target IP first")
    
    with col_send:
        if st.button("📤 Send Files", use_container_width=True, type="primary"):
            if target_ip.strip():
                all_files = [img['path'] for img in st.session_state.images if img['selected']]
                all_files += [doc['path'] for doc in st.session_state.docs]
                if all_files:
                    with st.spinner(f"Sending {len(all_files)} files to {target_ip.strip()}..."):
                        ok, msg = send_files_to_pc(target_ip.strip(), all_files)
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.warning("⚠️ No files selected to send")
            else:
                st.error("❌ Enter target IP first")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 4. DOCUMENT CENTER
    # ==========================================
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">📄 4. Document Center</div>', unsafe_allow_html=True)
    
    col_pdf, col_excel = st.columns(2)
    with col_pdf:
        pdf_file = st.file_uploader("Upload PDF", type=["pdf"], key="pdf_up", label_visibility="collapsed")
        if pdf_file:
            pdf_path = os.path.join(UPLOAD_FOLDER, pdf_file.name)
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
            if not any(d['name'] == pdf_file.name for d in st.session_state.docs):
                st.session_state.docs.append({"name": pdf_file.name, "path": pdf_path, "type": "pdf"})
                st.success(f"✅ PDF uploaded: {pdf_file.name}")
                st.rerun()
            else:
                st.info(f"📄 {pdf_file.name} already exists")
    
    with col_excel:
        excel_file = st.file_uploader("Upload Excel", type=["xls", "xlsx"], key="excel_up", label_visibility="collapsed")
        if excel_file:
            excel_path = os.path.join(UPLOAD_FOLDER, excel_file.name)
            with open(excel_path, "wb") as f:
                f.write(excel_file.getbuffer())
            if not any(d['name'] == excel_file.name for d in st.session_state.docs):
                st.session_state.docs.append({"name": excel_file.name, "path": excel_path, "type": "excel"})
                st.success(f"✅ Excel uploaded: {excel_file.name}")
                st.rerun()
            else:
                st.info(f"📊 {excel_file.name} already exists")
    
    if st.session_state.docs:
        st.write("**Uploaded Documents:**")
        for i, doc in enumerate(st.session_state.docs):
            icon = "📄" if doc["type"] == "pdf" else "📊"
            col_name, col_del = st.columns([5, 1])
            with col_name:
                st.markdown(f'<div class="doc-item"><span>{icon} <strong>{doc["name"]}</strong></span></div>', unsafe_allow_html=True)
            with col_del:
                if st.button("🗑️", key=f"del_doc_{i}"):
                    st.session_state.docs.pop(i)
                    try:
                        os.remove(doc["path"])
                    except OSError:
                        pass
                    st.rerun()
    else:
        st.info("No documents uploaded yet.")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 5. HD IMAGE GALLERY
    # ==========================================
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🖼️ 5. HD Image Gallery</div>', unsafe_allow_html=True)
    
    img_files = st.file_uploader("Upload HD Photos", type=["jpg", "jpeg", "png", "gif", "bmp", "webp"], accept_multiple_files=True, key="img_up", label_visibility="collapsed")
    
    if img_files:
        new_count = 0
        for img_file in img_files:
            img_path = os.path.join(UPLOAD_FOLDER, img_file.name)
            if not any(im['name'] == img_file.name for im in st.session_state.images):
                with open(img_path, "wb") as f:
                    f.write(img_file.getbuffer())
                st.session_state.images.append({"name": img_file.name, "path": img_path, "selected": False})
                new_count += 1
        if new_count > 0:
            st.success(f"✅ {new_count} new images uploaded!")
            st.rerun()
        else:
            st.info("All images already exist in gallery.")
    
    if st.session_state.images:
        cols = st.columns(4)
        for i, img in enumerate(st.session_state.images):
            with cols[i % 4]:
                try:
                    st.image(img["path"], use_container_width=True)
                except Exception:
                    st.warning(f"⚠️ Can't display {img['name']}")
                
                col_chk, col_btn = st.columns([1, 1])
                with col_chk:
                    new_sel = st.checkbox("✅", key=f"sel_img_{i}", value=img["selected"], label_visibility="collapsed")
                    if new_sel != img["selected"]:
                        st.session_state.images[i]["selected"] = new_sel
                with col_btn:
                    if st.button("🗑️", key=f"del_img_{i}"):
                        st.session_state.images.pop(i)
                        try:
                            os.remove(img["path"])
                        except OSError:
                            pass
                        st.rerun()
        
        sel_count = len([img for img in st.session_state.images if img["selected"]])
        st.markdown(f'<p style="text-align:center; font-size:1rem; color:#059669; margin-top:18px; font-weight:700;">{sel_count} Selected</p>', unsafe_allow_html=True)
    else:
        st.info("No images uploaded yet. Click above to add HD photos.")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 6. BLUETOOTH TRANSFER
    # ==========================================
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">🔵 6. Bluetooth Transfer</div>', unsafe_allow_html=True)
    
    st.caption("Pair your phone via Bluetooth and send images directly. Works on Chrome/Edge (Android) and Chrome (PC).")
    
    if 'bt_log' not in st.session_state:
        st.session_state.bt_log = ["Bluetooth log will appear here..."]
    
    col_pair, col_disc = st.columns(2)
    with col_pair:
        if st.button("🔵 Pair Device", use_container_width=True, type="primary"):
            st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Web Bluetooth API — not supported in Streamlit backend.")
            st.info("⚠️ Bluetooth requires browser Web Bluetooth API.\nUse the HTML/Flask version for full Bluetooth.")
    with col_disc:
        if st.button("❌ Disconnect", use_container_width=True, type="secondary"):
            st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Disconnected (no active connection)")
    
    bt_files = st.file_uploader("Pick Images for Bluetooth", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="bt_img_up", label_visibility="collapsed")
    
    if bt_files:
        st.success(f"📱 {len(bt_files)} BT images selected (ready for browser-based transfer)")
    
    if st.button("📤 Send via Bluetooth", use_container_width=True, type="primary"):
        st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Bluetooth send — requires Web Bluetooth API (browser only)")
        st.warning("Bluetooth file transfer requires Web Bluetooth API which is only available in browser context.")
    
    st.markdown('<div class="bt-log">', unsafe_allow_html=True)
    for log_line in st.session_state.bt_log:
        st.caption(log_line)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.caption("**Note:** If your browser doesn't support Web Bluetooth (e.g. iOS Safari, Firefox), the app falls back to WiFi transfer.")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # PRINT & SEND BUTTON
    # ==========================================
    sel_imgs = [img for img in st.session_state.images if img['selected']]
    
    if sel_imgs or st.session_state.docs:
        st.markdown('<div class="print-ready-card">', unsafe_allow_html=True)
        
        total_files = len(sel_imgs) + len(st.session_state.docs)
        st.markdown(f'<div class="card-title">🚀 Ready to Print & Send ({total_files} files)</div>', unsafe_allow_html=True)
        
        if sel_imgs:
            st.write(f"**Images:** {len(sel_imgs)} selected")
        if st.session_state.docs:
            st.write(f"**Documents:** {len(st.session_state.docs)}")
        
        if st.button("🚀 PRINT & SEND", use_container_width=True, type="primary"):
            if sel_imgs and st.session_state.selected_printer:
                for img in sel_imgs:
                    ok, msg = print_image_win(img['path'], st.session_state.selected_printer)
                    if ok:
                        st.success(f"🖨️ {img['name']} — {msg}")
                    else:
                        st.error(f"❌ {img['name']} — {msg}")
            elif sel_imgs and not st.session_state.selected_printer:
                st.warning("⚠️ No printer selected. Images not printed (but still in queue for PC transfer).")
            
            target = st.session_state.get('target_ip', '')
            if target and sel_imgs:
                all_paths = [img['path'] for img in sel_imgs]
                all_paths += [doc['path'] for doc in st.session_state.docs]
                with st.spinner("Sending to target PC..."):
                    ok, msg = send_files_to_pc(target.strip(), all_paths)
                if ok:
                    st.success(f"📤 {msg}")
                else:
                    st.error(f"❌ {msg}")
            
            st.balloons()
        
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# FOOTER (Imran Khan HD)
# ==========================================
now = time.localtime()
footer_time = time.strftime("%H:%M:%S", now)
days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
footer_date = f"{days[now.tm_wday]}, {now.tm_mday} {months[now.tm_mon - 1]}"

st.markdown(f"""
<div class="main-footer">
    <div class="footer-inner">
        <div class="footer-img-wrap">
            <img src="https://upload.wikimedia.org/wikipedia/commons/9/9e/Imran_Khan_November_2019.jpg"
                 alt="Imran Khan"
                 onerror="this.parentElement.innerHTML='<div style=\\'width:100%;height:100%;background:linear-gradient(135deg,#1a5276,#2ecc71);display:flex;align-items:center;justify-content:center;color:#fff;font-family:Orbitron,monospace;font-size:1.4rem;font-weight:900;\\'>IK</div>';">
        </div>
        <div style="flex:1; min-width:0;">
            <h3 class="footer-title">Ahmad Gujjar</h3>
            <p class="footer-subtitle">Smart Print Pro — Ultimate Edition</p>
            <p class="footer-quote">"Absolutely Not — A Stand for Sovereignty"</p>
        </div>
        <div style="flex-shrink:0; text-align:right;">
            <div class="footer-clock-time">{footer_time}</div>
            <div class="footer-clock-date">{footer_date}</div>
        </div>
    </div>
    <div class="footer-bottom-bar">
        &copy; 2024 Ahmad Gujjar — All Rights Reserved | Powered by Smart Print Pro
    </div>
</div>
""", unsafe_allow_html=True)

# Bottom spacing for fixed footer
st.markdown("<div style='height: 200px;'></div>", unsafe_allow_html=True)
