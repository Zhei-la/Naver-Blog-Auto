from flask import request, jsonify, session
from functools import wraps
import time
import os
import hashlib
import re
from collections import defaultdict
from datetime import datetime

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin1234")
SECRET_KEY = os.getenv("SECRET_KEY", "naver-blog-auto-secret-key-2026")

# Rate limiting
request_counts = defaultdict(list)
RATE_LIMIT = 100  # 1분에 최대 100개 요청
BLOCK_LIST = set()

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def rate_limit(f):
    """Rate limiting 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = get_client_ip()
        
        # 차단된 IP 체크
        if ip in BLOCK_LIST:
            return jsonify({"error": "Access denied"}), 403
        
        # Rate limit 체크
        now = time.time()
        request_counts[ip] = [t for t in request_counts[ip] if now - t < 60]
        
        if len(request_counts[ip]) >= RATE_LIMIT:
            BLOCK_LIST.add(ip)
            return jsonify({"error": "Too many requests"}), 429
        
        request_counts[ip].append(now)
        return f(*args, **kwargs)
    return decorated

def sanitize_input(text):
    """SQL injection, XSS 방어"""
    if not text:
        return text
    # SQL injection 패턴 제거
    sql_patterns = [
        r"(\s|^)(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)(\s|$)",
        r"--", r";--", r"';", r'";'
    ]
    for pattern in sql_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return ""
    
    # XSS 방어
    text = text.replace("<script", "&lt;script")
    text = text.replace("javascript:", "")
    text = text.replace("onerror=", "")
    text = text.replace("onload=", "")
    return text

def add_security_headers(response):
    """보안 헤더 추가"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response

def login_required(f):
    """로그인 필요 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            from flask import redirect, url_for
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def check_password(password):
    """비밀번호 확인"""
    hashed = hashlib.sha256(password.encode()).hexdigest()
    expected = hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()
    return hashed == expected

def security_report():
    """보안 점검 보고서 생성"""
    report = {
        "time": datetime.now().isoformat(),
        "blocked_ips": list(BLOCK_LIST),
        "active_sessions": len(request_counts),
        "api_key_valid": bool(os.getenv("OPENAI_API_KEY")),
        "pexels_key_valid": bool(os.getenv("PEXELS_API_KEY")),
        "password_set": DASHBOARD_PASSWORD != "admin1234",
        "status": "정상"
    }
    
    issues = []
    if not report["api_key_valid"]:
        issues.append("OpenAI API 키 없음")
    if not report["password_set"]:
        issues.append("기본 비밀번호 사용 중 - 변경 권장")
    if report["blocked_ips"]:
        issues.append(f"차단된 IP {len(report['blocked_ips'])}개")
    
    report["issues"] = issues
    report["status"] = "경고" if issues else "정상"
    return report
