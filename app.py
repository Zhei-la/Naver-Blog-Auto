from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import os
from datetime import datetime
from writer import generate_post
from blogger import publish_post
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
DB = "blog.db"

# DB 초기화
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
        status TEXT DEFAULT 'draft',
        published_url TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        published_at TEXT
    )''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# 라우트
@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    account_id = data['account_id']
    keyword = data['keyword']
    custom_prompt = data.get('custom_prompt', '')
    
    # 계정 정보 가져오기
    conn = get_db()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
    
    if not account:
        return jsonify({"success": False, "message": "계정 없음"})
    
    # AI 글 생성
    result = generate_post(keyword, account['topic_type'], custom_prompt)
    
    # DB 저장 (draft)
    cursor = conn.execute('INSERT INTO posts (account_id, keyword, title, body, status) VALUES (?, ?, ?, ?, ?)',
                 (account_id, keyword, result['title'], result['body'], 'draft'))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "post_id": post_id, "title": result['title'], "body": result['body']})

@app.route('/api/publish/<int:post_id>', methods=['POST'])
def publish(post_id):
    conn = get_db()
    post = conn.execute('SELECT p.*, a.naver_id, a.naver_pw FROM posts p JOIN accounts a ON p.account_id = a.id WHERE p.id = ?', (post_id,)).fetchone()
    
    if not post:
        return jsonify({"success": False, "message": "포스트 없음"})
    
    # 발행
    result = publish_post(post['naver_id'], post['naver_pw'], post['title'], post['body'])
    
    if result['success']:
        conn.execute('UPDATE posts SET status = ?, published_url = ?, published_at = ? WHERE id = ?',
                     ('published', result['url'], datetime.now().isoformat(), post_id))
    conn.commit()
    conn.close()
    
    return jsonify(result)

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
                               ORDER BY p.created_at DESC LIMIT 50''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in posts])

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    conn = get_db()
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_post(post_id):
    data = request.json
    conn = get_db()
    conn.execute('UPDATE posts SET title = ?, body = ? WHERE id = ?',
                 (data['title'], data['body'], post_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
