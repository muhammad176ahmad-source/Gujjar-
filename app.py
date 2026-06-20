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
        
        # Scale to printer
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
# INJECT ALL CSS (ORIGINAL GLASS DESIGN)
# ==========================================
st.markdown("""
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
    .stApp {
        background: url('https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=1920&auto=format&fit=crop') no-repeat center center fixed;
        background-size: cover;
    }
    section[data-testid="stSidebar"] {
        background: rgba(255,255,255,0.7) !important;
        backdrop-filter: blur(15px) !important;
        -webkit-backdrop-filter: blur(15px) !important;
        border-right: 1px solid rgba(255,255,255,0.5) !important;
    }
    div[data-testid="stTextInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stFileUploader"] label {
        color: #064e3b !important;
        font-weight: 600 !important;
    }
    div[data-testid="stTextInput"] input,
    div[data-testid="stSelectbox"] select {
        background: rgba(255,255,255,0.6) !important;
        border: 1px solid rgba(255,255,255,0.6) !important;
        border-radius: 14px !important;
        color: #064e3b !important;
        backdrop-filter: blur(5px) !important;
    }
    div[data-testid="stFileUploader"] section {
        background: rgba(255,255,255,0.4) !important;
        border: 2px dashed rgba(5, 150, 105, 0.3) !important;
        border-radius: 20px !important;
        backdrop-filter: blur(5px) !important;
    }
    .stButton > button[kind="primary"],
    .stButton > button {
        border-radius: 14px !important;
        font-weight: 600 !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(5, 150, 105, 0.4) !important;
    }
    .glass-card {
        background: var(--glass-bg);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 24px;
        padding: 25px;
        margin-bottom: 20px;
        border: 1px solid var(--glass-border);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
        transition: transform 0.3s ease;
    }
    .glass-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.2);
    }
    .card-title {
        font-size: 0.8rem;
        color: var(--text-sub);
        margin-bottom: 15px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        font-weight: 700;
        border-bottom: 1px solid rgba(5, 150, 105, 0.2);
        padding-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .stat-chip {
        text-align: center;
        background: rgba(255,255,255,0.5);
        border: 1px solid rgba(255,255,255,0.6);
        border-radius: 14px;
        padding: 10px 6px;
        backdrop-filter: blur(5px);
    }
    .stat-num {
        font-family: 'Orbitron', monospace;
        font-size: 1.2rem;
        font-weight: 700;
        color: var(--primary);
    }
    .stat-label {
        font-size: 0.65rem;
        color: var(--text-sub);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 2px;
    }
    .ip-pill {
        background: rgba(5, 150, 105, 0.12);
        color: #047857;
        border: 1px dashed rgba(5, 150, 105, 0.5);
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 0.85rem;
        font-weight: 600;
        word-break: break-all;
        text-align: center;
    }
    .doc-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(255,255,255,0.6);
        padding: 12px;
        border-radius: 14px;
        margin-bottom: 10px;
        border: 1px solid rgba(255,255,255,0.4);
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: 0.2s;
    }
    .doc-item:hover {
        background: rgba(255,255,255,0.9);
        transform: translateX(5px);
    }
    .img-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
        gap: 12px;
        margin-top: 15px;
    }
    .img-cell {
        position: relative;
        aspect-ratio: 1;
        border-radius: 16px;
        overflow: hidden;
        background: rgba(255,255,255,0.5);
        border: 2px solid transparent;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: 0.3s;
    }
    .img-cell.selected {
        border-color: var(--success);
        transform: scale(1.05);
        box-shadow: 0 8px 15px rgba(16, 185, 129, 0.3);
    }
    .img-cell img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }

    /* MAIN FOOTER */
    .main-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
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
        padding: 14px 20px;
        max-width: 700px;
        margin: 0 auto;
    }
    .footer-img-wrap {
        position: relative;
        flex-shrink: 0;
        width: 72px;
        height: 72px;
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
        font-size: 1.1rem;
        margin: 0;
        color: #fff;
        text-shadow: 0 2px 8px rgba(0,0,0,0.5);
    }
    .footer-subtitle {
        font-size: 0.72rem;
        margin: 2px 0 0 0;
        color: #67e8f9;
        letter-spacing: 1px;
    }
    .footer-quote {
        font-size: 0.68rem;
        margin: 3px 0 0 0;
        color: rgba(255,255,255,0.6);
        font-style: italic;
    }
    .footer-clock-time {
        font-family: 'Orbitron', monospace;
        font-size: 1rem;
        font-weight: 700;
        color: #67e8f9;
        text-shadow: 0 0 8px rgba(103, 232, 249, 0.4);
    }
    .footer-clock-date {
        font-size: 0.65rem;
        color: rgba(255,255,255,0.5);
        margin-top: 2px;
    }
    .footer-bottom-bar {
        background: rgba(0,0,0,0.3);
        padding: 5px 20px;
        text-align: center;
        font-size: 0.65rem;
        color: rgba(255,255,255,0.4);
        letter-spacing: 0.5px;
    }
    @media (max-width: 480px) {
        .footer-img-wrap { width: 56px; height: 56px; }
        .footer-title { font-size: 0.95rem; }
        .footer-subtitle { font-size: 0.65rem; }
        .footer-quote { font-size: 0.6rem; }
        .footer-clock-time { font-size: 0.85rem; }
    }

    /* BANNER */
    .banner {
        position: relative;
        width: 100%;
        height: 220px;
        overflow: hidden;
        background: #000;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
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
        font-size: 2rem;
        margin: 0;
        color: #fff;
        text-shadow: 0 3px 10px rgba(0,0,0,0.6);
    }
    .banner-text p {
        margin-top: 8px;
        color: #bbf7d0;
        font-size: 0.95rem;
        letter-spacing: 1px;
    }
    .banner-pulse {
        position: absolute;
        bottom: 14px;
        right: 18px;
        display: flex;
        align-items: center;
        gap: 6px;
        background: rgba(0,0,0,0.5);
        padding: 6px 12px;
        border-radius: 20px;
        color: #4ade80;
        font-size: 0.8rem;
    }
    .live-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #4ade80;
        box-shadow: 0 0 8px #4ade80;
        animation: liveBlink 1.4s infinite;
    }
    @keyframes liveBlink {
        0%,100% { opacity: 1; }
        50% { opacity: 0.3; }
    }

    /* NAV LINKS */
    .nav-bar {
        display: flex;
        justify-content: center;
        gap: 8px;
        padding: 8px 12px;
        flex-wrap: wrap;
        background: rgba(255,255,255,0.55);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-bottom: 1px solid var(--glass-border);
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        margin-bottom: 20px;
        border-radius: 10px;
    }
    .nav-link {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        border-radius: 22px;
        font-size: 0.9rem;
        font-weight: 600;
        color: #064e3b;
        text-decoration: none;
        background: rgba(255,255,255,0.6);
        border: 1px solid rgba(255,255,255,0.7);
        transition: all 0.25s ease;
        cursor: pointer;
        white-space: nowrap;
    }
    .nav-link:hover {
        background: linear-gradient(135deg, #059669, #10b981);
        color: #fff;
        transform: translateY(-2px);
        box-shadow: 0 6px 14px rgba(5,150,105,0.35);
    }

    /* HEADER */
    .app-header {
        background: var(--glass-bg);
        backdrop-filter: blur(15px);
        -webkit-backdrop-filter: blur(15px);
        padding: 12px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--glass-border);
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        border-radius: 14px;
        margin-bottom: 10px;
    }
    .header-title {
        font-family: 'Pacifico', cursive;
        font-size: 1.4rem;
        background: linear-gradient(45deg, #059669, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .live-clock {
        font-family: 'Orbitron', monospace;
        font-size: 0.85rem;
        font-weight: 700;
        color: #047857;
        background: rgba(255,255,255,0.4);
        padding: 6px 12px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.6);
        backdrop-filter: blur(5px);
        letter-spacing: 1px;
    }
    .status-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #cbd5e1;
        transition: 0.3s;
        border: 2px solid #fff;
        box-shadow: 0 0 0 1px #cbd5e1;
        display: inline-block;
    }
    .status-dot.active {
        background: var(--success);
        border-color: #fff;
        box-shadow: 0 0 0 1px var(--success);
        animation: pulseGreen 2s infinite;
    }
    @keyframes pulseGreen {
        0%,100% { box-shadow: 0 0 0 1px var(--success), 0 0 0 0 rgba(16,185,129,0.4); }
        50% { box-shadow: 0 0 0 1px var(--success), 0 0 0 8px rgba(16,185,129,0); }
    }

    /* SPLASH */
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
        width: 240px;
        height: 5px;
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

    /* PRINT BTN */
    .print-float-btn {
        position: fixed;
        bottom: 120px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 95;
        width: 90%;
        max-width: 560px;
    }

    /* WA SHARE BTN */
    .wa-share-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 18px;
        border-radius: 22px;
        font-size: 0.85rem;
        font-weight: 600;
        color: white;
        background: var(--wa-green);
        text-decoration: none;
        transition: all 0.25s ease;
        cursor: pointer;
        border: none;
    }
    .wa-share-btn:hover {
        background: #1ebc57;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(37, 211, 102, 0.4);
    }

    /* BT LOG */
    .bt-log {
        margin-top: 12px;
        font-size: 0.8rem;
        color: #374151;
        max-height: 140px;
        overflow-y: auto;
        background: rgba(255,255,255,0.5);
        padding: 10px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.5);
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
    <div style="display:flex; align-items:center; gap:10px;">
        <div class="live-clock">{time_str}</div>
        <span class="status-dot {status_class}"></span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# NAV BAR (Poetry, Islamic, News)
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
<div style="display:flex; gap:8px; margin-bottom:20px;">
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
# SIDEBAR — QR / BARCODE / INFO
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
    
    # Display docs list
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
    
    # Display images with select/delete
    if st.session_state.images:
        cols = st.columns(4)
        for i, img in enumerate(st.session_state.images):
            with cols[i % 4]:
                sel_border = "selected" if img["selected"] else ""
                try:
                    st.image(img["path"], width=120, use_container_width=True)
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
        st.markdown(f'<p style="text-align:center; font-size:0.9rem; color:#059669; margin-top:15px; font-weight:500;">{sel_count} Selected</p>', unsafe_allow_html=True)
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
            st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Web Bluetooth API — not supported in Streamlit backend. Use browser-based version for full Bluetooth.")
            st.info("⚠️ Bluetooth requires browser Web Bluetooth API.\nStreamlit server can't access device Bluetooth.\nUse the HTML/Flask version for Bluetooth features.")
    with col_disc:
        if st.button("❌ Disconnect", use_container_width=True):
            st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Disconnected (no active connection)")
    
    bt_files = st.file_uploader("Pick Images for Bluetooth", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="bt_img_up", label_visibility="collapsed")
    
    if bt_files:
        st.success(f"📱 {len(bt_files)} BT images selected (ready for browser-based transfer)")
    
    if st.button("📤 Send via Bluetooth", use_container_width=True, type="primary"):
        st.session_state.bt_log.append(f"[{time.strftime('%H:%M:%S')}] Bluetooth send — requires Web Bluetooth API (browser only)")
        st.warning("Bluetooth file transfer requires Web Bluetooth API which is only available in browser context, not in Streamlit server.")
    
    st.markdown('<div class="bt-log">', unsafe_allow_html=True)
    for log_line in st.session_state.bt_log:
        st.caption(log_line)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.caption("**Note:** If your browser doesn't support Web Bluetooth (e.g. iOS Safari, Firefox), the app will automatically fall back to WiFi transfer.")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # PRINT & SEND BUTTON
    # ==========================================
    sel_imgs = [img for img in st.session_state.images if img['selected']]
    
    if sel_imgs or st.session_state.docs:
        st.markdown('<div class="glass-card" style="border: 2px solid #10b981;">', unsafe_allow_html=True)
        
        total_files = len(sel_imgs) + len(st.session_state.docs)
        st.markdown(f'<div class="card-title">🚀 Ready to Print & Send ({total_files} files)</div>', unsafe_allow_html=True)
        
        if sel_imgs:
            st.write(f"**Images:** {len(sel_imgs)} selected")
        if st.session_state.docs:
            st.write(f"**Documents:** {len(st.session_state.docs)}")
        
        if st.button("🚀 PRINT & SEND", use_container_width=True, type="primary"):
            # Try to print images
            if sel_imgs and st.session_state.selected_printer:
                for img in sel_imgs:
                    ok, msg = print_image_win(img['path'], st.session_state.selected_printer)
                    if ok:
                        st.success(f"🖨️ {img['name']} — {msg}")
                    else:
                        st.error(f"❌ {img['name']} — {msg}")
            elif sel_imgs and not st.session_state.selected_printer:
                st.warning("⚠️ No printer selected. Images not printed (but still in queue for PC transfer).")
            
            # Try to send to target PC
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
