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
    c.execute('''CREATE TABLE IF NOT EXISTS auto_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        keywords TEXT DEFAULT '[]',
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
    conn.execute('''INSERT INTO accounts 
        (client_name, naver_id, naver_pw, blog_type,
         auto_like, auto_comment, auto_neighbor,
         auto_like_count, auto_comment_count, auto_neighbor_count,
         auto_target, auto_keyword)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d['client_name'], d['naver_id'], d['naver_pw'], d.get('blog_type','info'),
         d.get('auto_like',0), d.get('auto_comment',0), d.get('auto_neighbor',0),
         d.get('auto_like_count',10), d.get('auto_comment_count',5), d.get('auto_neighbor_count',5),
         d.get('auto_target','neighbor'), d.get('auto_keyword','')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/accounts/<int:aid>', methods=['PUT'])
def update_account(aid):
    d = request.json
    conn = get_db()
    conn.execute('''UPDATE accounts SET
        auto_like=?, auto_comment=?, auto_neighbor=?,
        auto_like_count=?, auto_comment_count=?, auto_neighbor_count=?,
        auto_target=?, auto_keyword=? WHERE id=?''',
        (d.get('auto_like',0), d.get('auto_comment',0), d.get('auto_neighbor',0),
         d.get('auto_like_count',10), d.get('auto_comment_count',5), d.get('auto_neighbor_count',5),
         d.get('auto_target','neighbor'), d.get('auto_keyword',''), aid))
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

@app.route('/')
def index():
    return render_template('index.html')

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
