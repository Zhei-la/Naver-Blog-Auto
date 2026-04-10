
@app.before_request
def check_login():
    # 로그인 불필요 경로
    public_paths = ['/login', '/api/login', '/api/logout', '/static']
    if any(request.path.startswith(p) for p in public_paths):
        return
    # 로그인 체크 - 페이지만 (API는 허용)
    if not session.get('logged_in'):
        if not request.path.startswith('/api/'):
            return redirect('/login')

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from security import rate_limit, sanitize_input, add_security_headers, check_password, security_report, SECRET_KEY
import sqlite3, os, json
from datetime import datetime
from writer import generate_post, suggest_keywords, BLOG_TYPES
from blogger import publish_post
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = SECRET_KEY
DB = "/app/data/blog.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT NOT NULL,
        naver_id TEXT NOT NULL,
        naver_pw TEXT NOT NULL,
        blog_type TEXT DEFAULT 'info',
        auto_like INTEGER DEFAULT 0,
        auto_comment INTEGER DEFAULT 0,
        auto_neighbor INTEGER DEFAULT 0,
        auto_like_count INTEGER DEFAULT 10,
        auto_comment_count INTEGER DEFAULT 5,
        auto_neighbor_count INTEGER DEFAULT 5,
        auto_target TEXT DEFAULT 'neighbor',
        auto_keyword TEXT DEFAULT '',
        keywords TEXT DEFAULT '[]',
        grade TEXT DEFAULT 'basic',
        memo TEXT DEFAULT '',
        target_audience TEXT DEFAULT '',
        monthly_goal INTEGER DEFAULT 0,
        contract_start TEXT DEFAULT '',
        special_notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        keyword TEXT,
        title TEXT,
        body TEXT,
        images TEXT DEFAULT '[]',
        blog_type TEXT DEFAULT 'info',
        post_style TEXT DEFAULT 'info',
        cta_link TEXT DEFAULT '',
        cta_text TEXT DEFAULT '',
        cpa_link TEXT DEFAULT '',
        cps_link TEXT DEFAULT '',
        status TEXT DEFAULT 'draft',
        published_url TEXT,
        scheduled_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        published_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS blog_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        title_template TEXT NOT NULL,
        body_template TEXT NOT NULL,
        images TEXT DEFAULT '[]',
        variables TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS auto_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        keywords TEXT DEFAULT '[]',
        grade TEXT DEFAULT 'basic',
        post_times TEXT DEFAULT '[]',
        post_style TEXT DEFAULT 'info',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── 계정 API ──
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    conn = get_db()
    rows = conn.execute('SELECT * FROM accounts').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/accounts', methods=['POST'])
