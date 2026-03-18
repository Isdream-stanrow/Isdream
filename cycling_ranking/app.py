from flask import Flask, render_template, request, jsonify
import sqlite3
import os

app = Flask(__name__)
DATABASE = 'database.db'

# 初始化数据库
def init_db():
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE rides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                distance REAL NOT NULL,  -- 单位：公里
                time REAL NOT NULL       -- 单位：分钟
            )
        ''')
        conn.commit()
        conn.close()

# 获取排行榜数据（按距离降序）
def get_ranking():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, distance, time FROM rides ORDER BY distance DESC')
    results = cursor.fetchall()
    conn.close()
    return results

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 处理上传数据
        name = request.form['name']
        distance = float(request.form['distance'])
        time = float(request.form['time'])
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO rides (name, distance, time) VALUES (?, ?, ?)',
                       (name, distance, time))
        conn.commit()
        conn.close()
    
    # 获取当前排名
    ranking = get_ranking()
    return render_template('index.html', ranking=ranking)

@app.route('/get_ranking')
def get_ranking_json():
    sort_by = request.args.get('sort_by', 'distance')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    if sort_by == 'distance':
        cursor.execute('''
            SELECT name, distance, time 
            FROM rides 
            ORDER BY distance DESC
        ''')
    elif sort_by == 'speed':
        # 计算均速（公里/分钟）: distance / time
        cursor.execute('''
            SELECT name, distance, time, (distance / time) AS speed 
            FROM rides 
            WHERE time > 0  -- 避免除零错误
            ORDER BY speed DESC
        ''')
    else:
        cursor.execute('SELECT name, distance, time FROM rides ORDER BY distance DESC')
    results = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        'name': row[0],
        'distance': row[1],
        'time': row[2],
        'speed': row[3] if sort_by == 'speed' else None
    } for row in results])

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
