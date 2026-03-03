from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = 'calendar_v2.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Workspaces Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        ''')
        
        # Initial Workspace
        cursor.execute("SELECT COUNT(*) FROM workspaces")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO workspaces (id, name) VALUES (?, ?)", ('default', 'メインワークスペース'))

        # Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'member',
                color TEXT,
                avatar_url TEXT,
                workspace_id TEXT DEFAULT 'default',
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
            )
        ''')
        
        # Initial Users
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("INSERT INTO users (id, name, color, role, workspace_id) VALUES (?, ?, ?, ?, ?)", [
                ('user1', 'あなた (User A)', '#0078d4', 'admin', 'default'),
                ('user2', '佐藤さん (User B)', '#107c10', 'member', 'default')
            ])

        # Events Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                user_id TEXT NOT NULL,
                location TEXT,
                status TEXT DEFAULT 'busy',
                is_private INTEGER DEFAULT 0,
                color TEXT,
                workspace_id TEXT DEFAULT 'default',
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
            )
        ''')

        # Tasks Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                user_id TEXT NOT NULL,
                due_date TEXT,
                priority TEXT DEFAULT 'medium',
                assignee_id TEXT,
                color TEXT,
                sort_order INTEGER DEFAULT 0,
                workspace_id TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (assignee_id) REFERENCES users (id),
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
            )
        ''')
        conn.commit()

# Migration function to ensure columns exist
def migrate():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for table in ['users', 'events', 'tasks']:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [c[1] for c in cursor.fetchall()]
            if 'workspace_id' not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id TEXT DEFAULT 'default'")
        conn.commit()

@app.route('/')
def index():
    return render_template('index.html', is_share=False)

@app.route('/share/<user_id>')
def share_view(user_id):
    return render_template('index.html', is_share=True, shared_user_id=user_id)

# User Endpoints
@app.route('/api/users', methods=['GET'])
def get_users():
    workspace_id = request.args.get('workspace_id', 'default')
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE workspace_id = ?", (workspace_id,))
        return jsonify([dict(row) for row in cursor.fetchall()])

@app.route('/api/users', methods=['POST'])
def add_user():
    data = request.json
    workspace_id = data.get('workspace_id', 'default')
    uid = data.get('id', f"user_{os.urandom(4).hex()}")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, name, color, role, workspace_id) VALUES (?, ?, ?, ?, ?)", 
                       (uid, data['name'], data.get('color', '#3b82f6'), 'member', workspace_id))
        conn.commit()
    return jsonify({"status": "success", "id": uid})

@app.route('/api/users/<id>', methods=['DELETE'])
def delete_user(id):
    if id == 'user1':
        return jsonify({"error": "Cannot delete primary user"}), 400
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Cascade delete events and tasks
        cursor.execute("DELETE FROM events WHERE user_id = ?", (id,))
        cursor.execute("DELETE FROM tasks WHERE user_id = ? OR assignee_id = ?", (id, id))
        # Delete user
        cursor.execute("DELETE FROM users WHERE id = ?", (id,))
        conn.commit()
    return jsonify({"status": "success"})

# Event Endpoints
@app.route('/api/events', methods=['GET'])
def get_events():
    workspace_id = request.args.get('workspace_id', 'default')
    user_id = request.args.get('user_id')
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if user_id:
            cursor.execute('SELECT * FROM events WHERE workspace_id = ? AND user_id = ?', (workspace_id, user_id))
        else:
            cursor.execute('SELECT * FROM events WHERE workspace_id = ?', (workspace_id,))
        events = [dict(row) for row in cursor.fetchall()]
    return jsonify(events)

@app.route('/api/events', methods=['POST'])
def add_event():
    data = request.json
    workspace_id = data.get('workspace_id', 'default')
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (title, start_time, end_time, user_id, location, status, is_private, color, workspace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['title'], data['start_time'], data['end_time'], data['user_id'], 
               data.get('location', ''), data.get('status', 'busy'), data.get('is_private', 0), 
               data.get('color', '#3b82f6'), workspace_id))
        conn.commit()
    return jsonify({'status': 'success', 'id': cursor.lastrowid})

@app.route('/api/events/<int:event_id>', methods=['PATCH'])
def update_event(event_id):
    data = request.json
    fields = []
    values = []
    for key in ['title', 'start_time', 'end_time', 'location', 'status', 'is_private', 'color', 'user_id']:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    
    if not fields:
        return jsonify({"error": "No fields to update"}), 400
    
    values.append(event_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    return jsonify({"status": "success"})

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        conn.commit()
    return jsonify({'status': 'success'})

# Task Endpoints
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    workspace_id = request.args.get('workspace_id', 'default')
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE workspace_id = ? ORDER BY sort_order ASC, created_at DESC", (workspace_id,))
        return jsonify([dict(row) for row in cursor.fetchall()])

@app.route('/api/tasks', methods=['POST'])
def add_task():
    data = request.json
    workspace_id = data.get('workspace_id', 'default')
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tasks (content, user_id, due_date, priority, assignee_id, color, workspace_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['content'], data.get('user_id', 'user1'), data.get('due_date'), 
               data.get('priority', 'medium'), data.get('assignee_id'), 
               data.get('color', '#3b82f6'), workspace_id))
        conn.commit()
    return jsonify({"status": "success", "id": cursor.lastrowid})

@app.route('/api/tasks/<int:task_id>', methods=['PATCH'])
def update_task(task_id):
    data = request.json
    fields = []
    values = []
    for key in ['content', 'is_completed', 'due_date', 'priority', 'assignee_id', 'color']:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    
    if not fields:
        return jsonify({"error": "No fields to update"}), 400

    values.append(task_id)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    return jsonify({"status": "success"})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return jsonify({"status": "success"})

@app.route('/api/tasks/reorder', methods=['POST'])
def reorder_tasks():
    data = request.json  # List of {id, sort_order}
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for item in data:
            cursor.execute("UPDATE tasks SET sort_order = ? WHERE id = ?", (item['sort_order'], item['id']))
        conn.commit()
    return jsonify({"status": "success"})

@app.route('/api/ai/analyze', methods=['POST'])
def ai_analyze():
    data = request.json
    events = data.get('events', [])
    tasks = data.get('tasks', [])
    
    summary = "✨ Zenith Planner による分析と提案:\n\n"
    
    # Analyze Schedule
    if not events:
        summary += "📅 【スケジュール】明日は予定がありません。集中作業の大チャンスです！\n"
    else:
        summary += f"📅 【スケジュール】明日は{len(events)}個の予定があります。\n"
        for e in events:
            summary += f"  • {e['title']} ({e['start_time'].split('T')[1][:5]}〜)\n"

    # Analyze Tasks
    pending_tasks = [t for t in tasks if not t['is_completed']]
    high_prio = [t for t in pending_tasks if t['priority'] == 'high']
    
    summary += "\n✅ 【未完了タスク】現在のタスク状況:\n"
    if not pending_tasks:
        summary += "  • 素晴らしい！全てのタスクが完了しています。\n"
    else:
        summary += f"  • 合計{len(pending_tasks)}個のタスクが残っています。\n"
        if high_prio:
            summary += f"  • 🚨 最優先事項: 「{high_prio[0]['content']}」を最優先で片付けましょう。\n"

    # Work Strategy
    summary += "\n💡 【明日の戦略提案】:\n"
    if events:
        # Find biggest gap
        summary += "  • 会議の合間に、1時間程度の集中タイムを1スロット確保できます。\n"
        summary += "  • 移動時間（もしあれば）を利用して、明日のタスクリストを再確認しましょう。\n"
    else:
        summary += "  • 午前中の最も生産性が高い時間に、最重要タスクを完了させることを推奨します。\n"
    
    return jsonify({'summary': summary})

@app.route('/api/workspaces', methods=['GET'])
def get_workspaces():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workspaces")
        return jsonify([dict(row) for row in cursor.fetchall()])

@app.route('/api/workspaces', methods=['POST'])
def add_workspace():
    data = request.json
    ws_id = f"ws_{os.urandom(4).hex()}"
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO workspaces (id, name) VALUES (?, ?)', (ws_id, data['name']))
        # Add basic user to new workspace
        cursor.execute("INSERT INTO users (id, name, color, role, workspace_id) VALUES (?, ?, ?, ?, ?)",
                     ('user1', 'あなた (User A)', '#0078d4', 'admin', ws_id))
        conn.commit()
    return jsonify({"status": "success", "id": ws_id})

# Collaboration & Invitations
@app.route('/api/workspaces/invite', methods=['POST'])
def invite_to_workspace():
    data = request.json
    workspace_id = data.get('workspace_id')
    email = data.get('email')
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Find user by email (from users table)
        cursor.execute("SELECT id FROM users WHERE name = ?", (email,))
        user_row = cursor.fetchone()
        
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = user_row[0]
        
        # Check if already a member
        cursor.execute("SELECT id FROM workspace_members WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id))
        if cursor.fetchone():
            return jsonify({'error': 'Already a member or invited'}), 400
            
        cursor.execute("INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, ?, ?)",
                       (workspace_id, user_id, 'member', 'pending'))
        conn.commit()
    return jsonify({'status': 'invited'})

@app.route('/api/workspaces/pending', methods=['GET'])
def get_pending_invites():
    user_id = request.args.get('user_id')
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT wm.id, w.name, w.id as workspace_id 
            FROM workspace_members wm 
            JOIN workspaces w ON wm.workspace_id = w.id 
            WHERE wm.user_id = ? AND wm.status = 'pending'
        ''', (user_id,))
        rows = cursor.fetchall()
        invites = [{'id': r[0], 'workspace_name': r[1], 'workspace_id': r[2]} for r in rows]
    return jsonify(invites)