def add_account():
    d = request.json
    conn = get_db()
    import json as _json
    conn.execute('''INSERT INTO accounts 
        (client_name, naver_id, naver_pw, blog_type,
         auto_like, auto_comment, auto_neighbor,
         auto_like_count, auto_comment_count, auto_neighbor_count,
         auto_target, auto_keyword, keywords)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d['client_name'], d['naver_id'], d['naver_pw'], d.get('blog_type','info'),
         d.get('auto_like',0), d.get('auto_comment',0), d.get('auto_neighbor',0),
         d.get('auto_like_count',10), d.get('auto_comment_count',5), d.get('auto_neighbor_count',5),
         d.get('auto_target','neighbor'), d.get('auto_keyword',''),
         _json.dumps(d.get('keywords',[])),
         d.get('memo',''), d.get('target_audience',''),
         d.get('monthly_goal',0), d.get('contract_start',''), d.get('special_notes','')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/accounts/<int:aid>', methods=['PUT'])
def update_account(aid):
    d = request.json
    conn = get_db()
    import json as _json
    conn.execute('''UPDATE accounts SET
        client_name=?, naver_id=?, blog_type=?,
        auto_like=?, auto_comment=?, auto_neighbor=?,
        auto_like_count=?, auto_comment_count=?, auto_neighbor_count=?,
        auto_target=?, auto_keyword=?, keywords=?, grade=? WHERE id=?''',
        (d.get('client_name',''), d.get('naver_id',''), d.get('blog_type','info'),
         d.get('auto_like',0), d.get('auto_comment',0), d.get('auto_neighbor',0),
         d.get('auto_like_count',10), d.get('auto_comment_count',5), d.get('auto_neighbor_count',5),
         d.get('auto_target','neighbor'), d.get('auto_keyword',''),
         _json.dumps(d.get('keywords',[])), d.get('grade','basic'), aid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/accounts/<int:aid>', methods=['DELETE'])
def delete_account(aid):
    conn = get_db()
    conn.execute('DELETE FROM accounts WHERE id=?', (aid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/blog_types', methods=['GET'])
def get_blog_types():
    return jsonify([{"key": k, "name": v["name"]} for k, v in BLOG_TYPES.items()])

# ── 키워드 추천 ──
@app.route('/api/keywords', methods=['POST'])
def keywords():
    d = request.json
    try:
        kws = suggest_keywords(d['topic'], d.get('blog_type','info'), d.get('count',6))
        return jsonify({"success": True, "keywords": kws})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ── 글 생성 ──
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id=?', (d['account_id'],)).fetchone()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    try:
        result = generate_post(
            keyword=d['keyword'],
            blog_type=account['blog_type'],
            post_style=d.get('post_style','info'),
            custom_prompt=d.get('custom_prompt',''),
            cta_link=d.get('cta_link',''),
            cta_text=d.get('cta_text',''),
            cpa_link=d.get('cpa_link',''),
            cps_link=d.get('cps_link','')
        )
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": str(e)})

    cursor = conn.execute('''INSERT INTO posts
        (account_id, keyword, title, body, images, blog_type, post_style,
         cta_link, cta_text, cpa_link, cps_link, status, scheduled_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d['account_id'], d['keyword'], result['title'], result['body'],
         json.dumps(result['images']), account['blog_type'], d.get('post_style','info'),
         d.get('cta_link',''), d.get('cta_text',''),
         d.get('cpa_link',''), d.get('cps_link',''),
         'scheduled' if d.get('scheduled_at') else 'draft',
         d.get('scheduled_at','')))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"success": True, "post_id": post_id,
                    "title": result['title'], "body": result['body'],
                    "images": result['images']})

# ── 대량 발행 ──
@app.route('/api/bulk_generate', methods=['POST'])
def bulk_generate():
    d = request.json
    account_ids = d.get('account_ids', [])
    keyword = d.get('keyword', '')
    results = []
    conn = get_db()
    for aid in account_ids:
        account = conn.execute('SELECT * FROM accounts WHERE id=?', (aid,)).fetchone()
        if not account:
            continue
        try:
            result = generate_post(keyword=keyword, blog_type=account['blog_type'],
                                   post_style=d.get('post_style','info'))
            cursor = conn.execute('''INSERT INTO posts
                (account_id, keyword, title, body, images, blog_type, post_style, status)
                VALUES (?,?,?,?,?,?,?,?)''',
                (aid, keyword, result['title'], result['body'],
                 json.dumps(result['images']), account['blog_type'],
                 d.get('post_style','info'), 'draft'))
            results.append({"account": account['client_name'], "post_id": cursor.lastrowid,
                           "title": result['title'], "success": True})
        except Exception as e:
            results.append({"account": account['client_name'], "success": False, "message": str(e)})
    conn.commit()
    conn.close()
    return jsonify({"success": True, "results": results})

