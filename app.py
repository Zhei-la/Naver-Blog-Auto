from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime
from writer import generate_post, suggest_keywords
from blogger import publish_post
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
DB = "blog.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT NOT NULL,
        naver_id TEXT NOT NULL,
        naver_pw TEXT NOT NULL,
        topic_type TEXT DEFAULT '기타',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        keyword TEXT,
        title TEXT,
        body TEXT,
        images TEXT DEFAULT '[]',
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
    accounts = conn.execute('SELECT id, client_name, naver_id, topic_type, created_at FROM accounts').fetchall()
    conn.close()
    return jsonify([dict(a) for a in accounts])

@app.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO accounts (client_name, naver_id, naver_pw, topic_type) VALUES (?, ?, ?, ?)',
                 (data['client_name'], data['naver_id'], data['naver_pw'], data.get('topic_type', '기타')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    conn = get_db()
    conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ── 키워드 추천 API ──
@app.route('/api/keywords', methods=['POST'])
def keywords():
    data = request.json
    try:
        kws = suggest_keywords(data['topic'], data.get('topic_type', '기타'), data.get('count', 5))
        return jsonify({"success": True, "keywords": kws})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ── 글 생성 API ──
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    account_id = data['account_id']
    
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    
    try:
        result = generate_post(
            keyword=data['keyword'],
            topic_type=account['topic_type'],
            post_style=data.get('post_style', 'info'),
            custom_prompt=data.get('custom_prompt', ''),
            cta_link=data.get('cta_link', ''),
            cta_text=data.get('cta_text', ''),
            cpa_link=data.get('cpa_link', ''),
            cps_link=data.get('cps_link', '')
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    
    import json
    cursor = conn.execute('''INSERT INTO posts 
        (account_id, keyword, title, body, images, post_style, cta_link, cta_text, cpa_link, cps_link, status, scheduled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (account_id, data['keyword'], result['title'], result['body'],
         json.dumps(result['images']), data.get('post_style', 'info'),
         data.get('cta_link', ''), data.get('cta_text', ''),
         data.get('cpa_link', ''), data.get('cps_link', ''),
         'scheduled' if data.get('scheduled_at') else 'draft',
         data.get('scheduled_at', '')))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "post_id": post_id, 
                    "title": result['title'], "body": result['body'],
                    "images": result['images']})

# ── 발행 API ──
@app.route('/api/publish/<int:post_id>', methods=['POST'])
def publish(post_id):
    conn = get_db()
    post = conn.execute('''SELECT p.*, a.naver_id, a.naver_pw 
                          FROM posts p JOIN accounts a ON p.account_id = a.id 
                          WHERE p.id = ?''', (post_id,)).fetchone()
    if not post:
        return jsonify({"success": False, "message": "포스트 없음"})
    
    result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
    
    if result['success']:
        conn.execute('UPDATE posts SET status = ?, published_url = ?, published_at = ? WHERE id = ?',
                     ('published', result['url'], datetime.now().isoformat(), post_id))
    conn.commit()
    conn.close()
    return jsonify(result)

# ── 포스트 API ──
@app.route('/api/posts', methods=['GET'])
def get_posts():
    account_id = request.args.get('account_id')
    conn = get_db()
    if account_id:
        posts = conn.execute('''SELECT p.*, a.client_name, a.naver_id FROM posts p 
                               JOIN accounts a ON p.account_id = a.id 
                               WHERE p.account_id = ? ORDER BY p.created_at DESC''', (account_id,)).fetchall()
    else:
        posts = conn.execute('''SELECT p.*, a.client_name, a.naver_id FROM posts p 
                               JOIN accounts a ON p.account_id = a.id 
                               ORDER BY p.created_at DESC LIMIT 100''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_post(post_id):
    data = request.json
    conn = get_db()
    conn.execute('UPDATE posts SET title = ?, body = ? WHERE id = ?',
                 (data['title'], data['body'], post_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    conn = get_db()
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ── 예약 발행 스케줄러 ──
def check_scheduled_posts():
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    posts = conn.execute('''SELECT p.*, a.naver_id, a.naver_pw 
                           FROM posts p JOIN accounts a ON p.account_id = a.id
                           WHERE p.status = 'scheduled' AND p.scheduled_at <= ?''', (now,)).fetchall()
    for post in posts:
        result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
        if result['success']:
            conn.execute('UPDATE posts SET status = ?, published_url = ?, published_at = ? WHERE id = ?',
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
    scheduler.start()
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ── 인게이저 API ──
from engager import auto_like, auto_comment, auto_neighbor, auto_engage

@app.route('/api/engage/like', methods=['POST'])
def engage_like():
    data = request.json
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (data['account_id'],)).fetchone()
    conn.close()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    result = auto_like(account['naver_id'], account['naver_pw'],
                       data.get('target', 'neighbor'), data.get('keyword', ''), data.get('count', 10))
    return jsonify(result)

@app.route('/api/engage/comment', methods=['POST'])
def engage_comment():
    data = request.json
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (data['account_id'],)).fetchone()
    conn.close()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    result = auto_comment(account['naver_id'], account['naver_pw'],
                          data.get('target', 'neighbor'), data.get('keyword', ''),
                          data.get('count', 5), data.get('tone', 'friendly'), data.get('custom_comment', ''))
    return jsonify(result)

@app.route('/api/engage/neighbor', methods=['POST'])
def engage_neighbor():
    data = request.json
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (data['account_id'],)).fetchone()
    conn.close()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    result = auto_neighbor(account['naver_id'], account['naver_pw'],
                           data.get('keyword', ''), data.get('count', 10), data.get('message', ''))
    return jsonify(result)

@app.route('/api/engage/engage', methods=['POST'])
def engage_all():
    data = request.json
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (data['account_id'],)).fetchone()
    conn.close()
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    result = auto_engage(account['naver_id'], account['naver_pw'],
                         data.get('target', 'neighbor'), data.get('keyword', ''),
                         data.get('like_count', 10), data.get('comment_count', 5), data.get('tone', 'friendly'))
    return jsonify(result)
