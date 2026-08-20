import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re

from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote


# =========================================================
# CONFIG
# =========================================================

DB_FILE = "attendance_platform.db"

GROUPS = [
    "المجموعة 1",
    "المجموعة 2",
]

GROUP_LIMIT = 70

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

DEFAULT_TEACHER_PASSWORD = "1234"


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
)


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1200px;
        padding-top: 25px;
        padding-bottom: 50px;
    }

    .main-title {
        text-align: center;
        font-size: 44px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 22px;
        margin-bottom: 25px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA busy_timeout=30000"
    )

    conn.execute(
        "PRAGMA foreign_keys=ON"
    )

    return conn


def init_db():

    conn = db()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                parent_phone TEXT DEFAULT '',
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_name TEXT NOT NULL,
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                active INTEGER DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                UNIQUE(lesson_id, student_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TEXT NOT NULL,
                UNIQUE(lesson_id, student_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = 'teacher_password'
            """
        ).fetchone()

        if row is None:

            conn.execute(
                """
                INSERT INTO settings
                (key, value)
                VALUES (?, ?)
                """,
                (
                    "teacher_password",
                    DEFAULT_TEACHER_PASSWORD,
                ),
            )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# BASIC
# =========================================================

def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def clean_phone(phone):

    return re.sub(
        r"\D",
        "",
        phone or "",
    )


def header(title, subtitle):

    st.markdown(
        f"""
        <div class="main-title">
            {title}
        </div>

        <div class="sub-title">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# TEACHER PASSWORD
# =========================================================

def get_teacher_password():

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = 'teacher_password'
            """
        ).fetchone()

        if row:
            return row["value"]

        return DEFAULT_TEACHER_PASSWORD

    finally:

        conn.close()


def set_teacher_password(password):

    conn = db()

    try:

        conn.execute(
            """
            INSERT INTO settings
            (key, value)
            VALUES (?, ?)

            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (
                "teacher_password",
                password,
            ),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()

        return False

    finally:

        conn.close()


# =========================================================
# STUDENTS
# =========================================================

def get_student(student_id):

    if not student_id:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()

    finally:

        conn.close()


def get_student_by_phone(phone):

    phone = clean_phone(phone)

    if not phone:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

    finally:

        conn.close()


def get_student_id():

    sid = st.session_state.get(
        "student_id"
    )

    if sid is None:

        sid = st.query_params.get(
            "student"
        )

    try:

        sid = int(sid)

    except (
        TypeError,
        ValueError,
    ):

        return None

    if get_student(sid):

        st.session_state.student_id = sid

        return sid

    return None


# =========================================================
# URL
# =========================================================

def get_base_url():

    try:

        current = st.context.url

        if current:

            parsed = urlparse(current)

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    except Exception:

        pass

    return ""


def lesson_url(token):

    base = get_base_url()

    if base:

        return (
            f"{base}"
            f"?page=student"
            f"&lesson={token}"
        )

    return (
        f"?page=student"
        f"&lesson={token}"
    )


def extract_token(value):

    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    if (
        "://" not in value
        and "lesson=" not in value
    ):

        return value

    try:

        result = parse_qs(
            urlparse(value).query
        ).get("lesson")

        if result:

            return unquote(
                result[0]
            ).strip()

    except Exception:

        pass

    match = re.search(
        r"lesson=([^&#\s]+)",
        value,
    )

    if match:

        return unquote(
            match.group(1)
        ).strip()

    return None


# =========================================================
# GROUPS
# =========================================================

def group_count(grade, group):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()[0]

    finally:

        conn.close()


# =========================================================
# LESSONS
# =========================================================

def get_lesson_by_token(token):

    if not token:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

    finally:

        conn.close()


def get_active_lessons():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()


# =========================================================
# QR
# =========================================================

def decode_qr(image_bytes):

    try:

        data = np.frombuffer(
            image_bytes,
            dtype=np.uint8,
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR,
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        h, w = gray.shape[:2]

        attempts = [
            image,
            gray,
            cv2.resize(
                gray,
                (
                    max(1, w * 2),
                    max(1, h * 2),
                ),
                interpolation=cv2.INTER_CUBIC,
            ),
        ]

        for img in attempts:

            try:

                value, _, _ = (
                    detector.detectAndDecode(img)
                )

                if value:

                    return value.strip()

            except Exception:

                pass

    except Exception:

        pass

    return None


# =========================================================
# ATTENDANCE
# =========================================================

def mark_attendance(token, student_id):

    token = extract_token(token)

    lesson = get_lesson_by_token(token)

    if not lesson:

        return (
            False,
            "❌ الحصة غير موجودة أو انتهت.",
        )

    student = get_student(student_id)

    if not student:

        return (
            False,
            "❌ الطالب غير موجود.",
        )

    if (
        student["grade"] != lesson["grade"]
        or student["group_name"]
        != lesson["group_name"]
    ):

        return (
            False,
            (
                "❌ لا يمكنك تسجيل الحضور في هذه الحصة.\n\n"
                f"📚 الحصة: "
                f"{lesson['grade']} - "
                f"{lesson['group_name']}\n\n"
                f"👨‍🎓 حسابك: "
                f"{student['grade']} - "
                f"{student['group_name']}"
            ),
        )

    conn = db()

    try:

        existing = conn.execute(
            """
            SELECT marked_at
            FROM attendance
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if existing:

            return (
                True,
                (
                    "✅ حضورك مسجل بالفعل.\n\n"
                    f"🕐 {existing['marked_at']}"
                ),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO lesson_students
            (lesson_id, student_id)
            VALUES (?, ?)
            """,
            (
                lesson["id"],
                student_id,
            ),
        )

        stamp = now()

        conn.execute(
            """
            INSERT INTO attendance
            (lesson_id, student_id, marked_at)
            VALUES (?, ?, ?)
            """,
            (
                lesson["id"],
                student_id,
                stamp,
            ),
        )

        conn.commit()

        return (
            True,
            (
                "🎉 تم تسجيل حضورك بنجاح.\n\n"
                f"🕐 {stamp}"
            ),
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except Exception as exc:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ: {exc}",
        )

    finally:

        conn.close()


# =========================================================
# STUDENT REGISTER
# =========================================================

def student_register():

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    st.info(
        "👋 سجل بياناتك مرة واحدة فقط."
    )

    with st.form(
        "student_register_form"
    ):

        name = st.text_input(
            "👨‍🎓 اسم الطالب"
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "👪 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES,
        )

        group = st.selectbox(
            "👥 المجموعة",
            GROUPS,
        )

        st.info(
            f"{group}: "
            f"{group_count(grade, group)}"
            f"/{GROUP_LIMIT}"
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submit:
        return

    name = name.strip()
    phone = clean_phone(phone)
    parent_phone = clean_phone(parent_phone)

    if not name:

        st.error(
            "❌ اكتب اسم الطالب."
        )

        return

    if len(phone) < 8:

        st.error(
            "❌ رقم الهاتف غير صحيح."
        )

        return

    conn = db()

    try:

        old = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

        if old:

            st.session_state.student_id = old["id"]

            st.query_params["page"] = "student"

            st.query_params["student"] = str(
                old["id"]
            )

            st.rerun()

            return

        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()[0]

        if count >= GROUP_LIMIT:

            st.error(
                "❌ هذه المجموعة مكتملة."
            )

            return

        cursor = conn.execute(
            """
            INSERT INTO students
            (
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                parent_phone,
                grade,
                group,
                now(),
            ),
        )

        conn.commit()

        sid = cursor.lastrowid

        st.session_state.student_id = sid

        st.query_params["page"] = "student"

        st.query_params["student"] = str(
            sid
        )

        st.rerun()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    except Exception as exc:

        conn.rollback()

        st.error(
            f"❌ حدث خطأ: {exc}"
        )

    finally:

        conn.close()


# =========================================================
# STUDENT LOGIN
# =========================================================

def student_login():

    header(
        "🎓 منصة الحضور",
        "🔐 دخول الطالب",
    )

    with st.form(
        "student_login_form"
    ):

        phone = st.text_input(
            "📱 رقم الهاتف"
        )

        submit = st.form_submit_button(
            "🔓 دخول",
            use_container_width=True,
        )

    if not submit:
        return

    phone = clean_phone(phone)

    if len(phone) < 8:

        st.error(
            "❌ رقم الهاتف غير صحيح."
        )

        return

    student = get_student_by_phone(phone)

    if not student:

        st.error(
            "❌ لا يوجد حساب بهذا الرقم."
        )

        return

    st.session_state.student_id = student["id"]

    st.query_params["page"] = "student"

    st.query_params["student"] = str(
        student["id"]
    )

    st.rerun()


# =========================================================
# STUDENT STATS
# =========================================================

def student_stats(student_id):

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM lesson_students ls
            JOIN lessons l
            ON l.id = ls.lesson_id
            WHERE ls.student_id = ?
            AND l.active = 0
            """,
            (student_id,),
        ).fetchone()[0]

        present = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance a
            JOIN lessons l
            ON l.id = a.lesson_id
            WHERE a.student_id = ?
            AND l.active = 0
            """,
            (student_id,),
        ).fetchone()[0]

        absent = total - present

        percentage = (
            present / total * 100
            if total
            else 0
        )

        return (
            total,
            present,
            absent,
            percentage,
        )

    finally:

        conn.close()


def get_student_history(student_id):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT
                l.lesson_name,
                l.grade,
                l.group_name,
                l.created_at,
                a.marked_at
            FROM lesson_students ls
            JOIN lessons l
            ON l.id = ls.lesson_id
            LEFT JOIN attendance a
            ON a.lesson_id = l.id
            AND a.student_id = ls.student_id
            WHERE ls.student_id = ?
            AND l.active = 0
            ORDER BY l.id DESC
            """,
            (student_id,),
        ).fetchall()

    finally:

        conn.close()


# =========================================================
# STUDENT PROFILE
# =========================================================

def student_profile(student):

    st.subheader(
        "👤 بيانات الطالب"
    )

    c1, c2 = st.columns(2)

    with c1:

        st.write(
            f"**👨‍🎓 الاسم:** {student['name']}"
        )

        st.write(
            f"**🎓 الصف:** {student['grade']}"
        )

    with c2:

        st.write(
            f"**👥 المجموعة:** "
            f"{student['group_name']}"
        )

        st.write(
            f"**📱 الهاتف:** {student['phone']}"
        )

    st.divider()

    (
        total,
        present,
        absent,
        percentage,
    ) = student_stats(student["id"])

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "📚 الحصص",
        total,
    )

    c2.metric(
        "✅ الحضور",
        present,
    )

    c3.metric(
        "❌ الغياب",
        absent,
    )

    c4.metric(
        "📈 النسبة",
        f"{percentage:.1f}%",
    )


# =========================================================
# STUDENT HISTORY
# =========================================================

def student_history(student):

    st.subheader(
        "📋 سجل الحضور والغياب"
    )

    rows = get_student_history(
        student["id"]
    )

    if not rows:

        st.info(
            "📭 لا توجد حصص منتهية."
        )

        return

    table = []

    for row in rows:

        table.append(
            {
                "الحصة": row["lesson_name"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "التاريخ": row["created_at"],
                "الحالة": (
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب"
                ),
                "وقت الحضور": (
                    row["marked_at"]
                    or "-"
                ),
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENT ATTENDANCE
# =========================================================

def student_attendance(student):

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.info(
        "📱 امسح QR الموجود عند المدرس."
    )

    photo = st.camera_input(
        "📷 كاميرا QR",
        key="student_camera",
    )

    if photo:

        raw = decode_qr(
            photo.getvalue()
        )

        if not raw:

            st.error(
                "❌ لم يتم قراءة QR."
            )

        else:

            ok, message = mark_attendance(
                raw,
                student["id"],
            )

            if ok:

                st.success(message)

                st.balloons()

            else:

                st.error(message)

    st.divider()

    st.subheader(
        "🔗 الحضور بالرابط"
    )

    manual = st.text_input(
        "الصق رابط الحصة",
        key="manual_link",
    )

    if st.button(
        "✅ تسجيل الحضور",
        use_container_width=True,
        key="manual_attendance",
    ):

        token = extract_token(manual)

        if not token:

            st.error(
                "❌ الرابط غير صحيح."
            )

        else:

            ok, message = mark_attendance(
                token,
                student["id"],
            )

            if ok:

                st.success(message)

            else:

                st.error(message)


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    sid = get_student_id()

    if sid is None:

        login, register = st.tabs(
            [
                "🔐 دخول",
                "📝 تسجيل",
            ]
        )

        with login:
            student_login()

        with register:
            student_register()

        return

    student = get_student(sid)

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

        return

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    st.success(
        f"""
👨‍🎓 {student['name']}

🎓 {student['grade']}

👥 {student['group_name']}
        """
    )

    t1, t2, t3 = st.tabs(
        [
            "📷 الحضور",
            "👤 حسابي",
            "📋 سجلي",
        ]
    )

    with t1:
        student_attendance(student)

    with t2:
        student_profile(student)

    with t3:
        student_history(student)

    st.divider()

    if st.button(
        "🚪 تسجيل خروج",
        use_container_width=True,
        key="student_logout",
    ):

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة المدرس",
    )

    password = st.text_input(
        "🔐 كلمة المرور",
        type="password",
        key="teacher_login_password",
    )

    if st.button(
        "👨‍🏫 دخول المدرس",
        use_container_width=True,
    ):

        if password == get_teacher_password():

            st.session_state.teacher = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# CHANGE PASSWORD
# =========================================================

def change_password():

    st.subheader(
        "🔐 تغيير كلمة مرور المدرس"
    )

    with st.form(
        "password_form"
    ):

        old = st.text_input(
            "🔑 كلمة المرور الحالية",
            type="password",
        )

        new = st.text_input(
            "🆕 كلمة المرور الجديدة",
            type="password",
        )

        confirm = st.text_input(
            "🔁 تأكيد كلمة المرور",
            type="password",
        )

        save = st.form_submit_button(
            "💾 حفظ",
            use_container_width=True,
        )

    if not save:
        return

    if old != get_teacher_password():

        st.error(
            "❌ كلمة المرور الحالية غير صحيحة."
        )

        return

    if len(new) < 4:

        st.error(
            "❌ كلمة المرور يجب أن تكون 4 أحرف أو أرقام على الأقل."
        )

        return

    if new != confirm:

        st.error(
            "❌ كلمتا المرور غير متطابقتين."
        )

        return

    if set_teacher_password(new):

        st.success(
            "✅ تم تغيير كلمة المرور."
        )

    else:

        st.error(
            "❌ حدث خطأ أثناء الحفظ."
        )


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="create_grade",
    )

    c1, c2 = st.columns(2)

    for i, group in enumerate(GROUPS):

        count = group_count(
            grade,
            group,
        )

        if i == 0:

            c1.metric(
                group,
                f"{count}/{GROUP_LIMIT}",
            )

        else:

            c2.metric(
                group,
                f"{count}/{GROUP_LIMIT}",
            )

    group = st.selectbox(
        "👥 المجموعة",
        GROUPS,
        key="create_group",
    )

    count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 الطلاب: {count}/{GROUP_LIMIT}"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="create_lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
        key="start_lesson",
    ):

        if count == 0:

            st.error(
                "❌ لا يوجد طلاب في هذه المجموعة."
            )

            return

        conn = db()

        try:

            conn.execute(
                """
                UPDATE lessons
                SET active = 0,
                    ended_at = ?
                WHERE active = 1
                AND grade = ?
                AND group_name = ?
                """,
                (
                    now(),
                    grade,
                    group,
                ),
            )

            token = secrets.token_urlsafe(32)

            cursor = conn.execute(
                """
                INSERT INTO lessons
                (
                    lesson_name,
                    grade,
                    group_name,
                    token,
                    created_at,
                    active
                )
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    lesson_name.strip()
                    or "الحصة الحالية",
                    grade,
                    group,
                    token,
                    now(),
                ),
            )

            lesson_id = cursor.lastrowid

            students_rows = conn.execute(
                """
                SELECT id
                FROM students
                WHERE grade = ?
                AND group_name = ?
                """,
                (
                    grade,
                    group,
                ),
            ).fetchall()

            conn.executemany(
                """
                INSERT OR IGNORE INTO lesson_students
                (lesson_id, student_id)
                VALUES (?, ?)
                """,
                [
                    (
                        lesson_id,
                        row["id"],
                    )
                    for row in students_rows
                ],
            )

            conn.commit()

            st.success(
                "🎉 تم بدء الحصة."
            )

            st.rerun()

        except Exception as exc:

            conn.rollback()

            st.error(
                f"❌ {exc}"
            )

        finally:

            conn.close()


# =========================================================
# CURRENT LESSONS
# =========================================================

def current_lessons():

    st.subheader(
        "📊 الحصص الحالية"
    )

    lessons = get_active_lessons()

    if not lessons:

        st.info(
            "⏳ لا توجد حصص مفتوحة."
        )

        return

    labels = [
        (
            f"#{x['id']} | "
            f"{x['grade']} | "
            f"{x['group_name']} | "
            f"{x['lesson_name']}"
        )
        for x in lessons
    ]

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="current_lesson",
    )

    lesson = lessons[
        labels.index(selected)
    ]

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson["id"],),
        ).fetchone()[0]

        present = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE lesson_id = ?
            """,
            (lesson["id"],),
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT
                s.name,
                s.phone,
                a.marked_at
            FROM lesson_students ls
            JOIN students s
            ON s.id = ls.student_id
            LEFT JOIN attendance a
            ON a.lesson_id = ls.lesson_id
            AND a.student_id = ls.student_id
            WHERE ls.lesson_id = ?
            ORDER BY s.name
            """,
            (lesson["id"],),
        ).fetchall()

    finally:

        conn.close()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total,
    )

    c2.metric(
        "✅ الحضور",
        present,
    )

    c3.metric(
        "⏳ لم يسجل",
        total - present,
    )

    st.write(
        f"🎓 الصف: **{lesson['grade']}**"
    )

    st.write(
        f"👥 المجموعة: **{lesson['group_name']}**"
    )

    st.write(
        f"📚 الحصة: **{lesson['lesson_name']}**"
    )

    link = lesson_url(
        lesson["token"]
    )

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=5,
    )

    qr.add_data(link)

    qr.make(
        fit=True
    )

    buffer = io.BytesIO()

    qr.make_image().save(
        buffer,
        format="PNG",
    )

    st.subheader(
        "📷 QR الحضور"
    )

    st.image(
        buffer.getvalue(),
        width=400,
    )

    st.subheader(
        "🔗 رابط الحصة"
    )

    st.code(
        link,
        language="text",
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة": (
                    "✅ حاضر"
                    if row["marked_at"]
                    else "⏳ لم يسجل"
                ),
                "وقت الحضور": (
                    row["marked_at"]
                    or "-"
                ),
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    c1, c2 = st.columns(2)

    with c1:

        if st.button(
            "🔄 تحديث",
            use_container_width=True,
            key=f"refresh_{lesson['id']}",
        ):

            st.rerun()

    with c2:

        if st.button(
            "⛔ إنهاء الحصة",
            use_container_width=True,
            key=f"end_{lesson['id']}",
        ):

            conn = db()

            try:

                conn.execute(
                    """
                    UPDATE lessons
                    SET active = 0,
                        ended_at = ?
                    WHERE id = ?
                    """,
                    (
                        now(),
                        lesson["id"],
                    ),
                )

                conn.commit()

            finally:

                conn.close()

            st.success(
                "✅ تم إنهاء الحصة وحفظ الغياب."
            )

            st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports():

    st.subheader(
        "📋 التقارير"
    )

    conn = db()

    try:

        lessons = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 0
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()

    if not lessons:

        st.info(
            "📭 لا توجد حصص منتهية."
        )

        return

    labels = [
        (
            f"#{x['id']} | "
            f"{x['grade']} | "
            f"{x['group_name']} | "
            f"{x['lesson_name']}"
        )
        for x in lessons
    ]

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="report_lesson",
    )

    lesson = lessons[
        labels.index(selected)
    ]

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                s.name,
                s.phone,
                s.grade,
                s.group_name,
                a.marked_at
            FROM lesson_students ls
            JOIN students s
            ON s.id = ls.student_id
            LEFT JOIN attendance a
            ON a.lesson_id = ls.lesson_id
            AND a.student_id = ls.student_id
            WHERE ls.lesson_id = ?
            ORDER BY s.name
            """,
            (lesson["id"],),
        ).fetchall()

    finally:

        conn.close()

    total = len(rows)

    present = sum(
        1
        for row in rows
        if row["marked_at"]
    )

    absent = total - present

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total,
    )

    c2.metric(
        "✅ الحضور",
        present,
    )

    c3.metric(
        "❌ الغياب",
        absent,
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "الحالة": (
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب"
                ),
                "وقت الحضور": (
                    row["marked_at"]
                    or "-"
                ),
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STATISTICS
# =========================================================

def statistics():

    st.subheader(
        "📈 إحصائيات الطلاب"
    )

    table = []

    for grade in GRADES:

        for group in GROUPS:

            count = group_count(
                grade,
                group,
            )

            table.append(
                {
                    "الصف": grade,
                    "المجموعة": group,
                    "الطلاب": count,
                    "السعة": GROUP_LIMIT,
                    "المتبقي": (
                        GROUP_LIMIT - count
                    ),
                }
            )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENTS
# =========================================================

def students():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
    )

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                created_at
            FROM students
            ORDER BY grade, group_name, name
            """
        ).fetchall()

    finally:

        conn.close()

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
        len(rows),
    )

    search = st.text_input(
        "🔎 بحث بالاسم أو الهاتف",
        key="students_search",
    ).strip()

    filtered = []

    for row in rows:

        if (
            not search
            or search.lower()
            in row["name"].lower()
            or search
            in row["phone"]
        ):

            filtered.append(row)

    table = []

    for row in filtered:

        table.append(
            {
                "ID": row["id"],
                "الاسم": row["name"],
                "الهاتف": row["phone"],
                "ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "تاريخ التسجيل": row["created_at"],
            }
        )

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "📭 لا يوجد طلاب."
        )


# =========================================================
# ANALYTICS
# =========================================================

def analytics():

    st.subheader(
        "📊 التحليلات المتقدمة"
    )

    conn = db()

    try:

        students_rows = conn.execute(
            """
            SELECT
                id,
                name,
                phone,
                grade,
                group_name
            FROM students
            ORDER BY name
            """
        ).fetchall()

        # =================================================
        # FEATURE 1
        # ATTENDANCE BY GRADE
        # =================================================

        st.markdown(
            "### 📈 نسبة الحضور حسب الصف"
        )

        grade_table = []

        for grade in GRADES:

            total = conn.execute(
                """
                SELECT COUNT(*)
                FROM lesson_students ls
                JOIN lessons l
                ON l.id = ls.lesson_id
                WHERE l.active = 0
                AND l.grade = ?
                """,
                (grade,),
            ).fetchone()[0]

            present = conn.execute(
                """
                SELECT COUNT(*)
                FROM attendance a
                JOIN lessons l
                ON l.id = a.lesson_id
                WHERE l.active = 0
                AND l.grade = ?
                """,
                (grade,),
            ).fetchone()[0]

            absent = total - present

            percentage = (
                present / total * 100
                if total
                else 0
            )

            grade_table.append(
                {
                    "الصف": grade,
                    "إجمالي الحضور المتوقع": total,
                    "الحضور": present,
                    "الغياب": absent,
                    "نسبة الحضور": (
                        f"{percentage:.1f}%"
                    ),
                }
            )

        st.dataframe(
            grade_table,
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # =================================================
        # FEATURE 2
        # TOP STUDENTS
        # =================================================

        st.markdown(
            "### 🏆 أكثر الطلاب حضورًا"
        )

        top_table = []

        for student in students_rows:

            total = conn.execute(
                """
                SELECT COUNT(*)
                FROM lesson_students ls
                JOIN lessons l
                ON l.id = ls.lesson_id
                WHERE ls.student_id = ?
                AND l.active = 0
                """,
                (student["id"],),
            ).fetchone()[0]

            present = conn.execute(
                """
                SELECT COUNT(*)
                FROM attendance a
                JOIN lessons l
                ON l.id = a.lesson_id
                WHERE a.student_id = ?
                AND l.active = 0
                """,
                (student["id"],),
            ).fetchone()[0]

            absent = total - present

            percentage = (
                present / total * 100
                if total
                else 0
            )

            if total > 0:

                top_table.append(
                    {
                        "الطالب": student["name"],
                        "الصف": student["grade"],
                        "المجموعة": student["group_name"],
                        "الحضور": present,
                        "الغياب": absent,
                        "النسبة": percentage,
                    }
                )

        top_table.sort(
            key=lambda x: x["النسبة"],
            reverse=True,
        )

        top_table = top_table[:10]

        for row in top_table:

            row["النسبة"] = (
                f"{row['النسبة']:.1f}%"
            )

        if top_table:

            st.dataframe(
                top_table,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "📭 لا توجد بيانات حضور."
            )

        st.divider()

        # =================================================
        # FEATURE 3
        # ABSENT STUDENTS
        # =================================================

        st.markdown(
            "### ⚠️ الطلاب أصحاب الغياب الكثير"
        )

        absent_table = []

        for student in students_rows:

            total = conn.execute(
                """
                SELECT COUNT(*)
                FROM lesson_students ls
                JOIN lessons l
                ON l.id = ls.lesson_id
                WHERE ls.student_id = ?
                AND l.active = 0
                """,
                (student["id"],),
            ).fetchone()[0]

            present = conn.execute(
                """
                SELECT COUNT(*)
                FROM attendance a
                JOIN lessons l
                ON l.id = a.lesson_id
                WHERE a.student_id = ?
                AND l.active = 0
                """,
                (student["id"],),
            ).fetchone()[0]

            absent = total - present

            percentage = (
                absent / total * 100
                if total
                else 0
            )

            if absent > 0:

                absent_table.append(
                    {
                        "الطالب": student["name"],
                        "الصف": student["grade"],
                        "المجموعة": student["group_name"],
                        "الحصص": total,
                        "الحضور": present,
                        "الغياب": absent,
                        "نسبة الغياب": percentage,
                    }
                )

        absent_table.sort(
            key=lambda x: (
                x["الغياب"],
                x["نسبة الغياب"],
            ),
            reverse=True,
        )

        absent_table = absent_table[:20]

        for row in absent_table:

            row["نسبة الغياب"] = (
                f"{row['نسبة الغياب']:.1f}%"
            )

        if absent_table:

            st.dataframe(
                absent_table,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.success(
                "🎉 لا يوجد غياب حتى الآن."
            )

        st.divider()

        # =================================================
        # FEATURE 4
        # GROUP STATISTICS
        # =================================================

        st.markdown(
            "### 👥 إحصائيات المجموعات"
        )

        group_table = []

        for grade in GRADES:

            for group in GROUPS:

                students_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM students
                    WHERE grade = ?
                    AND group_name = ?
                    """,
                    (
                        grade,
                        group,
                    ),
                ).fetchone()[0]

                total = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM lesson_students ls
                    JOIN lessons l
                    ON l.id = ls.lesson_id
                    WHERE l.active = 0
                    AND l.grade = ?
                    AND l.group_name = ?
                    """,
                    (
                        grade,
                        group,
                    ),
                ).fetchone()[0]

                present = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM attendance a
                    JOIN lessons l
                    ON l.id = a.lesson_id
                    WHERE l.active = 0
                    AND l.grade = ?
                    AND l.group_name = ?
                    """,
                    (
                        grade,
                        group,
                    ),
                ).fetchone()[0]

                absent = total - present

                percentage = (
                    present / total * 100
                    if total
                    else 0
                )

                group_table.append(
                    {
                        "الصف": grade,
                        "المجموعة": group,
                        "الطلاب": students_count,
                        "المتبقي": (
                            GROUP_LIMIT
                            - students_count
                        ),
                        "الحضور": present,
                        "الغياب": absent,
                        "نسبة الحضور": (
                            f"{percentage:.1f}%"
                        ),
                    }
                )

        st.dataframe(
            group_table,
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # =================================================
        # FEATURE 5
        # SEARCH STUDENT
        # =================================================

        st.markdown(
            "### 🔎 البحث عن طالب"
        )

        search = st.text_input(
            "اكتب اسم الطالب أو رقم الهاتف",
            key="analytics_search",
        ).strip()

        if search:

            matches = []

            for student in students_rows:

                if (
                    search.lower()
                    in student["name"].lower()
                    or search
                    in student["phone"]
                ):

                    matches.append(student)

            if not matches:

                st.warning(
                    "❌ لم يتم العثور على الطالب."
                )

            else:

                options = []

                for student in matches:

                    options.append(
                        f"{student['name']} | "
                        f"{student['grade']} | "
                        f"{student['group_name']}"
                    )

                selected = st.selectbox(
                    "اختر الطالب",
                    options,
                    key="analytics_selected_student",
                )

                selected_student = matches[
                    options.index(selected)
                ]

                st.success(
                    f"""
👨‍🎓 الاسم: {selected_student['name']}

🎓 الصف: {selected_student['grade']}

👥 المجموعة: {selected_student['group_name']}

📱 الهاتف: {selected_student['phone']}
                    """
                )

                (
                    total,
                    present,
                    absent,
                    percentage,
                ) = student_stats(
                    selected_student["id"]
                )

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "📚 الحصص