@app.route('/api/bulk_publish', methods=['POST'])
def bulk_publish():
    d = request.json
    post_ids = d.get('post_ids', [])
    results = []
    conn = get_db()
    for pid in post_ids:
        post = conn.execute('''SELECT p.*, a.naver_id, a.naver_pw
                               FROM posts p JOIN accounts a ON p.account_id=a.id
                               WHERE p.id=?''', (pid,)).fetchone()
        if not post:
            continue
        result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
        if result['success']:
            conn.execute('UPDATE posts SET status=?, published_url=?, published_at=? WHERE id=?',
                        ('published', result['url'], datetime.now().isoformat(), pid))
        results.append({"post_id": pid, **result})
    conn.commit()
    conn.close()
    return jsonify({"success": True, "results": results})

# ── 발행 ──
@app.route('/api/publish/<int:pid>', methods=['POST'])
def publish(pid):
    conn = get_db()
    post = conn.execute('''SELECT p.*, a.naver_id, a.naver_pw
                           FROM posts p JOIN accounts a ON p.account_id=a.id
                           WHERE p.id=?''', (pid,)).fetchone()
    if not post:
        return jsonify({"success": False, "message": "포스트 없음"})
    result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
    if result['success']:
        conn.execute('UPDATE posts SET status=?, published_url=?, published_at=? WHERE id=?',
                     ('published', result['url'], datetime.now().isoformat(), pid))
    conn.commit()
    conn.close()
    return jsonify(result)

