from flask import Flask, render_template, request, jsonify, session, redirect, send_file
from datetime import datetime
from collections import defaultdict
import time as time_module
import sqlite3
import hashlib
import os
import secrets 
import random
import html
import re
import shutil
import tempfile

ip_submit_count = defaultdict(list)
IP_LIMIT = 5  # 每个IP每分钟最多5次提交
IP_BLOCK_TIME = 300  # 违规IP封锁5分钟
blocked_ips = {}
attack_log = []


ADMIN_PASSWORD = "ZUISHUAI6"
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
DATABASE = 'database.db'

def sanitize_input(input_string, max_length=50):
    """
    清理用户输入,防止XSS攻击
    - 移除HTML标签
    - 转义特殊字符
    - 限制长度
    """
    if not input_string:
        return ""
    
    # 限制长度
    if len(input_string) > max_length:
        input_string = input_string[:max_length]

    
    
    # 移除所有HTML标签（允许基本标点）
    # 只允许中文、英文、数字、空格和常见标点
    cleaned = re.sub(r'[<>\"\'&;]', '', input_string)
    
    # 额外的安全：移除可能危险的字符
    dangerous_patterns = [
        r'javascript:', r'onclick=', r'onload=', r'onerror=',
        r'onmouseover=', r'alert\(', r'prompt\(', r'confirm\(',
        r'eval\(', r'<script', r'</script>', r'<iframe',
        r'<img', r'<svg', r'<body', r'<meta'
    ]
    
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    if input_string != cleaned:
        log_attack("XSS尝试", f"清理前: {input_string[:50]}...")
    
    return cleaned.strip()

def generate_math_captcha():
    """生成算术验证码"""
    ops = ['+', '-', '*']
    a = random.randint(1, 99)
    b = random.randint(1, 9)
    op = random.choice(ops)
    
    if op == '+':
        answer = a + b
    elif op == '-':
        answer = a - b
    else:
        answer = a * b
    
    question = f"{a} {op} {b} = ?"
    return question, str(answer)

def check_ip_limit(ip):
    """检查IP是否超出限制"""
    now = time_module.time()
    
    # 检查是否在封锁名单
    if ip in blocked_ips:
        if now - blocked_ips[ip] < IP_BLOCK_TIME:
            return False, f"IP已被临时封锁,请{int((IP_BLOCK_TIME - (now - blocked_ips[ip]))/60)}分钟后再试"
        else:
            del blocked_ips[ip]
    
    # 清理1分钟前的记录
    if ip in ip_submit_count:
        ip_submit_count[ip] = [t for t in ip_submit_count[ip] if now - t < 60]
    
    # 检查频率
    if ip in ip_submit_count and len(ip_submit_count[ip]) >= IP_LIMIT:
        blocked_ips[ip] = now
        return False, "提交频率过高,IP已被临时封锁"
    
    return True, ""