@app.route('/api/workspaces/respond', methods=['POST'])
def respond_to_invite():
    data = request.json
    invite_id = data.get('invite_id')
    action = data.get('action') # 'approve' or 'deny'
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if action == 'approve':
            cursor.execute("UPDATE workspace_members SET status = 'approved' WHERE id = ?", (invite_id,))
        else:
            cursor.execute("DELETE FROM workspace_members WHERE id = ?", (invite_id,))
        conn.commit()
    return jsonify({'status': 'done'})

# Filter workspaces to only those the user is a member of
@app.route('/api/workspaces', methods=['GET'])
def get_user_workspaces():
    user_id = request.args.get('user_id')
    if not user_id:
        # Compatibility fallback for initial load before identity
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM workspaces")
            return jsonify([{'id': r[0], 'name': r[1]} for r in cursor.fetchall()])

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT w.id, w.name 
            FROM workspaces w
            JOIN workspace_members wm ON w.id = wm.workspace_id
            WHERE wm.user_id = ? AND wm.status = 'approved'
        ''', (user_id,))
        rows = cursor.fetchall()
        workspaces = [{'id': r[0], 'name': r[1]} for r in rows]
    return jsonify(workspaces)

if __name__ == '__main__':
    init_db()
    migrate()
    app.run(debug=True, port=5000)