# ── 포스트 ──
@app.route('/api/posts', methods=['GET'])
def get_posts():
    aid = request.args.get('account_id')
    conn = get_db()
    if aid:
        posts = conn.execute('''SELECT p.*, a.client_name FROM posts p
                               JOIN accounts a ON p.account_id=a.id
                               WHERE p.account_id=? ORDER BY p.created_at DESC''', (aid,)).fetchall()
    else:
        posts = conn.execute('''SELECT p.*, a.client_name FROM posts p
                               JOIN accounts a ON p.account_id=a.id
                               ORDER BY p.created_at DESC LIMIT 100''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])

@app.route('/api/posts/<int:pid>', methods=['PUT'])
def update_post(pid):
    d = request.json
    conn = get_db()
    conn.execute('UPDATE posts SET title=?, body=? WHERE id=?', (d['title'], d['body'], pid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/posts/<int:pid>', methods=['DELETE'])
def delete_post(pid):
    conn = get_db()
    conn.execute('DELETE FROM posts WHERE id=?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ── 인게이저 ──
from engager import auto_like, auto_comment, auto_neighbor, auto_engage

@app.route('/api/engage/like', methods=['POST'])
def engage_like():
    d = request.json
    conn = get_db()
    acc = conn.execute('SELECT * FROM accounts WHERE id=?', (d['account_id'],)).fetchone()
    conn.close()
    if not acc: return jsonify({"success": False, "message": "계정 없음"})
    return jsonify(auto_like(acc['naver_id'], acc['naver_pw'],
                             d.get('target','neighbor'), d.get('keyword',''), d.get('count',10)))

@app.route('/api/engage/comment', methods=['POST'])
def engage_comment():
    d = request.json
    conn = get_db()
    acc = conn.execute('SELECT * FROM accounts WHERE id=?', (d['account_id'],)).fetchone()
    conn.close()
    if not acc: return jsonify({"success": False, "message": "계정 없음"})
    return jsonify(auto_comment(acc['naver_id'], acc['naver_pw'],
                                d.get('target','neighbor'), d.get('keyword',''),
                                d.get('count',5), d.get('tone','friendly'), d.get('custom_comment','')))

@app.route('/api/engage/neighbor', methods=['POST'])
def engage_neighbor():
    d = request.json
    conn = get_db()
    acc = conn.execute('SELECT * FROM accounts WHERE id=?', (d['account_id'],)).fetchone()
    conn.close()
    if not acc: return jsonify({"success": False, "message": "계정 없음"})
    return jsonify(auto_neighbor(acc['naver_id'], acc['naver_pw'],
                                 d.get('keyword',''), d.get('count',10), d.get('message','')))

@app.route('/api/engage/engage', methods=['POST'])
def engage_all():
    d = request.json
    conn = get_db()
    acc = conn.execute('SELECT * FROM accounts WHERE id=?', (d['account_id'],)).fetchone()
    conn.close()
    if not acc: return jsonify({"success": False, "message": "계정 없음"})
    return jsonify(auto_engage(acc['naver_id'], acc['naver_pw'],
                               d.get('target','neighbor'), d.get('keyword',''),
                               d.get('like_count',10), d.get('comment_count',5), d.get('tone','friendly')))

# ── 자동화 스케줄러 ──
def run_auto_posts():
    """자동 글 발행 - 매분 체크해서 시간 맞으면 발행"""
    import json as _json
    now_time = datetime.now().strftime("%H:%M")
    conn = get_db()
    schedules = conn.execute('''SELECT s.*, a.naver_id, a.naver_pw, a.blog_type 
                               FROM auto_schedule s JOIN accounts a ON s.account_id=a.id
                               WHERE s.is_active=1''').fetchall()
    conn.close()
    for s in schedules:
        times = _json.loads(s["post_times"] or "[]")
        if now_time not in times:
            continue
        keywords = _json.loads(s["keywords"] or "[]")
        if not keywords:
            continue
        import random as _random
        keyword = _random.choice(keywords)
        try:
            result = generate_post(keyword=keyword, blog_type=s["blog_type"], post_style=s["post_style"])
            conn2 = get_db()
            cursor = conn2.execute('''INSERT INTO posts (account_id, keyword, title, body, images, blog_type, post_style, status)
                               VALUES (?,?,?,?,?,?,?,?)''',
                (s["account_id"], keyword, result["title"], result["body"],
                 _json.dumps(result["images"]), s["blog_type"], s["post_style"], "draft"))
            post_id = cursor.lastrowid
            conn2.commit()
            conn2.close()
            publish_post(s["naver_id"], s["naver_pw"], result["title"], result["body"])
        except Exception as e:
            print(f"자동 발행 오류: {e}")

def run_auto_tasks():
    conn = get_db()
    accounts = conn.execute('SELECT * FROM accounts').fetchall()
    conn.close()
    for acc in accounts:
        if acc['auto_like']:
            auto_like(acc['naver_id'], acc['naver_pw'],
                      acc['auto_target'], acc['auto_keyword'], acc['auto_like_count'])
        if acc['auto_comment']:
            auto_comment(acc['naver_id'], acc['naver_pw'],
                         acc['auto_target'], acc['auto_keyword'], acc['auto_comment_count'])
        if acc['auto_neighbor']:
            auto_neighbor(acc['naver_id'], acc['naver_pw'],
                          acc['auto_keyword'], acc['auto_neighbor_count'])

def check_scheduled_posts():
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    posts = conn.execute('''SELECT p.*, a.naver_id, a.naver_pw
                            FROM posts p JOIN accounts a ON p.account_id=a.id
                            WHERE p.status='scheduled' AND p.scheduled_at<=?''', (now,)).fetchall()
    for post in posts:
        result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
        if result['success']:
            conn.execute('UPDATE posts SET status=?, published_url=?, published_at=? WHERE id=?',
                        ('published', result['url'], datetime.now().isoformat(), post['id']))
    conn.commit()
    conn.close()


@app.route('/login', methods=['GET'])
def login_page():
    if session.get('logged_in'):
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def do_login():
    pw = request.json.get('password','')
    DASH_PW = os.getenv('DASHBOARD_PASSWORD','admin1234')
    if pw == DASH_PW:
        session['logged_in'] = True
        session.permanent = True
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/logout', methods=['POST'])
def do_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/')
def index():
    return render_template('index.html')


# ── 인사이트 API ──
from insight import get_blog_insight

@app.route('/api/insight/<int:account_id>', methods=['GET'])
def get_insight(account_id):
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()
    conn.close()
    if not account:
        return jsonify({'success': False, 'message': '계정 없음'})
    date = request.args.get('date', None)
    result = get_blog_insight(account['naver_id'], account['naver_pw'], date)
    return jsonify(result)
if __name__ == '__main__':
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_scheduled_posts, 'interval', minutes=1)
    scheduler.add_job(run_auto_posts, 'interval', minutes=1)
    scheduler.add_job(run_auto_tasks, 'cron', hour=9, minute=0)  # 매일 오전 9시
    scheduler.start()
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ── 자동 글 발행 스케줄 API ──
@app.route('/api/schedule', methods=['GET'])
def get_schedules():
    aid = request.args.get('account_id')
    conn = get_db()
    if aid:
        rows = conn.execute('SELECT * FROM auto_schedule WHERE account_id=?', (aid,)).fetchall()
    else:
        rows = conn.execute('SELECT s.*, a.client_name FROM auto_schedule s JOIN accounts a ON s.account_id=a.id').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/schedule', methods=['POST'])
def add_schedule():
    d = request.json
    conn = get_db()
    conn.execute('''INSERT INTO auto_schedule (account_id, keywords, post_times, post_style, is_active)
                    VALUES (?,?,?,?,?)''',
        (d['account_id'], json.dumps(d.get('keywords',[])),
         json.dumps(d.get('post_times',[])), d.get('post_style','info'), 1))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/schedule/<int:sid>', methods=['PUT'])
def update_schedule(sid):
    d = request.json
    conn = get_db()
    conn.execute('''UPDATE auto_schedule SET keywords=?, post_times=?, post_style=?, is_active=? WHERE id=?''',
        (json.dumps(d.get('keywords',[])), json.dumps(d.get('post_times',[])),
         d.get('post_style','info'), d.get('is_active',1), sid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/schedule/<int:sid>', methods=['DELETE'])
def delete_schedule(sid):
    conn = get_db()
    conn.execute('DELETE FROM auto_schedule WHERE id=?', (sid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ── 템플릿 API ──
from template_manager import upload_image, delete_image, render_template

@app.route('/api/templates', methods=['GET'])
def get_templates():
    conn = get_db()
    templates = conn.execute('SELECT * FROM blog_templates ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(t) for t in templates])

@app.route('/api/templates', methods=['POST'])
def add_template():
    d = request.json
    conn = get_db()
    conn.execute('''INSERT INTO blog_templates (name, title_template, body_template, images, variables)
                    VALUES (?,?,?,?,?)''',
        (d['name'], d['title_template'], d['body_template'],
         json.dumps(d.get('images',[])), json.dumps(d.get('variables',[]))))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/templates/<int:tid>', methods=['PUT'])
def update_template(tid):
    d = request.json
    conn = get_db()
    conn.execute('''UPDATE blog_templates SET name=?, title_template=?, body_template=?, images=?, variables=? WHERE id=?''',
        (d['name'], d['title_template'], d['body_template'],
         json.dumps(d.get('images',[])), json.dumps(d.get('variables',[])), tid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/templates/<int:tid>', methods=['DELETE'])
def delete_template(tid):
    conn = get_db()
    conn.execute('DELETE FROM blog_templates WHERE id=?', (tid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/templates/upload-image', methods=['POST'])
def upload_template_image():
    if 'image' not in request.files:
        return jsonify({"success": False, "message": "이미지 없음"})
    file = request.files['image']
    import base64
    file_data = "data:" + file.content_type + ";base64," + base64.b64encode(file.read()).decode()
    result = upload_image(file_data, file.filename)
    return jsonify(result)

@app.route('/api/templates/<int:tid>/publish', methods=['POST'])
def publish_from_template(tid):
    d = request.json
    account_ids = d.get('account_ids', [])
    variables_list = d.get('variables_list', [{}])  # 계정별 변수값

    conn = get_db()
    template = conn.execute('SELECT * FROM blog_templates WHERE id=?', (tid,)).fetchone()
    if not template:
        return jsonify({"success": False, "message": "템플릿 없음"})

    results = []
    for i, aid in enumerate(account_ids):
        account = conn.execute('SELECT * FROM accounts WHERE id=?', (aid,)).fetchone()
        if not account:
            continue
        
        variables = variables_list[i] if i < len(variables_list) else {}
        title = render_template(template['title_template'], variables)
        body = render_template(template['body_template'], variables)
        images = json.loads(template['images'] or '[]')

        cursor = conn.execute('''INSERT INTO posts
            (account_id, keyword, title, body, images, blog_type, status)
            VALUES (?,?,?,?,?,?,?)''',
            (aid, variables.get('키워드', ''), title, body,
             template['images'], account['blog_type'], 'draft'))
        post_id = cursor.lastrowid

        result = publish_post(account['naver_id'], account['naver_pw'], title, body)
        if result['success']:
            conn.execute('UPDATE posts SET status=?, published_url=?, published_at=? WHERE id=?',
                        ('published', result['url'], datetime.now().isoformat(), post_id))
        results.append({"account": account['client_name'], "success": result['success'], "message": result.get('message','')})

    conn.commit()
    conn.close()
    return jsonify({"success": True, "results": results})

# ── 보안 관리 페이지 ──
import hashlib, secrets
from datetime import datetime as dt

# 보안 데이터 저장 (메모리 + DB 혼용)
security_blocked = {}  # ip -> {reason, time}
security_logs = []     # [{time, ip, type, detail}]
admin_tokens = set()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", os.getenv("DASHBOARD_PASSWORD", "admin1234"))

def get_security_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS blocked_ips (
        ip TEXT PRIMARY KEY,
        reason TEXT DEFAULT '수동 차단',
        blocked_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS security_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        type TEXT,
        detail TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    return conn

@app.route('/security')
def security_page():
    return render_template('security_admin.html')

@app.route('/api/security/auth', methods=['POST'])
def security_auth():
    d = request.json
    pw = d.get('password', '')
    if hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest():
        token = secrets.token_hex(32)
        admin_tokens.add(token)
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False})

def check_admin(req):
    return req.headers.get('X-Admin-Token') in admin_tokens

@app.route('/api/security/admin', methods=['GET'])
def security_admin():
    if not check_admin(request):
        return jsonify({"success": False}), 401
    conn = get_security_db()
    blocked = conn.execute('SELECT * FROM blocked_ips ORDER BY blocked_at DESC').fetchall()
    logs = conn.execute('SELECT * FROM security_logs ORDER BY created_at DESC LIMIT 100').fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "blocked_count": len(blocked),
        "blocked_ips": [{"ip": b["ip"], "reason": b["reason"], "time": b["blocked_at"]} for b in blocked],
        "security_logs": [{"ip": l["ip"], "type": l["type"], "detail": l["detail"], "time": l["created_at"]} for l in logs],
        "total_requests": len(logs)
    })

@app.route('/api/security/block', methods=['POST'])
def block_ip():
    if not check_admin(request):
        return jsonify({"success": False}), 401
    d = request.json
    ip = d.get('ip', '').strip()
    reason = d.get('reason', '수동 차단')
    if not ip:
        return jsonify({"success": False})
    conn = get_security_db()
    conn.execute('INSERT OR REPLACE INTO blocked_ips (ip, reason, blocked_at) VALUES (?,?,?)',
                 (ip, reason, dt.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.execute('INSERT INTO security_logs (ip, type, detail) VALUES (?,?,?)',
                 (ip, '수동 차단', f'관리자가 {ip} 차단'))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/security/unblock', methods=['POST'])
def unblock_ip():
    if not check_admin(request):
        return jsonify({"success": False}), 401
    ip = request.json.get('ip', '').strip()
    conn = get_security_db()
    conn.execute('DELETE FROM blocked_ips WHERE ip=?', (ip,))
    conn.execute('INSERT INTO security_logs (ip, type, detail) VALUES (?,?,?)',
                 (ip, '차단 해제', f'관리자가 {ip} 차단 해제'))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