# 初始化数据库
def init_db():
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                distance REAL NOT NULL, 
                time REAL NOT NULL,      
                date DATE NOT NULL DEFAULT (date('now')),
                is_anonymous BOOLEAN DEFAULT 0, 
                anonymous_id TEXT      
            )
        ''')
        conn.commit()
        conn.close()

with app.app_context():
    init_db()
# 获取排行榜数据（按距离降序）
def get_ranking():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT name, distance, time, date FROM rides ORDER BY distance DESC')
    results = cursor.fetchall()
    conn.close()
    return results
def log_attack(ip, reason, details=""):
    """记录攻击日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "ip": ip,
        "reason": reason,
        "details": details
    }
    attack_log.append(log_entry)
    
    # 只保留最近1000条日志
    if len(attack_log) > 1000:
        attack_log.pop(0)
    
    print(f"[攻击日志] {timestamp} - {ip} - {reason}")


# 添加攻击日志查看路由
@app.route('/admin/attack_logs')
def view_attack_logs():
    """查看攻击日志"""
    if not session.get('is_admin'):
        return redirect('/admin/login')
    
    return render_template('attack_logs.html', logs=attack_log)

@app.route('/refresh_captcha')
def refresh_captcha():
    """刷新验证码"""
    question, answer = generate_math_captcha()
    session['captcha_answer'] = answer
    return jsonify({
        "success": True,
        "question": question
    })

@app.route('/admin/batch_delete', methods=['POST'])
def batch_delete():
    """批量删除记录"""
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "未登录"}), 403
    
    data = request.json
    if not data or 'ids' not in data:
        return jsonify({"success": False, "error": "未提供删除ID列表"}), 400
    
    ids = data['ids']
    if not isinstance(ids, list) or len(ids) == 0:
        return jsonify({"success": False, "error": "ID列表格式错误"}), 400
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    deleted_count = 0
    
    try:
        # 使用IN子句批量删除
        placeholders = ','.join(['?'] * len(ids))
        cursor.execute(f'DELETE FROM rides WHERE id IN ({placeholders})', ids)
        conn.commit()
        deleted_count = cursor.rowcount
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()
    
    return jsonify({
        "success": True, 
        "message": f"成功删除 {deleted_count} 条记录",
        "deleted_count": deleted_count
    })

@app.route('/news')
def news_page():
    """新闻公告页面"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 1. 获取本月骑行冠军
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute('''
        SELECT name, SUM(distance) as total_distance
        FROM rides 
        WHERE strftime('%Y-%m', date) = ? AND time > 0
        GROUP BY name 
        ORDER BY total_distance DESC
        LIMIT 3
    ''', (current_month,))
    monthly_champs = cursor.fetchall()
    
    # 2. 获取统计数据
    cursor.execute('SELECT COUNT(DISTINCT name) FROM rides')
    total_riders = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(distance) FROM rides WHERE time > 0')
    total_distance = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM rides WHERE time > 0')
    total_rides = cursor.fetchone()[0]
    
    conn.close()
    current_month_display = datetime.now().strftime('%Y年%m月')
    return render_template('news.html',
                          monthly_champs=monthly_champs,
                          total_riders=total_riders,
                          total_distance=total_distance,
                          total_rides=total_rides,
                          current_month_display=current_month_display
                          )


@app.route('/admin/download_db')
def download_database():
    """下载数据库文件（仅管理员可访问）"""
    # 验证管理员权限
    if not session.get('is_admin'):
        return "未授权访问", 403
    
     # 额外的安全验证：检查Referer，确保请求来自管理页面
    referer = request.headers.get('Referer')
    if referer and '/admin' not in referer:
        # 可以记录这个可疑请求
        print(f"可疑的数据库下载请求,Referer: {referer}")
        # 不直接拒绝，但记录日志
    
    # 确保数据库文件存在
    if not os.path.exists(DATABASE):
        return "数据库文件不存在", 404
    
    try:
        # 可选：在下载前创建临时备份（避免下载过程中数据被修改）
        import shutil
        import tempfile
        
        # 创建临时备份文件
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f'cycling_club_backup_{timestamp}.db'
        backup_path = os.path.join(temp_dir, backup_filename)
        
        # 复制数据库文件到临时位置
        shutil.copy2(DATABASE, backup_path)
        
        # 发送备份文件
        # 发送数据库文件
        return send_file(
            backup_path,
            as_attachment=True,  # 作为附件下载
            download_name=backup_filename,
            mimetype='application/x-sqlite3',
            conditional=True
        )
    except Exception as e:
        return f"下载失败: {str(e)}", 500

@app.route('/admin/restore_db', methods=['GET', 'POST'])
def restore_database():
    """恢复数据库（仅管理员可访问）"""
    if not session.get('is_admin'):
        return "未授权访问", 403
    
    if request.method == 'POST':
        # 检查是否上传了文件
        if 'database_file' not in request.files:
            return "没有选择文件", 400
        
        file = request.files['database_file']
        
        if file.filename == '':
            return "没有选择文件", 400
        
        # 检查文件扩展名
        if not file.filename.endswith('.db'):
            return "只能上传.db文件", 400
        
        try:
            # 备份当前数据库
            if os.path.exists(DATABASE):
                backup_name = f"{DATABASE}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(DATABASE, backup_name)
                print(f"已创建备份: {backup_name}")
            
            # 保存上传的文件
            file.save(DATABASE)
            
            return '''
                <script>
                    alert("数据库恢复成功！");
                    window.location.href = "/admin";
                </script>
            '''
        except Exception as e:
            return f"恢复失败: {str(e)}", 500
    
    # GET请求显示上传表单
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>恢复数据库</title></head>
    <body>
        <h1>恢复数据库</h1>
        <p><strong>警告：</strong>此操作将覆盖当前所有数据！</p>
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="database_file" accept=".db" required>
            <br><br>
            <button type="submit" style="padding: 10px 20px; background: #e74c3c; color: white; border: none; border-radius: 5px; cursor: pointer;">
                确认恢复
            </button>
            <a href="/admin" style="margin-left: 20px;">取消</a>
        </form>
    </body>
    </html>
    '''

