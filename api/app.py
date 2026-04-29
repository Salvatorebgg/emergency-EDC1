"""
急诊科 EDC 系统 - Flask API 后端
提供 RESTful API 接口连接 MySQL 数据库
"""

import json
import os
import base64
import hashlib
import hmac
import pymysql
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from datetime import datetime, date

app = Flask(__name__)
CORS(app)

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '5311600wang',
    'database': 'ed_emergency',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = pymysql.connect(**DB_CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


class DateTimeEncoder(json.JSONEncoder):
    """处理 datetime 序列化"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if isinstance(obj, datetime) else obj.strftime('%Y-%m-%d')
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)


def query_db(sql, args=None, one=False):
    """执行查询"""
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, args)
        result = cursor.fetchall()
        return result[0] if one and result else result


def execute_db(sql, args=None):
    """执行写操作"""
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, args)
        db.commit()
        return cursor.lastrowid


# ============================================================
# 第一阶段: 登录、权限与通用工具
# ============================================================

AUTH_SECRET = os.environ.get('EDC_AUTH_SECRET', 'edc-phase1-dev-secret')


def password_digest(password):
    """演示版密码摘要。生产环境请改用 bcrypt/argon2。"""
    return hashlib.sha256((password or '').encode('utf-8')).hexdigest()


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def _b64url_decode(data):
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode('utf-8'))


def make_token(user):
    payload = {
        'user_id': user.get('user_id'),
        'username': user.get('username'),
        'role_code': user.get('role_code'),
        'staff_id': user.get('staff_id'),
        'iat': int(datetime.now().timestamp())
    }
    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    payload_part = _b64url_encode(payload_raw)
    signature = hmac.new(AUTH_SECRET.encode('utf-8'), payload_part.encode('utf-8'), hashlib.sha256).digest()
    return f'{payload_part}.{_b64url_encode(signature)}'


def parse_token():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        payload_part, signature_part = token.split('.', 1)
        expected = hmac.new(AUTH_SECRET.encode('utf-8'), payload_part.encode('utf-8'), hashlib.sha256).digest()
        actual = _b64url_decode(signature_part)
        if not hmac.compare_digest(expected, actual):
            return None
        return json.loads(_b64url_decode(payload_part).decode('utf-8'))
    except Exception:
        return None


def current_staff_id():
    user = parse_token()
    return user.get('staff_id') if user else None


def log_audit(action, target_table=None, target_id=None, new_value=None, staff_id=None):
    """尽力写入审计日志；未执行升级脚本时不阻断业务。"""
    try:
        execute_db(
            "INSERT INTO sys_audit_log (staff_id, action, target_table, target_id, new_value, ip_address) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                staff_id or current_staff_id(),
                action,
                target_table,
                target_id,
                json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
                request.remote_addr
            )
        )
    except Exception:
        try:
            get_db().rollback()
        except Exception:
            pass


def missing_upgrade_response(error):
    if getattr(error, 'args', None) and error.args and error.args[0] in (1054, 1146):
        return jsonify({
            'success': False,
            'message': '数据库升级对象不存在，请先执行 sql/05_phase1_upgrade.sql 和 sql/06_phase2_upgrade.sql'
        }), 400
    return jsonify({'success': False, 'message': str(error)}), 400


def text_contains(source, keyword):
    return keyword and keyword.lower() in (source or '').lower()


def parse_datetime_input(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError('无效时间格式，支持 YYYY-MM-DD HH:MM:SS 或 HTML datetime-local')


def json_text(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def green_target_met(channel_type, metrics):
    channel_type = channel_type or ''
    checks = []
    if channel_type == '胸痛':
        if metrics.get('door_to_ecg') is not None:
            checks.append(metrics['door_to_ecg'] <= 600)
        if metrics.get('door_to_balloon') is not None:
            checks.append(metrics['door_to_balloon'] <= 5400)
        if metrics.get('door_to_needle') is not None:
            checks.append(metrics['door_to_needle'] <= 1800)
    elif channel_type == '卒中':
        if metrics.get('door_to_ct') is not None:
            checks.append(metrics['door_to_ct'] <= 1500)
        if metrics.get('door_to_needle') is not None:
            checks.append(metrics['door_to_needle'] <= 3600)
    elif channel_type == '创伤':
        if metrics.get('door_to_ct') is not None:
            checks.append(metrics['door_to_ct'] <= 1800)
        if metrics.get('door_to_surgery') is not None:
            checks.append(metrics['door_to_surgery'] <= 3600)
    else:
        if metrics.get('door_to_ecg') is not None:
            checks.append(metrics['door_to_ecg'] <= 600)
        if metrics.get('door_to_ct') is not None:
            checks.append(metrics['door_to_ct'] <= 1800)
        if metrics.get('door_to_surgery') is not None:
            checks.append(metrics['door_to_surgery'] <= 3600)
    if not checks:
        return None
    return 1 if all(checks) else 0


def green_metric_column(event_type):
    return {
        'ecg': 'door_to_ecg',
        'ct': 'door_to_ct',
        'needle': 'door_to_needle',
        'balloon': 'door_to_balloon',
        'surgery': 'door_to_surgery'
    }.get(event_type)


def build_quality_snapshot_items(quality_row, green_row):
    quality_row = quality_row or {}
    green_row = green_row or {}
    return [
        ('今日急诊量', quality_row.get('today_visits'), '人次', 60),
        ('当前在诊患者', quality_row.get('active_visits'), '人', 35),
        ('候诊超30分钟人数', quality_row.get('waiting_over_30min'), '人', 3),
        ('床位占用率', quality_row.get('bed_occupancy_rate'), '%', 85),
        ('绿色通道今日启动数', green_row.get('today_channel_count'), '例', 6),
        ('绿色通道达标率', green_row.get('target_met_rate'), '%', 90),
        ('抢救启动数', quality_row.get('rescue_today_count'), '例', 6),
        ('危急值未处理数', quality_row.get('critical_unhandled_count'), '条', 0),
        ('检验平均周转时间', quality_row.get('lab_avg_tat_min'), '分钟', 45),
        ('影像平均周转时间', quality_row.get('imaging_avg_tat_min'), '分钟', 60),
        ('危急值确认耗时', quality_row.get('critical_ack_avg_min'), '分钟', 10),
        ('平均停留时长', quality_row.get('avg_stay_minutes'), '分钟', 240)
    ]


def refresh_quality_indicator_snapshot(staff_id=None):
    quality_row = query_db("SELECT * FROM v_quality_dashboard", one=True) or {}
    green_row = query_db("SELECT * FROM v_green_channel_dashboard", one=True) or {}
    items = build_quality_snapshot_items(quality_row, green_row)
    snapshot_date = datetime.now().strftime('%Y-%m-%d')
    for name, value, unit, target in items:
        execute_db(
            "DELETE FROM ed_quality_indicator WHERE indicator_date=%s AND indicator_name=%s",
            (snapshot_date, name)
        )
        is_met = None
        if value is not None and target is not None:
            if name in ('候诊超30分钟人数', '危急值未处理数', '检验平均周转时间', '影像平均周转时间', '危急值确认耗时', '平均停留时长', '床位占用率'):
                is_met = 1 if float(value) <= float(target) else 0
            else:
                is_met = 1 if float(value) >= float(target) else 0
        execute_db(
            """
            INSERT INTO ed_quality_indicator (
                indicator_date, indicator_name, indicator_value, indicator_unit, target_value, is_met
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (snapshot_date, name, value, unit, target, is_met)
        )
    log_audit('QUALITY_REFRESH', 'ed_quality_indicator', None, {'count': len(items)}, staff_id=staff_id)
    return len(items)


@app.route('/api/auth/login', methods=['POST'])
def login():
    """登录并返回演示版 Bearer token。"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'}), 400
    try:
        user = query_db("""
            SELECT u.user_id, u.username, u.password_hash, u.role_code, u.staff_id, u.is_active,
                   s.staff_name, s.role_type, s.title
            FROM sys_user u
            LEFT JOIN sys_staff s ON u.staff_id = s.staff_id
            WHERE u.username = %s
        """, (username,), one=True)
        if not user or not user.get('is_active') or user.get('password_hash') != password_digest(password):
            return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
        execute_db("UPDATE sys_user SET last_login_at = NOW() WHERE user_id = %s", (user['user_id'],))
        safe_user = {k: v for k, v in user.items() if k != 'password_hash'}
        token = make_token(safe_user)
        log_audit('LOGIN', 'sys_user', user['user_id'], {'username': username}, user.get('staff_id'))
        return jsonify({'success': True, 'token': token, 'user': safe_user})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = parse_token()
    if not user:
        return jsonify({'success': False, 'message': '未登录'}), 401
    detail = query_db("""
        SELECT u.user_id, u.username, u.role_code, u.staff_id, s.staff_name, s.role_type, s.title
        FROM sys_user u
        LEFT JOIN sys_staff s ON u.staff_id = s.staff_id
        WHERE u.user_id = %s AND u.is_active = 1
    """, (user.get('user_id'),), one=True)
    return jsonify({'success': bool(detail), 'user': detail})


# ============================================================
# 仪表盘 / 大屏数据
# ============================================================

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    """获取急诊大屏统计数据"""
    data = query_db("SELECT * FROM v_ed_dashboard", one=True)
    # 分区统计
    zones = query_db("CALL sp_zone_statistics()")
    # 今日就诊列表
    visits = query_db("""
        SELECT visit_id, visit_no, patient_name, gender, age, age_unit,
               triage_level, triage_color, chief_complaint, visit_status,
               bed_code, bed_zone, attending_doctor_name, stay_minutes,
               allergy_history, arrival_mode, is_green_channel, is_pediatric,
               is_120_transfer, outcome_time, past_history, visit_time
        FROM v_ed_visit_full
        WHERE visit_status IN ('分诊中', '候诊', '就诊中', '观察中', '处置中')
          AND visit_time >= DATE_SUB(NOW(), INTERVAL 18 HOUR)
        ORDER BY
            CASE WHEN triage_level IS NULL THEN 9 ELSE triage_level END ASC,
            CASE visit_status
                WHEN '候诊' THEN 1
                WHEN '分诊中' THEN 2
                WHEN '处置中' THEN 3
                WHEN '就诊中' THEN 4
                WHEN '观察中' THEN 5
                WHEN '待入院' THEN 6
                ELSE 7
            END ASC,
            visit_time ASC
        LIMIT 60
    """)
    return jsonify({
        'stats': data,
        'zones': zones,
        'active_visits': visits
    })


# ============================================================
# 床位管理
# ============================================================

@app.route('/api/beds', methods=['GET'])
def get_beds():
    """获取所有床位状态"""
    zone = request.args.get('zone')
    base_sql = """
        SELECT v.*, b.current_visit_id
        FROM v_bed_status v
        LEFT JOIN ed_bed b ON b.bed_id = v.bed_id
    """
    if zone:
        beds = query_db(
            base_sql + " WHERE v.bed_zone = %s ORDER BY CASE v.bed_zone WHEN '红区' THEN 1 WHEN '黄区' THEN 2 WHEN '绿区' THEN 3 END, v.bed_code",
            (zone,)
        )
    else:
        beds = query_db(
            base_sql + " ORDER BY CASE v.bed_zone WHEN '红区' THEN 1 WHEN '黄区' THEN 2 WHEN '绿区' THEN 3 END, v.bed_code"
        )
    return jsonify(beds)


@app.route('/api/beds/assignable-visits', methods=['GET'])
def get_assignable_bed_visits():
    """获取可分配床位的患者列表。"""
    visits = query_db("""
        SELECT visit_id, visit_no, patient_name, gender, age, age_unit,
               triage_level, chief_complaint, visit_status, stay_minutes,
               bed_code, visit_time, attending_doctor_name
        FROM v_ed_visit_full
        WHERE bed_code IS NULL
          AND visit_status NOT IN ('已离院', '已转院', '死亡')
        ORDER BY CASE WHEN triage_level IS NULL THEN 9 ELSE triage_level END,
                 visit_time ASC
        LIMIT 60
    """)
    return jsonify(visits)


@app.route('/api/beds/<int:bed_id>/assign', methods=['POST'])
def assign_bed(bed_id):
    """分配床位给患者"""
    data = request.json or {}
    visit_id = data.get('visit_id')
    if not visit_id:
        return jsonify({'success': False, 'message': '缺少就诊记录 ID'}), 400
    try:
        bed = query_db(
            "SELECT bed_id, bed_code, bed_status, current_visit_id FROM ed_bed WHERE bed_id = %s",
            (bed_id,),
            one=True
        )
        if not bed:
            return jsonify({'success': False, 'message': '床位不存在'}), 404
        if bed.get('bed_status') != '空闲':
            return jsonify({'success': False, 'message': f"当前床位状态为 {bed.get('bed_status')}，暂不可分配"}), 400

        visit = query_db(
            "SELECT visit_id, visit_status FROM ed_visit WHERE visit_id = %s",
            (visit_id,),
            one=True
        )
        if not visit:
            return jsonify({'success': False, 'message': '就诊记录不存在'}), 404
        if visit.get('visit_status') in ('已离院', '已转院', '死亡'):
            return jsonify({'success': False, 'message': '该患者当前状态不可再分配床位'}), 400

        db = get_db()
        with db.cursor() as cursor:
            cursor.callproc('sp_assign_bed', (visit_id, bed_id))
            result = cursor.fetchall()
            db.commit()

        updated_bed = query_db("SELECT * FROM v_bed_status WHERE bed_id = %s", (bed_id,), one=True)
        return jsonify({
            'success': True,
            'message': '床位分配成功',
            'data': result[0] if result else None,
            'bed': updated_bed
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/beds/<int:bed_id>/release', methods=['POST'])
def release_bed(bed_id):
    """释放床位"""
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT bed_id, bed_status, current_visit_id FROM ed_bed WHERE bed_id = %s FOR UPDATE",
                (bed_id,)
            )
            bed = cursor.fetchone()
            if not bed:
                return jsonify({'success': False, 'message': '床位不存在'}), 404
            if bed.get('current_visit_id'):
                cursor.execute("UPDATE ed_visit SET bed_id = NULL WHERE visit_id = %s", (bed['current_visit_id'],))
            cursor.execute("UPDATE ed_bed SET bed_status='清洁中', current_visit_id=NULL WHERE bed_id=%s", (bed_id,))
            db.commit()

        updated_bed = query_db("SELECT * FROM v_bed_status WHERE bed_id = %s", (bed_id,), one=True)
        return jsonify({'success': True, 'message': '床位已释放，待清洁后可重新使用', 'bed': updated_bed})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/beds/<int:bed_id>/clean', methods=['POST'])
def clean_bed(bed_id):
    """清洁完成"""
    try:
        execute_db("UPDATE ed_bed SET bed_status='空闲' WHERE bed_id=%s AND bed_status='清洁中'", (bed_id,))
        return jsonify({'success': True, 'message': '床位已就绪'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ============================================================
# 患者管理
# ============================================================

@app.route('/api/patients', methods=['GET'])
def get_patients():
    """获取患者列表"""
    keyword = request.args.get('keyword', '')
    if keyword:
        patients = query_db(
            "SELECT * FROM patient_info WHERE patient_name LIKE %s OR patient_no LIKE %s OR phone LIKE %s ORDER BY patient_id DESC LIMIT 50",
            (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%')
        )
    else:
        patients = query_db("SELECT * FROM patient_info ORDER BY patient_id DESC LIMIT 50")
    return jsonify(patients)


@app.route('/api/patients/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    """获取患者详情"""
    patient = query_db("SELECT * FROM patient_info WHERE patient_id = %s", (patient_id,), one=True)
    if patient:
        visits = query_db(
            "SELECT * FROM ed_visit WHERE patient_id = %s ORDER BY visit_time DESC",
            (patient_id,)
        )
        patient['visits'] = visits
    return jsonify(patient)


@app.route('/api/patients/search', methods=['GET'])
def search_patients():
    """患者主索引检索：姓名、患者号、身份证、电话。"""
    keyword = (request.args.get('keyword') or '').strip()
    limit = min(int(request.args.get('limit', 30)), 100)
    args = []
    sql = """
        SELECT p.patient_id, p.patient_no, p.id_card_no, p.patient_name, p.gender, p.age, p.age_unit,
               p.phone, p.blood_type, p.allergy_history, p.past_history, p.insurance_type,
               COUNT(v.visit_id) AS visit_count,
               MAX(v.visit_time) AS last_visit_time,
               MAX(CASE WHEN v.visit_status NOT IN ('已离院','已转院','死亡') THEN v.visit_id ELSE NULL END) AS active_visit_id
        FROM patient_info p
        LEFT JOIN ed_visit v ON p.patient_id = v.patient_id
        WHERE 1=1
    """
    if keyword:
        like = f'%{keyword}%'
        sql += " AND (p.patient_name LIKE %s OR p.patient_no LIKE %s OR p.id_card_no LIKE %s OR p.phone LIKE %s)"
        args.extend([like, like, like, like])
    sql += """
        GROUP BY p.patient_id, p.patient_no, p.id_card_no, p.patient_name, p.gender, p.age, p.age_unit,
                 p.phone, p.blood_type, p.allergy_history, p.past_history, p.insurance_type
        ORDER BY last_visit_time DESC, p.patient_id DESC
        LIMIT %s
    """
    args.append(limit)
    patients = query_db(sql, args)
    return jsonify(patients)


# ============================================================
# 就诊管理
# ============================================================

@app.route('/api/visits', methods=['GET'])
def get_visits():
    """获取就诊列表"""
    status = request.args.get('status')
    date_filter = request.args.get('date')
    level = request.args.get('level')
    
    sql = "SELECT * FROM v_ed_visit_full WHERE 1=1"
    args = []
    
    if status:
        sql += " AND visit_status = %s"
        args.append(status)
    if date_filter:
        sql += " AND visit_date = %s"
        args.append(date_filter)
    if level:
        sql += " AND triage_level = %s"
        args.append(int(level))
    
    sql += " ORDER BY triage_level ASC, visit_time DESC LIMIT 100"
    visits = query_db(sql, args if args else None)
    return jsonify(visits)


@app.route('/api/visits/<int:visit_id>', methods=['GET'])
def get_visit(visit_id):
    """获取就诊详情"""
    visit = query_db("SELECT * FROM v_ed_visit_full WHERE visit_id = %s", (visit_id,), one=True)
    if not visit:
        return jsonify({'error': '未找到就诊记录'}), 404
    
    # 分诊评估
    triage = query_db("SELECT * FROM ed_triage_assessment WHERE visit_id = %s ORDER BY assess_time", (visit_id,))
    # 医嘱
    orders = query_db("SELECT o.*, s.staff_name as doctor_name FROM ed_order o LEFT JOIN sys_staff s ON o.doctor_id=s.staff_id WHERE o.visit_id = %s ORDER BY order_time", (visit_id,))
    # 检验
    labs = query_db("SELECT l.*, e.exam_name FROM ed_lab_order l LEFT JOIN sys_exam_dict e ON l.exam_id=e.exam_id WHERE l.visit_id = %s ORDER BY order_time", (visit_id,))
    # 影像
    imaging = query_db("SELECT i.*, e.exam_name FROM ed_imaging_order i LEFT JOIN sys_exam_dict e ON i.exam_id=e.exam_id WHERE i.visit_id = %s ORDER BY order_time", (visit_id,))
    # 护理
    nursing = query_db("SELECT n.*, s.staff_name as nurse_name FROM ed_nursing_record n LEFT JOIN sys_staff s ON n.nurse_id=s.staff_id WHERE n.visit_id = %s ORDER BY record_time", (visit_id,))
    # 绿色通道
    green = query_db("SELECT * FROM ed_green_channel WHERE visit_id = %s", (visit_id,), one=True)
    
    visit['triage_assessments'] = triage
    visit['orders'] = orders
    visit['labs'] = labs
    visit['imaging'] = imaging
    visit['nursing_records'] = nursing
    visit['green_channel'] = green
    
    return jsonify(visit)


@app.route('/api/visits/register', methods=['POST'])
def register_visit():
    """患者登记并创建急诊就诊"""
    data = request.json
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.callproc('sp_register_ed_visit', (
                data.get('patient_no'), data.get('id_card'), data.get('patient_name'),
                data.get('gender'), data.get('birth_date'), data.get('age'),
                data.get('age_unit', '岁'), data.get('phone'), data.get('address'),
                data.get('emergency_contact'), data.get('emergency_phone'),
                data.get('blood_type'), data.get('allergy_history'),
                data.get('past_history'), data.get('insurance_type'),
                data.get('arrival_mode', '步行'), data.get('chief_complaint'),
                data.get('present_illness'), data.get('nurse_id', 11)
            ))
            result = cursor.fetchall()
            db.commit()
        return jsonify({'success': True, 'data': result[0] if result else None})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ============================================================
# 分诊管理
# ============================================================

@app.route('/api/triage/queue', methods=['GET'])
def triage_queue():
    """获取分诊待处理队列"""
    queue = query_db("SELECT * FROM v_triage_queue")
    return jsonify(queue)


@app.route('/api/triage/waiting', methods=['GET'])
def waiting_queue():
    """获取候诊队列"""
    queue = query_db("""
        SELECT
            v.visit_id,
            v.visit_no,
            p.patient_name,
            p.gender,
            p.age,
            p.allergy_history,
            v.triage_level,
            v.triage_color,
            v.chief_complaint,
            v.triage_time,
            v.arrival_mode,
            v.is_green_channel,
            v.is_120_transfer,
            TIMESTAMPDIFF(MINUTE, v.triage_time, NOW()) AS wait_minutes
        FROM ed_visit v
        LEFT JOIN patient_info p ON v.patient_id = p.patient_id
        WHERE v.visit_status = '候诊'
          AND v.triage_time IS NOT NULL
          AND v.triage_time >= DATE_SUB(NOW(), INTERVAL 18 HOUR)
        ORDER BY
            CASE WHEN v.triage_level IS NULL THEN 9 ELSE v.triage_level END ASC,
            v.triage_time ASC
        LIMIT 20
    """)
    return jsonify(queue)


@app.route('/api/triage/assess', methods=['POST'])
def triage_assess():
    """分诊评估"""
    data = request.json
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.callproc('sp_triage_assess', (
                data.get('visit_id'), data.get('nurse_id'),
                data.get('consciousness'), data.get('pain_score'),
                data.get('hr'), data.get('bp_systolic'), data.get('bp_diastolic'),
                data.get('temperature'), data.get('rr'), data.get('spo2'),
                data.get('weight'), data.get('fall_risk'),
                data.get('triage_level'), data.get('triage_category'),
                data.get('brief_history')
            ))
            result = cursor.fetchall()
            db.commit()
        return jsonify({'success': True, 'data': result[0] if result else None})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


def calculate_triage(data):
    complaint = (data.get('chief_complaint') or data.get('complaint') or '').lower()
    arrival_mode = data.get('arrival_mode') or ''
    consciousness = data.get('consciousness') or '清醒'
    age = int(data.get('age') or 0)
    hr = int(data.get('hr') or 0)
    bp_s = int(data.get('bp_systolic') or data.get('bp_sys') or 0)
    temp = float(data.get('temperature') or 0)
    rr = int(data.get('rr') or 0)
    spo2 = int(data.get('spo2') or 0)
    pain = int(data.get('pain_score') or 0)

    score = 0
    reasons = []

    red_keywords = ['心脏骤停', '呼吸心跳停止', '意识丧失', '昏迷', '大出血', '休克', '抽搐持续', '严重创伤']
    orange_keywords = ['胸痛', '呼吸困难', '气促', '偏瘫', '中风', '卒中', '剧烈腹痛', '中毒', '车祸', '坠落', '高热']
    yellow_keywords = ['发热', '腹痛', '呕吐', '头晕', '腹泻', '腰痛', '皮疹']

    if any(k in complaint for k in red_keywords):
        score += 100
        reasons.append('主诉命中濒危关键词')
    elif any(k in complaint for k in orange_keywords):
        score += 75
        reasons.append('主诉命中危重关键词')
    elif any(k in complaint for k in yellow_keywords):
        score += 45
        reasons.append('主诉命中急症关键词')
    else:
        score += 20
        reasons.append('普通急诊主诉')

    if consciousness not in ('清醒', '正常', ''):
        score += 60
        reasons.append('意识状态异常')
    if spo2 and spo2 < 90:
        score += 80
        reasons.append('血氧低于90%')
    elif spo2 and spo2 < 94:
        score += 45
        reasons.append('血氧偏低')
    if bp_s and (bp_s < 90 or bp_s >= 180):
        score += 45
        reasons.append('收缩压危险范围')
    if hr and (hr < 45 or hr > 130):
        score += 40
        reasons.append('心率危险范围')
    if rr and (rr < 10 or rr > 30):
        score += 35
        reasons.append('呼吸频率异常')
    if temp and temp >= 39.5:
        score += 25
        reasons.append('高热')
    if pain >= 8:
        score += 20
        reasons.append('重度疼痛')
    if arrival_mode == '120急救':
        score += 15
        reasons.append('120急救转入')
    if age >= 80:
        score += 10
        reasons.append('高龄患者')

    if score >= 100:
        level, color = 1, '红'
    elif score >= 75:
        level, color = 2, '橙'
    elif score >= 45:
        level, color = 3, '黄'
    elif score >= 25:
        level, color = 4, '绿'
    else:
        level, color = 5, '蓝'

    return {
        'triage_level': level,
        'triage_color': color,
        'priority_score': score,
        'reasons': reasons,
        'recommendation': f'{level}级{color}色分诊，建议{"立即抢救" if level == 1 else "优先处置" if level == 2 else "按序候诊并动态复评"}'
    }


@app.route('/api/triage/evaluate', methods=['POST'])
def triage_evaluate():
    """智能分诊评分，可选择写回就诊记录。"""
    data = request.json or {}
    result = calculate_triage(data)
    visit_id = data.get('visit_id')
    apply_result = bool(data.get('apply'))
    if visit_id and apply_result:
        try:
            execute_db("""
                UPDATE ed_visit
                SET triage_level=%s, triage_color=%s, priority_score=%s, triage_reason=%s,
                    triage_time=NOW(), visit_status=CASE WHEN visit_status='分诊中' THEN '候诊' ELSE visit_status END
                WHERE visit_id=%s
            """, (
                result['triage_level'], result['triage_color'], result['priority_score'],
                '；'.join(result['reasons']), visit_id
            ))
            log_audit('TRIAGE_EVALUATE', 'ed_visit', visit_id, result)
        except Exception as e:
            return missing_upgrade_response(e)
    return jsonify({'success': True, 'data': result})


# ============================================================
# 医嘱管理
# ============================================================

@app.route('/api/visits/<int:visit_id>/orders', methods=['GET'])
def get_orders(visit_id):
    """获取就诊医嘱"""
    orders = query_db(
        "SELECT o.*, s.staff_name as doctor_name FROM ed_order o LEFT JOIN sys_staff s ON o.doctor_id=s.staff_id WHERE o.visit_id = %s ORDER BY order_time",
        (visit_id,)
    )
    return jsonify(orders)


@app.route('/api/visits/<int:visit_id>/orders', methods=['POST'])
def add_order(visit_id):
    """新增医嘱"""
    data = request.json
    try:
        order_id = execute_db("""
            INSERT INTO ed_order (visit_id, order_time, doctor_id, order_type, order_category,
                order_content, item_code, dosage, frequency, route, is_stat)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            visit_id, data.get('doctor_id'), data.get('order_type'),
            data.get('order_category', '临时'), data.get('order_content'),
            data.get('item_code'), data.get('dosage'), data.get('frequency'),
            data.get('route'), data.get('is_stat', 0)
        ))
        return jsonify({'success': True, 'order_id': order_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/orders/<int:order_id>/execute', methods=['POST'])
def execute_order(order_id):
    """执行医嘱"""
    data = request.json
    try:
        execute_db("""
            UPDATE ed_order SET order_status='已完成', execute_time=NOW(), execute_nurse_id=%s
            WHERE order_id=%s
        """, (data.get('nurse_id'), order_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/orders/<int:order_id>/review', methods=['POST'])
def review_order(order_id):
    """医嘱审核：通过后进入待执行，不通过则取消。"""
    data = request.json or {}
    approved = bool(data.get('approved', True))
    reviewer_id = data.get('reviewer_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_order
            SET review_status=%s, reviewer_id=%s, review_time=NOW(),
                order_status=CASE WHEN %s=1 THEN order_status ELSE '已取消' END,
                cancel_reason=CASE WHEN %s=1 THEN cancel_reason ELSE %s END
            WHERE order_id=%s
        """, (
            '已审核' if approved else '已驳回',
            reviewer_id, 1 if approved else 0, 1 if approved else 0,
            data.get('reason') or '审核驳回', order_id
        ))
        log_audit('ORDER_REVIEW', 'ed_order', order_id, {'approved': approved, 'reviewer_id': reviewer_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """取消医嘱。"""
    data = request.json or {}
    try:
        execute_db("""
            UPDATE ed_order
            SET order_status='已取消', cancel_reason=%s, stop_time=NOW()
            WHERE order_id=%s AND order_status NOT IN ('已完成','已取消')
        """, (data.get('reason') or '医生取消', order_id))
        log_audit('ORDER_CANCEL', 'ed_order', order_id, {'reason': data.get('reason')})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/orders/<int:order_id>/execute-detail', methods=['POST'])
def execute_order_detail(order_id):
    """护士执行医嘱并记录闭环明细。"""
    data = request.json or {}
    nurse_id = data.get('nurse_id') or current_staff_id()
    try:
        execution_id = execute_db("""
            INSERT INTO ed_order_execution (order_id, execute_time, execute_nurse_id, execution_status, result_note, vital_snapshot)
            VALUES (%s, NOW(), %s, %s, %s, %s)
        """, (
            order_id, nurse_id, data.get('execution_status', '已执行'),
            data.get('result_note'), json.dumps(data.get('vital_snapshot'), ensure_ascii=False) if data.get('vital_snapshot') else None
        ))
        execute_db("""
            UPDATE ed_order
            SET order_status='已完成', execute_time=NOW(), execute_nurse_id=%s
            WHERE order_id=%s
        """, (nurse_id, order_id))
        log_audit('ORDER_EXECUTE', 'ed_order', order_id, {'execution_id': execution_id, 'nurse_id': nurse_id})
        return jsonify({'success': True, 'execution_id': execution_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/doctor/worklist', methods=['GET'])
def doctor_worklist():
    """医生工作站患者列表。"""
    doctor_id = request.args.get('doctor_id')
    sql = """
        SELECT ev.visit_id, ev.visit_no, p.patient_name, p.gender, p.age, p.age_unit,
               ev.visit_time, ev.visit_status, ev.triage_level, ev.triage_color,
               ev.chief_complaint, b.bed_code, b.bed_zone, ev.attending_doctor_id,
               s.staff_name AS attending_doctor_name,
               TIMESTAMPDIFF(MINUTE, ev.visit_time, IFNULL(ev.outcome_time, NOW())) AS stay_minutes,
               p.allergy_history,
               (SELECT COUNT(*) FROM ed_order o WHERE o.visit_id=ev.visit_id AND o.order_status='待执行') AS pending_orders,
               (SELECT COUNT(*) FROM ed_lab_order l WHERE l.visit_id=ev.visit_id AND l.lab_status <> '已报告') AS pending_labs,
               (SELECT MAX(record_time) FROM ed_medical_record mr WHERE mr.visit_id=ev.visit_id) AS last_record_time
        FROM ed_visit ev
        JOIN patient_info p ON ev.patient_id = p.patient_id
        LEFT JOIN ed_bed b ON ev.bed_id = b.bed_id
        LEFT JOIN sys_staff s ON ev.attending_doctor_id = s.staff_id
        WHERE ev.visit_date = CURDATE()
          AND ev.visit_status IN ('分诊中','候诊','就诊中','观察中','处置中')
    """
    args = []
    if doctor_id:
        sql += " AND (ev.attending_doctor_id = %s OR ev.attending_doctor_id IS NULL)"
        args.append(doctor_id)
    sql += " ORDER BY ev.triage_level ASC, ev.visit_time ASC"
    return jsonify(query_db(sql, args if args else None))


@app.route('/api/visits/<int:visit_id>/medical-records', methods=['GET'])
def get_medical_records(visit_id):
    records = query_db("""
        SELECT mr.*, s.staff_name AS doctor_name
        FROM ed_medical_record mr
        LEFT JOIN sys_staff s ON mr.doctor_id = s.staff_id
        WHERE mr.visit_id=%s
        ORDER BY mr.record_time DESC
    """, (visit_id,))
    return jsonify(records)


@app.route('/api/visits/<int:visit_id>/medical-records', methods=['POST'])
def add_medical_record(visit_id):
    """医生写诊疗记录。"""
    data = request.json or {}
    try:
        record_id = execute_db("""
            INSERT INTO ed_medical_record (
                visit_id, doctor_id, record_time, record_type, chief_complaint, present_illness,
                physical_exam, assessment, treatment_plan, doctor_orders,
                hr, bp_systolic, bp_diastolic, temperature, rr, spo2
            ) VALUES (%s,%s,NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            visit_id, data.get('doctor_id') or current_staff_id() or 1,
            data.get('record_type', '初诊'), data.get('chief_complaint'), data.get('present_illness'),
            data.get('physical_exam'), data.get('assessment'), data.get('treatment_plan'), data.get('doctor_orders'),
            data.get('hr'), data.get('bp_systolic'), data.get('bp_diastolic'), data.get('temperature'), data.get('rr'), data.get('spo2')
        ))
        if data.get('icd_code'):
            execute_db("UPDATE ed_visit SET icd_code=%s WHERE visit_id=%s", (data.get('icd_code'), visit_id))
        log_audit('MEDICAL_RECORD_CREATE', 'ed_medical_record', record_id, {'visit_id': visit_id})
        return jsonify({'success': True, 'record_id': record_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/visits/<int:visit_id>/diagnoses', methods=['POST'])
def add_visit_diagnosis(visit_id):
    """新增诊断并同步主诊断到就诊记录。"""
    data = request.json or {}
    try:
        diagnosis_id = execute_db("""
            INSERT INTO ed_diagnosis (visit_id, icd_code, diagnosis_name, diagnosis_type, doctor_id, diagnose_time, is_primary)
            VALUES (%s,%s,%s,%s,%s,NOW(),%s)
        """, (
            visit_id, data.get('icd_code'), data.get('diagnosis_name'),
            data.get('diagnosis_type', '初步诊断'), data.get('doctor_id') or current_staff_id() or 1,
            data.get('is_primary', 1)
        ))
        if data.get('is_primary', 1):
            execute_db("UPDATE ed_visit SET icd_code=%s WHERE visit_id=%s", (data.get('icd_code'), visit_id))
        log_audit('DIAGNOSIS_CREATE', 'ed_diagnosis', diagnosis_id, {'visit_id': visit_id})
        return jsonify({'success': True, 'diagnosis_id': diagnosis_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/nurse/tasks', methods=['GET'])
def nurse_tasks():
    """护士工作站待执行任务。"""
    status = request.args.get('status', '待执行')
    tasks = query_db("""
        SELECT o.order_id, o.visit_id, o.order_time, o.order_type, o.order_category, o.order_content,
               o.dosage, o.frequency, o.route, o.is_stat, o.order_status, o.review_status,
               v.visit_no, p.patient_name, p.gender, p.age, p.age_unit,
               ev.triage_level, ev.triage_color, b.bed_code, s.staff_name AS doctor_name
        FROM ed_order o
        JOIN ed_visit ev ON o.visit_id = ev.visit_id
        JOIN patient_info p ON ev.patient_id = p.patient_id
        LEFT JOIN ed_bed b ON ev.bed_id = b.bed_id
        LEFT JOIN sys_staff s ON o.doctor_id = s.staff_id
        LEFT JOIN v_ed_visit_full v ON o.visit_id = v.visit_id
        WHERE o.order_status = %s
          AND ev.visit_status NOT IN ('已离院','已转院','死亡')
        ORDER BY o.is_stat DESC, ev.triage_level ASC, o.order_time ASC
    """, (status,))
    return jsonify(tasks)


# ============================================================
# 检验管理
# ============================================================

def create_or_update_critical_value(lab_id):
    """根据检验结果生成或更新危急值。"""
    lab = query_db("""
        SELECT l.lab_id, l.visit_id, l.result_flag, l.result_value, l.reference_range,
               e.exam_name, v.attending_doctor_id
        FROM ed_lab_order l
        LEFT JOIN sys_exam_dict e ON l.exam_id = e.exam_id
        LEFT JOIN ed_visit v ON l.visit_id = v.visit_id
        WHERE l.lab_id = %s
    """, (lab_id,), one=True)
    if not lab or lab.get('result_flag') not in ('HH', 'LL'):
        return None

    critical = query_db("SELECT critical_id FROM ed_critical_value WHERE lab_id=%s", (lab_id,), one=True)
    payload = {
        'lab_id': lab_id,
        'visit_id': lab.get('visit_id'),
        'critical_level': lab.get('result_flag'),
        'item_name': lab.get('exam_name') or '检验项目',
        'result_value': str(lab.get('result_value') or ''),
        'reference_range': lab.get('reference_range'),
        'notify_doctor_id': lab.get('attending_doctor_id'),
        'notify_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    if critical:
        execute_db("""
            UPDATE ed_critical_value
            SET critical_level=%s, item_name=%s, result_value=%s, reference_range=%s,
                notify_doctor_id=%s, notify_time=NOW(), status=CASE WHEN status='已处理' THEN status ELSE '未确认' END
            WHERE critical_id=%s
        """, (
            payload['critical_level'], payload['item_name'], payload['result_value'],
            payload['reference_range'], payload['notify_doctor_id'], critical['critical_id']
        ))
        critical_id = critical['critical_id']
    else:
        critical_id = execute_db("""
            INSERT INTO ed_critical_value (
                lab_id, visit_id, critical_level, item_name, result_value, reference_range,
                notify_doctor_id, notify_time, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),'未确认')
        """, (
            payload['lab_id'], payload['visit_id'], payload['critical_level'], payload['item_name'],
            payload['result_value'], payload['reference_range'], payload['notify_doctor_id']
        ))
    try:
        execute_db("""
            INSERT INTO ed_alert_event (visit_id, alert_type, severity, title, message, alert_status, created_by)
            VALUES (%s, 'lab', 'critical', %s, %s, '未处理', %s)
        """, (
            payload['visit_id'],
            f"危急值 {payload['item_name']}",
            f"{payload['item_name']} {payload['critical_level']}，结果 {payload['result_value']}，参考 {payload['reference_range'] or '-'}",
            current_staff_id()
        ))
    except Exception:
        try:
            get_db().rollback()
        except Exception:
            pass
    return critical_id


@app.route('/api/visits/<int:visit_id>/labs', methods=['GET'])
def get_labs(visit_id):
    """获取检验结果"""
    labs = query_db(
        "SELECT l.*, e.exam_name, e.reference_low, e.reference_high, e.reference_unit FROM ed_lab_order l LEFT JOIN sys_exam_dict e ON l.exam_id=e.exam_id WHERE l.visit_id = %s ORDER BY order_time",
        (visit_id,)
    )
    return jsonify(labs)


@app.route('/api/visits/<int:visit_id>/labs', methods=['POST'])
def add_lab(visit_id):
    """新增检验申请"""
    data = request.json or {}
    try:
        lab_id = execute_db("""
            INSERT INTO ed_lab_order (visit_id, exam_id, order_time, doctor_id, specimen_type, is_stat)
            VALUES (%s, %s, NOW(), %s, %s, %s)
        """, (visit_id, data.get('exam_id'), data.get('doctor_id'),
              data.get('specimen_type'), data.get('is_stat', 0)))
        log_audit('LAB_ORDER_CREATE', 'ed_lab_order', lab_id, {'visit_id': visit_id, 'exam_id': data.get('exam_id')})
        return jsonify({'success': True, 'lab_id': lab_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/labs/worklist', methods=['GET'])
def get_lab_worklist():
    """检验闭环工作列表。"""
    status = request.args.get('status')
    sql = "SELECT * FROM v_lab_worklist WHERE 1=1"
    args = []
    if status:
        sql += " AND lab_status = %s"
        args.append(status)
    sql += " ORDER BY is_stat DESC, triage_level ASC, order_time ASC"
    return jsonify(query_db(sql, args if args else None))


@app.route('/api/labs/<int:lab_id>/collect', methods=['POST'])
def collect_lab_specimen(lab_id):
    """采样。"""
    data = request.json or {}
    nurse_id = data.get('nurse_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_lab_order
            SET specimen_time=NOW(), collect_nurse_id=%s,
                specimen_type=COALESCE(%s, specimen_type), lab_status='已采集'
            WHERE lab_id=%s
        """, (nurse_id, data.get('specimen_type'), lab_id))
        log_audit('LAB_COLLECT', 'ed_lab_order', lab_id, {'nurse_id': nurse_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/labs/<int:lab_id>/receive', methods=['POST'])
def receive_lab_specimen(lab_id):
    """检验科接收标本。"""
    data = request.json or {}
    technician_id = data.get('technician_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_lab_order
            SET receive_time=NOW(), lab_technician_id=%s,
                lab_status=CASE WHEN lab_status='待采集' THEN '已采集' ELSE lab_status END
            WHERE lab_id=%s
        """, (technician_id, lab_id))
        log_audit('LAB_RECEIVE', 'ed_lab_order', lab_id, {'technician_id': technician_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/labs/<int:lab_id>/start', methods=['POST'])
def start_lab_test(lab_id):
    """开始检验。"""
    data = request.json or {}
    technician_id = data.get('technician_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_lab_order
            SET lab_status='检验中', lab_technician_id=%s,
                receive_time=COALESCE(receive_time, NOW())
            WHERE lab_id=%s
        """, (technician_id, lab_id))
        log_audit('LAB_START', 'ed_lab_order', lab_id, {'technician_id': technician_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/labs/<int:lab_id>/result', methods=['PUT'])
def update_lab_result(lab_id):
    """更新检验结果"""
    data = request.json or {}
    try:
        execute_db("""
            UPDATE ed_lab_order SET lab_status='已报告', report_time=NOW(),
                result_value=%s, result_unit=%s, result_flag=%s, result_text=%s, reference_range=%s,
                lab_technician_id=COALESCE(%s, lab_technician_id)
            WHERE lab_id=%s
        """, (data.get('result_value'), data.get('result_unit'), data.get('result_flag'),
              data.get('result_text'), data.get('reference_range'), data.get('technician_id') or current_staff_id(), lab_id))
        critical_id = create_or_update_critical_value(lab_id)
        log_audit('LAB_REPORT', 'ed_lab_order', lab_id, {'critical_id': critical_id, 'result_flag': data.get('result_flag')})
        return jsonify({'success': True, 'critical_id': critical_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/labs/<int:lab_id>/confirm', methods=['POST'])
def confirm_lab_result(lab_id):
    """医生确认检验报告。"""
    data = request.json or {}
    doctor_id = data.get('doctor_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_lab_order
            SET confirm_doctor_id=%s, confirm_time=NOW()
            WHERE lab_id=%s
        """, (doctor_id, lab_id))
        critical = query_db("SELECT critical_id FROM ed_critical_value WHERE lab_id=%s AND status<>'已处理'", (lab_id,), one=True)
        if critical:
            execute_db("""
                UPDATE ed_critical_value
                SET acknowledged_by=%s, acknowledged_at=NOW(),
                    action_note=COALESCE(%s, action_note), status='已处理'
                WHERE critical_id=%s
            """, (doctor_id, data.get('action_note') or '医生确认检验报告', critical['critical_id']))
        log_audit('LAB_CONFIRM', 'ed_lab_order', lab_id, {'doctor_id': doctor_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/critical-values', methods=['GET'])
def get_critical_values():
    """获取危急值告警。"""
    status = request.args.get('status')
    sql = "SELECT * FROM v_critical_values_active WHERE 1=1"
    args = []
    if status:
        sql += " AND status = %s"
        args.append(status)
    sql += " ORDER BY created_at DESC"
    return jsonify(query_db(sql, args if args else None))


@app.route('/api/critical-values/<int:critical_id>/ack', methods=['POST'])
def acknowledge_critical_value(critical_id):
    """确认并处理危急值。"""
    data = request.json or {}
    staff_id = data.get('staff_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_critical_value
            SET acknowledged_by=%s, acknowledged_at=NOW(),
                action_note=%s, status='已处理',
                notify_time=COALESCE(notify_time, NOW())
            WHERE critical_id=%s
        """, (staff_id, data.get('action_note') or '已知悉并处理', critical_id))
        execute_db("""
            UPDATE ed_alert_event
            SET alert_status='已处理', handled_by=%s, handled_at=NOW()
            WHERE alert_type='lab' AND message LIKE %s AND alert_status <> '已处理'
        """, (staff_id, f'%危急值%'))
        log_audit('CRITICAL_ACK', 'ed_critical_value', critical_id, {'staff_id': staff_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


# ============================================================
# 影像管理
# ============================================================

@app.route('/api/visits/<int:visit_id>/imaging', methods=['GET'])
def get_imaging(visit_id):
    """获取影像检查"""
    imaging = query_db(
        "SELECT i.*, e.exam_name FROM ed_imaging_order i LEFT JOIN sys_exam_dict e ON i.exam_id=e.exam_id WHERE i.visit_id = %s ORDER BY order_time",
        (visit_id,)
    )
    return jsonify(imaging)


@app.route('/api/visits/<int:visit_id>/imaging', methods=['POST'])
def add_imaging(visit_id):
    """新增影像申请"""
    data = request.json or {}
    try:
        imaging_id = execute_db("""
            INSERT INTO ed_imaging_order (visit_id, exam_id, order_time, doctor_id, is_stat)
            VALUES (%s, %s, NOW(), %s, %s)
        """, (visit_id, data.get('exam_id'), data.get('doctor_id'), data.get('is_stat', 0)))
        log_audit('IMAGING_ORDER_CREATE', 'ed_imaging_order', imaging_id, {'visit_id': visit_id, 'exam_id': data.get('exam_id')})
        return jsonify({'success': True, 'imaging_id': imaging_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/imaging/worklist', methods=['GET'])
def get_imaging_worklist():
    status = request.args.get('status')
    sql = "SELECT * FROM v_imaging_worklist WHERE 1=1"
    args = []
    if status:
        sql += " AND imaging_status = %s"
        args.append(status)
    sql += " ORDER BY is_stat DESC, triage_level ASC, order_time ASC"
    return jsonify(query_db(sql, args if args else None))


@app.route('/api/imaging/<int:imaging_id>/start', methods=['POST'])
def start_imaging_exam(imaging_id):
    data = request.json or {}
    technician_id = data.get('technician_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_imaging_order
            SET imaging_status='检查中', arrive_time=COALESCE(arrive_time, NOW()),
                exam_time=COALESCE(exam_time, NOW()), technician_id=%s, exam_room=%s
            WHERE imaging_id=%s
        """, (technician_id, data.get('exam_room'), imaging_id))
        log_audit('IMAGING_START', 'ed_imaging_order', imaging_id, {'technician_id': technician_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/imaging/<int:imaging_id>/report', methods=['PUT'])
def report_imaging_result(imaging_id):
    data = request.json or {}
    try:
        execute_db("""
            UPDATE ed_imaging_order
            SET imaging_status='已报告', report_time=NOW(), report_text=%s, impression=%s,
                radiologist_id=%s, technician_id=COALESCE(%s, technician_id), exam_room=COALESCE(%s, exam_room)
            WHERE imaging_id=%s
        """, (
            data.get('report_text'), data.get('impression'),
            data.get('radiologist_id') or current_staff_id(),
            data.get('technician_id'), data.get('exam_room'), imaging_id
        ))
        log_audit('IMAGING_REPORT', 'ed_imaging_order', imaging_id, {'radiologist_id': data.get('radiologist_id') or current_staff_id()})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/imaging/<int:imaging_id>/confirm', methods=['POST'])
def confirm_imaging_result(imaging_id):
    data = request.json or {}
    doctor_id = data.get('doctor_id') or current_staff_id()
    try:
        execute_db("""
            UPDATE ed_imaging_order
            SET confirm_doctor_id=%s, confirm_time=NOW()
            WHERE imaging_id=%s
        """, (doctor_id, imaging_id))
        log_audit('IMAGING_CONFIRM', 'ed_imaging_order', imaging_id, {'doctor_id': doctor_id})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


# ============================================================
# 护理记录
# ============================================================

@app.route('/api/visits/<int:visit_id>/nursing', methods=['GET'])
def get_nursing(visit_id):
    """获取护理记录"""
    records = query_db(
        "SELECT n.*, s.staff_name as nurse_name FROM ed_nursing_record n LEFT JOIN sys_staff s ON n.nurse_id=s.staff_id WHERE n.visit_id = %s ORDER BY record_time",
        (visit_id,)
    )
    return jsonify(records)


@app.route('/api/visits/<int:visit_id>/nursing', methods=['POST'])
def add_nursing(visit_id):
    """新增护理记录"""
    data = request.json
    try:
        nursing_id = execute_db("""
            INSERT INTO ed_nursing_record (visit_id, nurse_id, record_time, record_type,
                hr, bp_systolic, bp_diastolic, temperature, rr, spo2, consciousness, pain_score,
                intake_ml, output_ml, iv_fluid, nursing_content, special_notes)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            visit_id, data.get('nurse_id'), data.get('record_type', '常规'),
            data.get('hr'), data.get('bp_systolic'), data.get('bp_diastolic'),
            data.get('temperature'), data.get('rr'), data.get('spo2'),
            data.get('consciousness'), data.get('pain_score'),
            data.get('intake_ml'), data.get('output_ml'),
            data.get('iv_fluid'), data.get('nursing_content'), data.get('special_notes')
        ))
        return jsonify({'success': True, 'nursing_id': nursing_id})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ============================================================
# 患者离科
# ============================================================

@app.route('/api/visits/<int:visit_id>/discharge', methods=['POST'])
def discharge_patient(visit_id):
    """患者离科"""
    data = request.json
    try:
        db = get_db()
        with db.cursor() as cursor:
            cursor.callproc('sp_discharge_patient', (
                visit_id, data.get('outcome'), data.get('dest_dept'), data.get('icd_code')
            ))
            result = cursor.fetchall()
            db.commit()
        return jsonify({'success': True, 'data': result[0] if result else None})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ============================================================
# 字典查询
# ============================================================

@app.route('/api/dict/diagnosis', methods=['GET'])
def get_diagnosis_dict():
    """获取诊断字典"""
    keyword = request.args.get('keyword', '')
    if keyword:
        items = query_db(
            "SELECT * FROM sys_diagnosis_dict WHERE icd_name LIKE %s OR icd_code LIKE %s ORDER BY is_common DESC, sort_order LIMIT 30",
            (f'%{keyword}%', f'%{keyword}%')
        )
    else:
        items = query_db("SELECT * FROM sys_diagnosis_dict WHERE is_common=1 ORDER BY sort_order")
    return jsonify(items)


@app.route('/api/dict/medicine', methods=['GET'])
def get_medicine_dict():
    """获取药品字典"""
    keyword = request.args.get('keyword', '')
    if keyword:
        items = query_db(
            "SELECT * FROM sys_medicine_dict WHERE medicine_name LIKE %s OR medicine_code LIKE %s LIMIT 30",
            (f'%{keyword}%', f'%{keyword}%')
        )
    else:
        items = query_db("SELECT * FROM sys_medicine_dict WHERE is_emergency=1")
    return jsonify(items)


@app.route('/api/medication/check', methods=['POST'])
def medication_check():
    """药学校验：过敏、重复医嘱、规则提示。"""
    data = request.json or {}
    visit_id = data.get('visit_id')
    medicine_name = (data.get('medicine_name') or data.get('order_content') or '').strip()
    if not visit_id or not medicine_name:
        return jsonify({'success': False, 'message': '请提供 visit_id 和 medicine_name'}), 400

    visit = query_db("""
        SELECT v.visit_id, p.patient_name, p.allergy_history, p.past_history
        FROM ed_visit v
        JOIN patient_info p ON v.patient_id = p.patient_id
        WHERE v.visit_id = %s
    """, (visit_id,), one=True)
    if not visit:
        return jsonify({'success': False, 'message': '未找到就诊记录'}), 404

    warnings = []
    rules = query_db("SELECT * FROM sys_drug_warning_rule WHERE is_active=1")
    allergy_text = visit.get('allergy_history') or ''
    history_text = visit.get('past_history') or ''
    for rule in rules:
        if text_contains(medicine_name, rule.get('medicine_keyword')):
            allergy_keyword = rule.get('allergy_keyword')
            if not allergy_keyword or text_contains(allergy_text, allergy_keyword) or text_contains(history_text, allergy_keyword):
                warnings.append({
                    'severity': rule.get('severity'),
                    'message': rule.get('warning_message'),
                    'rule_name': rule.get('rule_name')
                })

    duplicates = query_db("""
        SELECT order_id, order_content, order_status
        FROM ed_order
        WHERE visit_id=%s
          AND order_status IN ('待执行','执行中')
        ORDER BY order_time DESC
    """, (visit_id,))
    for item in duplicates:
        if text_contains(item.get('order_content'), medicine_name) or text_contains(medicine_name, item.get('order_content')):
            warnings.append({
                'severity': 'warn',
                'message': f"存在重复在途医嘱：{item.get('order_content')}",
                'rule_name': '重复医嘱'
            })
            break

    blocked = any(w['severity'] == 'block' for w in warnings)
    return jsonify({
        'success': True,
        'blocked': blocked,
        'warnings': warnings,
        'patient_name': visit.get('patient_name'),
        'allergy_history': allergy_text
    })


@app.route('/api/dict/exam', methods=['GET'])
def get_exam_dict():
    """获取检查检验项目字典"""
    category = request.args.get('category')
    if category:
        items = query_db("SELECT * FROM sys_exam_dict WHERE exam_category = %s ORDER BY exam_code", (category,))
    else:
        items = query_db("SELECT * FROM sys_exam_dict ORDER BY exam_category, exam_code")
    return jsonify(items)


@app.route('/api/dict/staff', methods=['GET'])
def get_staff():
    """获取医护人员"""
    role = request.args.get('role')
    if role:
        staff = query_db("SELECT * FROM sys_staff WHERE role_type = %s AND is_active=1", (role,))
    else:
        staff = query_db("SELECT * FROM sys_staff WHERE is_active=1")
    return jsonify(staff)


@app.route('/api/dict/departments', methods=['GET'])
def get_departments():
    """获取科室字典。"""
    category = request.args.get('category')
    if category:
        depts = query_db("SELECT * FROM sys_department WHERE dept_category=%s ORDER BY sort_order, dept_id", (category,))
    else:
        depts = query_db("SELECT * FROM sys_department ORDER BY sort_order, dept_id")
    return jsonify(depts)


# ============================================================
# 统计报表
# ============================================================

@app.route('/api/stats/daily', methods=['GET'])
def daily_stats():
    """每日统计报表"""
    date_param = request.args.get('date')
    if not date_param:
        date_param = datetime.now().strftime('%Y-%m-%d')
    db = get_db()
    with db.cursor() as cursor:
        cursor.callproc('sp_daily_report', (date_param,))
        result = cursor.fetchall()
    return jsonify(result[0] if result else {})


@app.route('/api/stats/hourly', methods=['GET'])
def hourly_stats():
    """按小时统计"""
    date_param = request.args.get('date')
    if not date_param:
        date_param = datetime.now().strftime('%Y-%m-%d')
    data = query_db("""
        SELECT HOUR(visit_time) as hour, COUNT(*) as count,
               SUM(CASE WHEN triage_level <= 2 THEN 1 ELSE 0 END) as critical_count
        FROM ed_visit
        WHERE visit_date = %s
        GROUP BY HOUR(visit_time)
        ORDER BY hour
    """, (date_param,))
    return jsonify(data)


@app.route('/api/stats/diagnosis', methods=['GET'])
def diagnosis_stats():
    """诊断分布统计"""
    data = query_db("""
        SELECT icd_code, main_diagnosis, COUNT(*) as count
        FROM v_ed_visit_full
        WHERE visit_date = CURDATE() AND icd_code IS NOT NULL
        GROUP BY icd_code, main_diagnosis
        ORDER BY count DESC
        LIMIT 15
    """)
    return jsonify(data)


# ============================================================
# 绿色通道
# ============================================================

@app.route('/api/green-channel', methods=['GET'])
def get_green_channels():
    """获取活跃绿色通道"""
    channels = query_db("""
        SELECT gc.*, v.visit_no, p.patient_name, v.chief_complaint
        FROM ed_green_channel gc
        LEFT JOIN ed_visit v ON gc.visit_id = v.visit_id
        LEFT JOIN patient_info p ON v.patient_id = p.patient_id
        WHERE v.visit_status NOT IN ('已离院','已转院')
          AND (gc.channel_status = '进行中' OR gc.latest_event_time >= DATE_SUB(NOW(), INTERVAL 12 HOUR))
        ORDER BY gc.activate_time DESC
    """)
    return jsonify(channels)


# ============================================================
# 第二阶段: 会诊与留观
# ============================================================

@app.route('/api/green-channel', methods=['POST'])
def create_green_channel():
    data = request.json or {}
    visit_id = data.get('visit_id')
    channel_type = data.get('channel_type')
    if not visit_id or not channel_type:
        return jsonify({'success': False, 'message': '缺少 visit_id 或 channel_type'}), 400
    active = query_db(
        "SELECT channel_id FROM ed_green_channel WHERE visit_id=%s AND channel_status='进行中'",
        (visit_id,),
        one=True
    )
    if active:
        return jsonify({'success': True, 'channel_id': active['channel_id'], 'message': '该患者已有进行中的绿色通道'})
    try:
        activate_time = parse_datetime_input(data.get('activate_time')) or datetime.now()
        doctor_id = data.get('activate_doctor') or current_staff_id() or 1
        channel_id = execute_db(
            """
            INSERT INTO ed_green_channel (
                visit_id, channel_type, activate_time, activate_doctor,
                coordinator_nurse_id, latest_event_time, channel_status
            ) VALUES (%s, %s, %s, %s, %s, %s, '进行中')
            """,
            (
                visit_id,
                channel_type,
                activate_time,
                doctor_id,
                data.get('coordinator_nurse_id'),
                activate_time
            )
        )
        execute_db("UPDATE ed_visit SET is_green_channel=1 WHERE visit_id=%s", (visit_id,))
        execute_db(
            """
            INSERT INTO ed_green_channel_event (
                channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note
            ) VALUES (%s, %s, 'activate', %s, %s, 0, %s, %s)
            """,
            (
                channel_id,
                visit_id,
                f'{channel_type}绿色通道启动',
                activate_time,
                doctor_id,
                data.get('note')
            )
        )
        log_audit('GREEN_CHANNEL_CREATE', 'ed_green_channel', channel_id, {'visit_id': visit_id, 'channel_type': channel_type})
        return jsonify({'success': True, 'channel_id': channel_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/green-channel/dashboard', methods=['GET'])
def green_channel_dashboard():
    try:
        return jsonify({
            'summary': query_db("SELECT * FROM v_green_channel_dashboard", one=True) or {},
            'active': query_db("SELECT * FROM v_green_channel_active ORDER BY activate_time DESC LIMIT 20"),
            'all_channels': query_db(
                """
                SELECT
                    gc.channel_id, gc.visit_id, gc.channel_type, gc.activate_time, gc.activate_doctor,
                    gc.coordinator_nurse_id, gc.latest_event_time, gc.door_to_ecg, gc.door_to_needle,
                    gc.door_to_balloon, gc.door_to_ct, gc.door_to_surgery, gc.target_met,
                    gc.channel_outcome, gc.channel_status, gc.completed_time,
                    v.visit_no, v.triage_level, v.triage_color, v.chief_complaint,
                    p.patient_name, b.bed_code
                FROM ed_green_channel gc
                JOIN ed_visit v ON gc.visit_id = v.visit_id
                JOIN patient_info p ON v.patient_id = p.patient_id
                LEFT JOIN ed_bed b ON v.bed_id = b.bed_id
                ORDER BY CASE gc.channel_status WHEN '进行中' THEN 0 ELSE 1 END, gc.activate_time DESC
                LIMIT 30
                """
            )
        })
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/green-channel/<int:channel_id>/milestone', methods=['POST'])
def record_green_channel_milestone(channel_id):
    data = request.json or {}
    channel = query_db("SELECT * FROM ed_green_channel WHERE channel_id=%s", (channel_id,), one=True)
    if not channel:
        return jsonify({'success': False, 'message': '未找到绿色通道记录'}), 404
    event_type = data.get('event_type')
    if not event_type:
        return jsonify({'success': False, 'message': '缺少 event_type'}), 400
    try:
        event_time = parse_datetime_input(data.get('event_time')) or datetime.now()
        elapsed_seconds = max(0, int((event_time - channel['activate_time']).total_seconds()))
        event_name_map = {
            'ecg': '心电图完成',
            'ct': 'CT完成',
            'needle': '溶栓完成',
            'balloon': '球囊开通',
            'surgery': '手术开始',
            'handoff': '院内交接完成',
            'admission': '收入住院'
        }
        execute_db(
            """
            INSERT INTO ed_green_channel_event (
                channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                channel_id,
                channel['visit_id'],
                event_type,
                data.get('event_name') or event_name_map.get(event_type, event_type),
                event_time,
                elapsed_seconds,
                data.get('recorder_id') or current_staff_id(),
                data.get('note')
            )
        )
        metrics = {
            'door_to_ecg': channel.get('door_to_ecg'),
            'door_to_ct': channel.get('door_to_ct'),
            'door_to_needle': channel.get('door_to_needle'),
            'door_to_balloon': channel.get('door_to_balloon'),
            'door_to_surgery': channel.get('door_to_surgery')
        }
        updates = ["latest_event_time=%s"]
        params = [event_time]
        metric_column = green_metric_column(event_type)
        if metric_column:
            updates.append(f"{metric_column}=%s")
            params.append(elapsed_seconds)
            metrics[metric_column] = elapsed_seconds
        target_met = green_target_met(channel.get('channel_type'), metrics)
        if target_met is not None:
            updates.append("target_met=%s")
            params.append(target_met)
        params.append(channel_id)
        execute_db(f"UPDATE ed_green_channel SET {', '.join(updates)} WHERE channel_id=%s", tuple(params))
        log_audit('GREEN_CHANNEL_MILESTONE', 'ed_green_channel', channel_id, {'event_type': event_type, 'elapsed_seconds': elapsed_seconds})
        return jsonify({'success': True, 'elapsed_seconds': elapsed_seconds, 'target_met': target_met})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/green-channel/<int:channel_id>/complete', methods=['POST'])
def complete_green_channel(channel_id):
    data = request.json or {}
    channel = query_db("SELECT * FROM ed_green_channel WHERE channel_id=%s", (channel_id,), one=True)
    if not channel:
        return jsonify({'success': False, 'message': '未找到绿色通道记录'}), 404
    try:
        event_time = parse_datetime_input(data.get('completed_time')) or datetime.now()
        metrics = {
            'door_to_ecg': channel.get('door_to_ecg'),
            'door_to_ct': channel.get('door_to_ct'),
            'door_to_needle': channel.get('door_to_needle'),
            'door_to_balloon': channel.get('door_to_balloon'),
            'door_to_surgery': channel.get('door_to_surgery')
        }
        target_met = green_target_met(channel.get('channel_type'), metrics)
        execute_db(
            """
            UPDATE ed_green_channel
            SET channel_status='已完成',
                completed_time=%s,
                latest_event_time=%s,
                channel_outcome=%s,
                target_met=%s
            WHERE channel_id=%s
            """,
            (
                event_time,
                event_time,
                data.get('channel_outcome') or channel.get('channel_outcome') or '完成院内交接',
                target_met,
                channel_id
            )
        )
        execute_db(
            """
            INSERT INTO ed_green_channel_event (
                channel_id, visit_id, event_type, event_name, event_time, elapsed_seconds, recorder_id, note
            ) VALUES (%s, %s, 'close', '绿色通道关闭', %s, %s, %s, %s)
            """,
            (
                channel_id,
                channel['visit_id'],
                event_time,
                max(0, int((event_time - channel['activate_time']).total_seconds())),
                data.get('recorder_id') or current_staff_id(),
                data.get('note')
            )
        )
        log_audit('GREEN_CHANNEL_COMPLETE', 'ed_green_channel', channel_id, {'target_met': target_met})
        return jsonify({'success': True, 'target_met': target_met})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/rescue/worklist', methods=['GET'])
def get_rescue_worklist():
    status = request.args.get('status')
    sql = "SELECT * FROM v_rescue_worklist WHERE 1=1"
    args = []
    if status:
        sql += " AND rescue_status=%s"
        args.append(status)
    sql += " ORDER BY CASE rescue_status WHEN '抢救中' THEN 0 ELSE 1 END, rescue_start DESC"
    try:
        return jsonify(query_db(sql, args if args else None))
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/rescue/<int:rescue_id>', methods=['GET'])
def get_rescue_detail(rescue_id):
    try:
        rescue = query_db("SELECT * FROM v_rescue_worklist WHERE rescue_id=%s", (rescue_id,), one=True)
        if not rescue:
            return jsonify({'success': False, 'message': '未找到抢救记录'}), 404
        timeline = query_db(
            """
            SELECT t.*, s.staff_name AS performer_name
            FROM ed_rescue_timeline t
            LEFT JOIN sys_staff s ON t.performer_id = s.staff_id
            WHERE t.rescue_id=%s
            ORDER BY t.event_time ASC, t.timeline_id ASC
            """,
            (rescue_id,)
        )
        return jsonify({'success': True, 'rescue': rescue, 'timeline': timeline})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/rescue/start', methods=['POST'])
def start_rescue():
    data = request.json or {}
    visit_id = data.get('visit_id')
    if not visit_id:
        return jsonify({'success': False, 'message': '缺少 visit_id'}), 400
    active = query_db(
        "SELECT rescue_id FROM ed_rescue_record WHERE visit_id=%s AND rescue_status='抢救中'",
        (visit_id,),
        one=True
    )
    if active:
        return jsonify({'success': True, 'rescue_id': active['rescue_id'], 'message': '该患者已有进行中的抢救记录'})
    try:
        rescue_start = parse_datetime_input(data.get('rescue_start')) or datetime.now()
        rescue_leader = data.get('rescue_leader') or current_staff_id() or 1
        rescue_id = execute_db(
            """
            INSERT INTO ed_rescue_record (
                visit_id, rescue_start, rescue_leader, rescue_team, arrest_type,
                cpr_flag, cpr_start, airway_type, rescue_status, latest_event_time, rescue_summary
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '抢救中', %s, %s)
            """,
            (
                visit_id,
                rescue_start,
                rescue_leader,
                json_text(data.get('rescue_team')),
                data.get('arrest_type'),
                1 if data.get('cpr_flag') else 0,
                rescue_start if data.get('cpr_flag') else None,
                data.get('airway_type'),
                rescue_start,
                data.get('rescue_summary')
            )
        )
        execute_db(
            """
            INSERT INTO ed_rescue_timeline (
                rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
            ) VALUES (%s, %s, %s, 'start', '抢救启动', %s, %s)
            """,
            (rescue_id, visit_id, rescue_start, rescue_leader, data.get('rescue_summary'))
        )
        if data.get('cpr_flag'):
            execute_db(
                """
                INSERT INTO ed_rescue_timeline (
                    rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
                ) VALUES (%s, %s, %s, 'cpr', 'CPR开始', %s, %s)
                """,
                (rescue_id, visit_id, rescue_start, rescue_leader, '启动心肺复苏')
            )
        execute_db("UPDATE ed_visit SET visit_status='处置中' WHERE visit_id=%s", (visit_id,))
        log_audit('RESCUE_START', 'ed_rescue_record', rescue_id, {'visit_id': visit_id})
        return jsonify({'success': True, 'rescue_id': rescue_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/rescue/<int:rescue_id>/events', methods=['POST'])
def add_rescue_event(rescue_id):
    data = request.json or {}
    rescue = query_db("SELECT * FROM ed_rescue_record WHERE rescue_id=%s", (rescue_id,), one=True)
    if not rescue:
        return jsonify({'success': False, 'message': '未找到抢救记录'}), 404
    event_type = data.get('event_type')
    if not event_type:
        return jsonify({'success': False, 'message': '缺少 event_type'}), 400
    try:
        event_time = parse_datetime_input(data.get('event_time')) or datetime.now()
        execute_db(
            """
            INSERT INTO ed_rescue_timeline (
                rescue_id, visit_id, event_time, event_type, event_name, performer_id,
                medication_name, dose, route, note, vital_snapshot
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                rescue_id,
                rescue['visit_id'],
                event_time,
                event_type,
                data.get('event_name') or event_type,
                data.get('performer_id') or current_staff_id(),
                data.get('medication_name'),
                data.get('dose'),
                data.get('route'),
                data.get('note'),
                json_text(data.get('vital_snapshot'))
            )
        )
        updates = ["latest_event_time=%s"]
        params = [event_time]
        if event_type == 'cpr' and not rescue.get('cpr_start'):
            updates.extend(["cpr_flag=1", "cpr_start=%s"])
            params.append(event_time)
        if event_type == 'rosc':
            updates.append("rosc_time=%s")
            params.append(event_time)
        params.append(rescue_id)
        execute_db(f"UPDATE ed_rescue_record SET {', '.join(updates)} WHERE rescue_id=%s", tuple(params))
        log_audit('RESCUE_EVENT_ADD', 'ed_rescue_record', rescue_id, {'event_type': event_type})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/rescue/<int:rescue_id>/complete', methods=['POST'])
def complete_rescue(rescue_id):
    data = request.json or {}
    rescue = query_db("SELECT * FROM ed_rescue_record WHERE rescue_id=%s", (rescue_id,), one=True)
    if not rescue:
        return jsonify({'success': False, 'message': '未找到抢救记录'}), 404
    try:
        event_time = parse_datetime_input(data.get('rescue_end')) or datetime.now()
        outcome = data.get('outcome') or rescue.get('outcome') or '成功'
        execute_db(
            """
            UPDATE ed_rescue_record
            SET rescue_end=%s,
                rescue_duration=TIMESTAMPDIFF(MINUTE, rescue_start, %s),
                outcome=%s,
                rescue_status='已完成',
                latest_event_time=%s,
                rescue_summary=%s
            WHERE rescue_id=%s
            """,
            (
                event_time,
                event_time,
                outcome,
                event_time,
                data.get('rescue_summary') or rescue.get('rescue_summary'),
                rescue_id
            )
        )
        execute_db(
            """
            INSERT INTO ed_rescue_timeline (
                rescue_id, visit_id, event_time, event_type, event_name, performer_id, note
            ) VALUES (%s, %s, %s, 'end', '抢救结束', %s, %s)
            """,
            (rescue_id, rescue['visit_id'], event_time, data.get('performer_id') or current_staff_id(), data.get('note'))
        )
        if outcome == '死亡':
            execute_db(
                "UPDATE ed_visit SET visit_status='死亡', outcome='死亡', outcome_time=%s WHERE visit_id=%s",
                (event_time, rescue['visit_id'])
            )
        else:
            execute_db(
                """
                UPDATE ed_visit
                SET visit_status=CASE WHEN visit_status='处置中' THEN '就诊中' ELSE visit_status END
                WHERE visit_id=%s
                """,
                (rescue['visit_id'],)
            )
        log_audit('RESCUE_COMPLETE', 'ed_rescue_record', rescue_id, {'outcome': outcome})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/quality/dashboard', methods=['GET'])
def get_quality_dashboard():
    try:
        quality_row = query_db("SELECT * FROM v_quality_dashboard", one=True) or {}
        green_row = query_db("SELECT * FROM v_green_channel_dashboard", one=True) or {}
        data_scale = query_db("SELECT * FROM v_demo_data_scale", one=True) or {}
        indicators = query_db(
            """
            SELECT indicator_date, indicator_name, indicator_value, indicator_unit, target_value, is_met
            FROM ed_quality_indicator
            ORDER BY indicator_date DESC, indicator_id DESC
            LIMIT 20
            """
        )
        return jsonify({
            'summary': quality_row,
            'green_summary': green_row,
            'data_scale': data_scale,
            'snapshot_preview': [
                {
                    'indicator_name': name,
                    'indicator_value': value,
                    'indicator_unit': unit,
                    'target_value': target
                }
                for name, value, unit, target in build_quality_snapshot_items(quality_row, green_row)
            ],
            'recent_indicators': indicators,
            'rescue': query_db("SELECT * FROM v_rescue_worklist ORDER BY CASE rescue_status WHEN '抢救中' THEN 0 ELSE 1 END, rescue_start DESC LIMIT 8"),
            'green_channels': query_db("SELECT * FROM v_green_channel_active ORDER BY activate_time DESC LIMIT 8")
        })
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/quality/refresh', methods=['POST'])
def refresh_quality_snapshot():
    try:
        count = refresh_quality_indicator_snapshot(staff_id=current_staff_id())
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/demo/summary', methods=['GET'])
def get_demo_summary():
    try:
        return jsonify(query_db("SELECT * FROM v_demo_data_scale", one=True) or {})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/consultations', methods=['GET'])
def get_consultations():
    status = request.args.get('status')
    sql = """
        SELECT c.*, p.patient_name, v.visit_no, v.triage_level,
               d.dept_name AS requested_dept_name,
               req.staff_name AS request_doctor_name,
               rsp.staff_name AS responder_name
        FROM ed_consultation c
        JOIN ed_visit v ON c.visit_id = v.visit_id
        JOIN patient_info p ON v.patient_id = p.patient_id
        LEFT JOIN sys_department d ON c.requested_dept_id = d.dept_id
        LEFT JOIN sys_staff req ON c.request_doctor_id = req.staff_id
        LEFT JOIN sys_staff rsp ON c.responder_id = rsp.staff_id
        WHERE 1=1
    """
    args = []
    if status:
        sql += " AND c.consult_status = %s"
        args.append(status)
    sql += " ORDER BY CASE c.urgency_level WHEN '紧急' THEN 1 WHEN '加急' THEN 2 ELSE 3 END, c.request_time DESC"
    return jsonify(query_db(sql, args if args else None))


@app.route('/api/consultations', methods=['POST'])
def create_consultation():
    data = request.json or {}
    try:
        consult_id = execute_db("""
            INSERT INTO ed_consultation (
                visit_id, request_time, request_doctor_id, requested_dept_id, requested_staff_id,
                consult_reason, urgency_level, consult_status
            ) VALUES (%s, NOW(), %s, %s, %s, %s, %s, '待响应')
        """, (
            data.get('visit_id'),
            data.get('request_doctor_id') or current_staff_id() or 1,
            data.get('requested_dept_id'),
            data.get('requested_staff_id'),
            data.get('consult_reason'),
            data.get('urgency_level', '普通')
        ))
        log_audit('CONSULT_CREATE', 'ed_consultation', consult_id, {'visit_id': data.get('visit_id')})
        return jsonify({'success': True, 'consult_id': consult_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/consultations/<int:consult_id>/reply', methods=['POST'])
def reply_consultation(consult_id):
    data = request.json or {}
    try:
        execute_db("""
            UPDATE ed_consultation
            SET consult_status='已完成', response_time=COALESCE(response_time, NOW()),
                responder_id=%s, consult_opinion=%s, advice_plan=%s, completed_time=NOW()
            WHERE consult_id=%s
        """, (
            data.get('responder_id') or current_staff_id(),
            data.get('consult_opinion'),
            data.get('advice_plan'),
            consult_id
        ))
        log_audit('CONSULT_REPLY', 'ed_consultation', consult_id, {'responder_id': data.get('responder_id') or current_staff_id()})
        return jsonify({'success': True})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/observation/active', methods=['GET'])
def get_active_observation():
    return jsonify(query_db("SELECT * FROM v_observation_active ORDER BY obs_start ASC"))


@app.route('/api/observation/start', methods=['POST'])
def start_observation():
    data = request.json or {}
    visit_id = data.get('visit_id')
    if not visit_id:
        return jsonify({'success': False, 'message': '缺少 visit_id'}), 400
    try:
        obs_id = execute_db("""
            INSERT INTO ed_observation (
                visit_id, bed_id, responsible_doctor_id, obs_start, obs_reason, obs_status
            ) VALUES (%s, %s, %s, NOW(), %s, '观察中')
        """, (
            visit_id,
            data.get('bed_id'),
            data.get('responsible_doctor_id') or current_staff_id(),
            data.get('obs_reason')
        ))
        execute_db("""
            UPDATE ed_visit
            SET visit_status='观察中', bed_id=COALESCE(%s, bed_id)
            WHERE visit_id=%s
        """, (data.get('bed_id'), visit_id))
        log_audit('OBS_START', 'ed_observation', obs_id, {'visit_id': visit_id})
        return jsonify({'success': True, 'obs_id': obs_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/observation/<int:obs_id>/reassess', methods=['POST'])
def reassess_observation(obs_id):
    data = request.json or {}
    obs = query_db("SELECT visit_id FROM ed_observation WHERE obs_id=%s", (obs_id,), one=True)
    if not obs:
        return jsonify({'success': False, 'message': '未找到留观记录'}), 404
    try:
        reassess_id = execute_db("""
            INSERT INTO ed_observation_reassess (
                obs_id, visit_id, reassess_time, doctor_id, vitals_json, assessment, plan, next_reassess_time
            ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s)
        """, (
            obs_id, obs['visit_id'],
            data.get('doctor_id') or current_staff_id() or 1,
            json.dumps(data.get('vitals_json'), ensure_ascii=False) if data.get('vitals_json') else None,
            data.get('assessment'),
            data.get('plan'),
            data.get('next_reassess_time')
        ))
        execute_db("""
            UPDATE ed_observation
            SET reassess_count = reassess_count + 1,
                latest_reassess_time = NOW()
            WHERE obs_id=%s
        """, (obs_id,))
        log_audit('OBS_REASSESS', 'ed_observation_reassess', reassess_id, {'obs_id': obs_id})
        return jsonify({'success': True, 'reassess_id': reassess_id})
    except Exception as e:
        return missing_upgrade_response(e)


@app.route('/api/observation/<int:obs_id>/complete', methods=['POST'])
def complete_observation(obs_id):
    data = request.json or {}
    obs = query_db("SELECT * FROM ed_observation WHERE obs_id=%s", (obs_id,), one=True)
    if not obs:
        return jsonify({'success': False, 'message': '未找到留观记录'}), 404
    outcome = data.get('outcome', '离院')
    try:
        execute_db("""
            UPDATE ed_observation
            SET obs_end=NOW(),
                obs_duration=TIMESTAMPDIFF(HOUR, obs_start, NOW()),
                outcome=%s, dest_dept=%s, dest_ward=%s,
                obs_status=%s
            WHERE obs_id=%s
        """, (
            outcome, data.get('dest_dept'), data.get('dest_ward'),
            '待入院' if outcome == '住院' else '已完成',
            obs_id
        ))
        if obs.get('bed_id'):
            execute_db("UPDATE ed_bed SET bed_status='清洁中', current_visit_id=NULL WHERE bed_id=%s", (obs.get('bed_id'),))
        if outcome == '住院':
            execute_db("""
                UPDATE ed_visit
                SET visit_status='待入院', outcome='住院', outcome_time=NOW()
                WHERE visit_id=%s
            """, (obs['visit_id'],))
            transfer_id = execute_db("""
                INSERT INTO ed_transfer_request (
                    visit_id, request_type, request_time, request_doctor_id,
                    target_dept, target_ward, bed_request_note, transfer_status
                ) VALUES (%s, '住院', NOW(), %s, %s, %s, %s, '待响应')
            """, (
                obs['visit_id'],
                data.get('request_doctor_id') or current_staff_id() or 1,
                data.get('dest_dept'),
                data.get('dest_ward'),
                data.get('bed_request_note')
            ))
        elif outcome == '转院':
            execute_db("""
                UPDATE ed_visit
                SET visit_status='已转院', outcome='转院', outcome_time=NOW()
                WHERE visit_id=%s
            """, (obs['visit_id'],))
            transfer_id = execute_db("""
                INSERT INTO ed_transfer_request (
                    visit_id, request_type, request_time, request_doctor_id,
                    target_dept, target_ward, bed_request_note, transfer_status
                ) VALUES (%s, '转院', NOW(), %s, %s, %s, %s, '待响应')
            """, (
                obs['visit_id'],
                data.get('request_doctor_id') or current_staff_id() or 1,
                data.get('dest_dept'),
                data.get('dest_ward'),
                data.get('bed_request_note')
            ))
        else:
            execute_db("""
                UPDATE ed_visit
                SET visit_status='已离院', outcome='离院回家', outcome_time=NOW()
                WHERE visit_id=%s
            """, (obs['visit_id'],))
            transfer_id = None
        log_audit('OBS_COMPLETE', 'ed_observation', obs_id, {'outcome': outcome, 'transfer_id': transfer_id})
        return jsonify({'success': True, 'transfer_id': transfer_id})
    except Exception as e:
        return missing_upgrade_response(e)


# ============================================================
# 医师分配
# ============================================================

@app.route('/api/visits/<int:visit_id>/assign-doctor', methods=['POST'])
def assign_doctor(visit_id):
    """分配主治医生"""
    data = request.json
    doctor_id = data.get('doctor_id')
    if not doctor_id:
        return jsonify({'success': False, 'message': '请指定医生ID'}), 400
    try:
        execute_db("""
            UPDATE ed_visit SET attending_doctor_id = %s,
                visit_status = CASE WHEN visit_status = '分诊中' THEN '候诊' ELSE visit_status END
            WHERE visit_id = %s
        """, (doctor_id, visit_id))
        return jsonify({'success': True, 'message': '医生分配成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# 静态文件服务 - 前端页面
@app.route('/')
def index():
    from flask import send_from_directory
    web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web'))
    return send_from_directory(web_dir, 'index.html')


@app.route('/test')
def test_page():
    from flask import send_from_directory
    web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web'))
    return send_from_directory(web_dir, 'test.html')


if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
