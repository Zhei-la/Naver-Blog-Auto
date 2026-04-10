from flask import request, jsonify, session
from functools import wraps
import time, os, hashlib, re, base64
from collections import defaultdict
from datetime import datetime

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin1234")
SECRET_KEY = os.getenv("SECRET_KEY", "naver-blog-auto-secret-key-2026")

request_counts = defaultdict(list)
RATE_LIMIT = 100
BLOCK_LIST = set()

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def encrypt_pw(pw):
    """비밀번호 암호화 (복호화 가능한 방식 - 로그인에 실제 사용해야 하므로)"""
    key = (SECRET_KEY * 10)[:32].encode()
    pw_bytes = pw.encode()
    encrypted = bytes([pw_bytes[i] ^ key[i % len(key)] for i in range(len(pw_bytes))])
    return base64.b64encode(encrypted).decode()

def decrypt_pw(encrypted_pw):
    """비밀번호 복호화"""
    try:
        key = (SECRET_KEY * 10)[:32].encode()
        encrypted = base64.b64decode(encrypted_pw.encode())
        decrypted = bytes([encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted))])
        return decrypted.decode()
    except:
        return encrypted_pw  # 복호화 실패시 원본 반환 (기존 데이터 호환)

def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = get_client_ip()
        if ip in BLOCK_LIST:
            return jsonify({"error": "Access denied"}), 403
        now = time.time()
        request_counts[ip] = [t for t in request_counts[ip] if now - t < 60]
        if len(request_counts[ip]) >= RATE_LIMIT:
            BLOCK_LIST.add(ip)
            return jsonify({"error": "Too many requests"}), 429
        request_counts[ip].append(now)
        return f(*args, **kwargs)
    return decorated

def sanitize_input(text):
    if not text:
        return text
    sql_patterns = [
        r"(\s|^)(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)(\s|$)",
        r"--", r";--", r"';", r'";'
    ]
    for pattern in sql_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return ""
    text = text.replace("<script", "&lt;script")
    text = text.replace("javascript:", "")
    text = text.replace("onerror=", "")
    text = text.replace("onload=", "")
    return text

def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            from flask import redirect
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def check_password(password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    expected = hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()
    return hashed == expected

def security_report():
    report = {
        "time": datetime.now().isoformat(),
        "blocked_ips": list(BLOCK_LIST),
        "active_sessions": len(request_counts),
        "api_key_valid": bool(os.getenv("OPENAI_API_KEY")),
        "pexels_key_valid": bool(os.getenv("PEXELS_API_KEY")),
        "password_set": DASHBOARD_PASSWORD != "admin1234",
        "secret_key_set": SECRET_KEY != "naver-blog-auto-secret-key-2026",
        "status": "정상"
    }
    issues = []
    if not report["api_key_valid"]:
        issues.append("OpenAI API 키 없음")
    if not report["password_set"]:
        issues.append("⚠️ 기본 비밀번호 사용 중 - 변경 필요!")
    if not report["secret_key_set"]:
        issues.append("⚠️ 기본 SECRET_KEY 사용 중 - 변경 필요!")
    if report["blocked_ips"]:
        issues.append(f"차단된 IP {len(report['blocked_ips'])}개")
    report["issues"] = issues
    report["status"] = "경고" if issues else "정상"
    return report