@app.route('/admin/backups')
def list_backups():
    if not session.get('is_admin'):
        return "未授权访问", 403

    backups = []
    for file in os.listdir('.'):
        if file.startswith('cycling.db.backup.') or file.endswith('_backup.db'):
            file_info = {
                'name': file,
                'size': os.path.getsize(file),
                'time': datetime.fromtimestamp(os.path.getctime(file)).strftime('%Y-%m-%d %H:%M:%S')
            }
            backups.append(file_info)

    # 按时间倒序排序
    backups.sort(key=lambda x: x['time'], reverse=True)

    return render_template('backup_list.html', backups=backups)

# 修改原有的管理面板路由，添加登录检查
@app.route('/admin')
def admin_panel():
    """管理员面板主页"""
    # 1. 验证密码
    if not session.get('is_admin'):
        # 未登录，重定向到登录页
        return redirect('/admin/login')
    
    # 2. 获取所有数据
    conn = sqlite3.connect(DATABASE)
    # 按日期倒序排列，方便查看最新数据
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, distance, time, date, is_anonymous, anonymous_id 
        FROM rides 
        ORDER BY date DESC, id DESC
    ''')
    all_rides = cursor.fetchall()
    conn.close()
    
    print(f"查询到 {len(all_rides)} 条记录")
    for i, ride in enumerate(all_rides[:5]):  # 只打印前5条
        print(f"记录 {i}: {ride}")
    # 3. 渲染管理模板
    return render_template('admin.html', rides=all_rides)
# 在 app.py 中添加新路由
@app.route('/admin/delete/<int:ride_id>', methods=['POST'])
def admin_delete(ride_id):
    """删除单条骑行记录"""
    # 1. 验证密码
    if not session.get('is_admin'):
        return jsonify({"success": False, "error": "未登录或会话已过期。"}), 403
    
    # 2. 执行删除
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM rides WHERE id = ?', (ride_id,))
        conn.commit()
        deleted = cursor.rowcount > 0  # 检查是否成功删除了行
    except Exception as e:
        deleted = False
        print(f"删除记录时出错: {e}")
    finally:
        conn.close()
    
    # 3. 返回结果
    if deleted:
        return jsonify({"success": True, "message": f"记录 ID {ride_id} 已删除。"})
    else:
        return jsonify({"success": False, "error": "删除失败，记录可能不存在。"})

# 添加登录页面路由
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理员登录页面"""
    # 如果已经登录，直接跳转到管理面板
    if session.get('is_admin'):
        return redirect('/admin')
    
    error = None
    if request.method == 'POST':
        # 验证密码
        provided_pass = request.form.get('admin_pass')
        if provided_pass == ADMIN_PASSWORD:
            # 密码正确，设置session
            session['is_admin'] = True
            return redirect('/admin')
        else:
            error = "密码错误，请重试。"
    
    # GET请求 或 密码错误时，显示登录表单
    return render_template('admin_login.html', error=error)



@app.route('/admin/logout')
def admin_logout():
    """管理员登出"""
    session.pop('is_admin', None)  # 清除session
    return redirect('/admin/login')
# 在 app.py 中添加以下代码
@app.route('/user/<identifier>')
def user_stats(identifier):
    """个人骑行统计页面"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 1. 获取用户所有骑行记录
    cursor.execute('''
        SELECT date, distance, time, (60 * distance / time) as speed, 
            is_anonymous, anonymous_id, name
        FROM rides 
        WHERE (name = ? OR anonymous_id = ?) AND time > 0
        ORDER BY date DESC
    ''', (identifier, identifier))
    records = cursor.fetchall()
    
    if not records:
        # 如果没有记录，返回空统计
        return render_template('user_stats.html', 
                              name=identifier, 
                              has_data=False,
                              records=[])
    first_record = records[0]
    is_anonymous_user = first_record[4]  # is_anonymous 字段
    display_name = first_record[5] if is_anonymous_user else first_record[6]
    # 2. 计算基本统计
    total_distance = sum(r[1] for r in records)
    total_time = sum(r[2] for r in records)
    average_speed = total_distance / (total_time/60) if total_time > 0 else 0
    total_rides = len(records)
    
    # 3. 计算最佳记录
    best_distance = max(records, key=lambda x: x[1])[1] if records else 0
    best_speed = max(records, key=lambda x: x[3])[3] if records else 0
    
    # 4. 按月份分组统计
    monthly_stats = {}
    for record in records:
        date = record[0]
        year_month = date[:7]  # 格式: YYYY-MM
        
        if year_month not in monthly_stats:
            monthly_stats[year_month] = {
                'distance': 0,
                'time': 0,
                'count': 0,
                'avg_speed': 0
            }
        
        monthly_stats[year_month]['distance'] += record[1]
        monthly_stats[year_month]['time'] += record[2]
        monthly_stats[year_month]['count'] += 1
    
    # 计算月度平均速度
    for month in monthly_stats.values():
        if month['time'] > 0:
            month['avg_speed'] = month['distance'] / (month['time']/60)
    
    # 5. 计算每周骑行统计（用于图表）
    weekly_distance = []
    weekly_speed = []
    weekly_dates = []
    
    # 按时间排序（从早到晚）
    sorted_records = sorted(records, key=lambda x: x[0])
    
    # 每5次骑行作为一个数据点（避免图表过于密集）
    chunk_size = 5
    for i in range(0, len(sorted_records), chunk_size):
        chunk = sorted_records[i:i+chunk_size]
        if chunk:
            chunk_distance = sum(r[1] for r in chunk)
            chunk_time = sum(r[2] for r in chunk)
            chunk_speed = chunk_distance / (chunk_time/60) if chunk_time > 0 else 0
            
            weekly_distance.append(chunk_distance)
            weekly_speed.append(chunk_speed)
            weekly_dates.append(f"第{i//chunk_size+1}组")
    
    # 如果骑行次数太少，就每条记录作为一个点
    if len(sorted_records) < 5:
        weekly_distance = [r[1] for r in sorted_records]
        weekly_speed = [r[3] for r in sorted_records]
        weekly_dates = [r[0] for r in sorted_records]
    
    # 6. 格式化记录用于前端显示
    formatted_records = []
    for record in records:
        formatted_records.append({
            'date': record[0],
            'distance': record[1],
            'time': record[2],
            'speed': record[3]
        })
    
    conn.close()
    
    return render_template('user_stats.html',
                          name=display_name,
                          has_data=True,
                          total_distance=total_distance,
                          total_time=total_time,
                          average_speed=average_speed,
                          total_rides=total_rides,
                          best_distance=best_distance,
                          best_speed=best_speed,
                          records=formatted_records,
                          monthly_stats=monthly_stats,
                          weekly_distance=weekly_distance,
                          weekly_speed=weekly_speed,
                          weekly_dates=weekly_dates,
                          is_anonymous=is_anonymous_user)



@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_answer = request.form.get('captcha', '').strip()
        correct_answer = session.get('captcha_answer', '')
    
        if not user_answer or user_answer != correct_answer:
            return jsonify({
                "success": False, 
                "message": f"验证码错误，正确答案是 {correct_answer}"
            }), 400
    
        # 验证成功后清除
        session.pop('captcha_answer', None)

        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        is_allowed, msg = check_ip_limit(client_ip)
        if not is_allowed:
            log_attack(client_ip, "频率限制", f"1分钟内提交{len(ip_submit_count.get(client_ip, []))}次")
            return jsonify({"success": False, "message": msg}), 429

        raw_name = request.form['name']
        name = sanitize_input(raw_name, max_length=12)

        if not name:
                    return jsonify({
                    "success": False,
                    "message": "姓名不能为空或包含非法字符"
                    }), 400
        raw_date = request.form.get('date', '')
        if raw_date:
            # 验证日期格式：YYYY-MM-DD
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', raw_date):
                return jsonify({
                    "success": False,
                    "message": "日期格式无效，请使用YYYY-MM-DD格式"
                }), 400
        # 记录本次提交
        if client_ip not in ip_submit_count:
            ip_submit_count[client_ip] = []
        ip_submit_count[client_ip].append(time_module.time())

        
        distance = float(request.form['distance'])
        time_val = float(request.form['time'])
        date = request.form.get('date')
        is_anonymous = request.form.get('is_anonymous') == '1'
        anonymous_id = None
        if is_anonymous:
            # 1. 生成固定匿名ID
            # 使用用户IP和盐值创建哈希，确保同一来源生成相同ID
            salt = "YOUR_APP_SECRET_SALT"  # 请替换为一个复杂的随机字符串
            user_ip = request.remote_addr or '0.0.0.0'
            raw_id = f"{salt}{user_ip}"
            
            # 取哈希值前8位，生成如“匿名骑士A1B2C3D4”
            hash_obj = hashlib.md5(raw_id.encode())
            hash_hex = hash_obj.hexdigest()[:8].upper()
            anonymous_id = f"匿名骑士{hash_hex}"
            
            # 2. 在数据库记录中，我们仍然保存真实姓名（用于内部管理），
            # 但会标记为匿名，并记录其匿名ID。
            # 注意：display_name 在查询结果中将被 anonymous_id 覆盖
        else:
            # 公开提交，anonymous_id 为 NULL
            anonymous_id = None
        # 处理上传数据

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rides (name, distance, time, date, is_anonymous, anonymous_id) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''',(name, distance, time_val, date, 1 if is_anonymous else 0, anonymous_id))
        conn.commit()
        conn.close()
        return jsonify({
            "success": True,
            "message": "数据提交成功！"+ ("（已匿名）" if is_anonymous else "")
        })
    try:
        ranking = get_ranking()
    except sqlite3.OperationalError:
        ranking = []
    captcha_question, captcha_answer = generate_math_captcha()
    session['captcha_answer'] = captcha_answer
    
    return render_template('index.html', 
                            ranking=ranking,
                            captcha_question=captcha_question)

@app.route('/get_ranking')
def get_ranking_json():
    sort_by = request.args.get('sort_by', 'distance')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    search_name = request.args.get('search_name', '')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    base_query = '''
        SELECT name, 
        distance,
        time, 
        date, 
        (60*distance / time) AS speed,
        is_anonymous,
        anonymous_id
    FROM rides 
    WHERE time > 0
    '''
    conditions = []
    params = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    if search_name:
        # 同时搜索真实姓名和匿名ID
        conditions.append("(name LIKE ? OR anonymous_id LIKE ?)")
        params.append(f"%{search_name}%")
        params.append(f"%{search_name}%")
    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    if sort_by == 'distance':
        base_query += " ORDER BY distance DESC"
    elif sort_by == 'speed':
        base_query += " ORDER BY speed DESC"
    elif sort_by == 'date':
        base_query += " ORDER BY date DESC"
    else:
        base_query += " ORDER BY distance DESC"
        
    cursor.execute(base_query, params)
    results = cursor.fetchall()
    conn.close()
    
    formatted_results = []
    for row in results:
        name, distance, time, date, speed, is_anonymous, anonymous_id = row
        display_name = anonymous_id if is_anonymous else name
        
        formatted_results.append({
            'name': display_name,  # 前端看到的是处理后的显示名
            'original_name': name,  # 保留原名，可用于后端管理（可选）
            'is_anonymous': bool(is_anonymous),
            'distance': distance,
            'time': time,
            'date': date,
            'speed': speed
        })
    
    return jsonify(formatted_results)

@app.after_request
def add_security_headers(response):
    """
    添加安全相关的HTTP头部，提供额外的XSS防护层。
    """
    # 内容安全策略 (CSP) - 严格限制资源加载
    # 注意：如果未来需要加载更多外部资源（如图标、字体），需在此添加
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "  # 允许本站脚本和Chart.js
        "style-src 'self' 'unsafe-inline'; "  # 允许内联样式
        "img-src 'self' data:; "  # 允许本站图片和dataURL
        "font-src 'self'; "
        "connect-src 'self'; "  # 限制AJAX请求到同源
        "frame-ancestors 'none';"  # 禁止页面被嵌入（防点击劫持）
    )
    
    # 防止浏览器猜测MIME类型
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # 防止点击劫持
    response.headers['X-Frame-Options'] = 'DENY'
    
    # 启用浏览器的XSS过滤器
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # 控制Referrer信息
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
