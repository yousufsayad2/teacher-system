import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re
import csv
import hashlib

from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote


# =========================================================
# CONFIG
# =========================================================

DB_FILE = "attendance_platform.db"

GROUPS = [
    "المجموعة 1",
    "المجموعة 2",
    "المجموعة 3",
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

TEACHER_PASSWORD = "1234"


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
        padding-bottom: 60px;
    }

    .main-title {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 25px;
        margin-bottom: 30px;
    }

    .big-number {
        font-size: 32px;
        font-weight: bold;
        text-align: center;
    }

    @media (max-width: 700px) {

        .main-title {
            font-size: 34px;
        }

        .sub-title {
            font-size: 20px;
        }

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

        # =====================================================
        # INDEXES
        # =====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_students_phone
            ON students(phone)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_students_grade_group
            ON students(grade, group_name)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lessons_token
            ON lessons(token)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_attendance_lesson
            ON attendance(lesson_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_attendance_student
            ON attendance(student_id)
            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# HELPERS
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


def safe_text(value):

    if value is None:
        return ""

    return str(value)


# =========================================================
# STUDENT HELPERS
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

    if sid is not None:

        try:

            sid = int(sid)

            if get_student(sid):

                return sid

        except Exception:

            pass

    sid = st.query_params.get(
        "student"
    )

    if sid:

        try:

            sid = int(sid)

            student = get_student(
                sid
            )

            if student:

                st.session_state.student_id = sid

                return sid

        except Exception:

            pass

    return None


# =========================================================
# URL
# =========================================================

def get_base_url():

    try:

        current = st.context.url

        if current:

            parsed = urlparse(
                current
            )

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    except Exception:

        pass

    return ""


def student_url():

    base = get_base_url()

    if base:

        return (
            f"{base}?page=student"
        )

    return "?page=student"


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


# =========================================================
# HEADER
# =========================================================

def header(
    title,
    subtitle,
):

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
# GROUP COUNT
# =========================================================

def group_count(
    grade,
    group,
):

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()

        return row["total"]

    finally:

        conn.close()


# =========================================================
# TOTAL STUDENTS
# =========================================================

def total_students():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            """
        ).fetchone()[0]

    finally:

        conn.close()


# =========================================================
# LESSON HELPERS
# =========================================================

def get_lesson_by_token(
    token
):

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


def get_all_lessons():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()


# =========================================================
# TOKEN
# =========================================================

def extract_token(
    value
):

    if not value:

        return None

    value = str(
        value
    ).strip()

    # QR يحتوي Token فقط

    if (
        "://" not in value
        and "lesson=" not in value
    ):

        return value

    try:

        parsed = urlparse(
            value
        )

        query = parse_qs(
            parsed.query
        )

        result = query.get(
            "lesson"
        )

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
# QR DECODER
# =========================================================

def decode_qr(
    image_bytes
):

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

        attempts = []

        attempts.append(
            image
        )

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        attempts.append(
            gray
        )

        h, w = gray.shape[:2]

        resized = cv2.resize(
            gray,
            (
                max(1, w * 2),
                max(1, h * 2),
            ),
            interpolation=cv2.INTER_CUBIC,
        )

        attempts.append(
            resized
        )

        # Threshold
        try:

            _, threshold = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY
                + cv2.THRESH_OTSU,
            )

            attempts.append(
                threshold
            )

        except Exception:

            pass

        for img in attempts:

            try:

                value, points, _ = (
                    detector.detectAndDecode(
                        img
                    )
                )

                if value:

                    return value.strip()

            except Exception:

                pass

        return None

    except Exception:

        return None


# =========================================================
# ATTENDANCE
# =========================================================

def mark_attendance(
    token,
    student_id,
):

    token = extract_token(
        token
    )

    if not token:

        return (
            False,
            "❌ QR غير صحيح.",
        )

    lesson = get_lesson_by_token(
        token
    )

    if not lesson:

        return (
            False,
            "❌ الحصة غير موجودة أو انتهت.",
        )

    student = get_student(
        student_id
    )

    if not student:

        return (
            False,
            "❌ الطالب غير موجود.",
        )

    # =====================================================
    # الصف والمجموعة
    # =====================================================

    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        return (
            False,
            f"""
❌ لا يمكنك تسجيل الحضور في هذه الحصة.

📚 الحصة تخص:

🎓 {lesson['grade']}
👥 {lesson['group_name']}

وأنت مسجل في:

🎓 {student['grade']}
👥 {student['group_name']}
            """,
        )

    conn = db()

    try:

        # =================================================
        # إضافة الطالب إلى كشف الحصة
        # =================================================

        conn.execute(
            """
            INSERT OR IGNORE INTO
            lesson_students
            (
                lesson_id,
                student_id
            )
            VALUES (?, ?)
            """,
            (
                lesson["id"],
                student_id,
            ),
        )

        # =================================================
        # هل حضر بالفعل؟
        # =================================================

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

            conn.commit()

            return (
                True,
                f"""
✅ حضورك مسجل بالفعل.

🕐 وقت الحضور:
{existing['marked_at']}
                """,
            )

        # =================================================
        # تسجيل الحضور
        # =================================================

        attendance_time = now()

        conn.execute(
            """
            INSERT INTO attendance
            (
                lesson_id,
                student_id,
                marked_at
            )
            VALUES (?, ?, ?)
            """,
            (
                lesson["id"],
                student_id,
                attendance_time,
            ),
        )

        conn.commit()

        return (
            True,
            f"""
🎉 تم تسجيل حضورك بنجاح.

🕐 {attendance_time}
            """,
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ: {e}",
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
        """
👋 أهلاً بك.

سجل بياناتك مرة واحدة فقط،
وبعدها يمكنك الدخول إلى حسابك في أي وقت.
        """
    )

    with st.form(
        "student_register_form",
        clear_on_submit=False,
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

        count = group_count(
            grade,
            group,
        )

        st.info(
            f"👥 {group}: "
            f"{count}/{GROUP_LIMIT} طالب"
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submit:

        return

    name = name.strip()

    phone = clean_phone(
        phone
    )

    parent_phone = clean_phone(
        parent_phone
    )

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

            st.session_state.student_id = (
                old["id"]
            )

            st.query_params["page"] = (
                "student"
            )

            st.query_params["student"] = (
                str(old["id"])
            )

            st.success(
                "✅ الحساب موجود بالفعل، تم الدخول إليه."
            )

            st.rerun()

        count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()["total"]

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

        student_id = cursor.lastrowid

        st.session_state.student_id = (
            student_id
        )

        st.query_params["page"] = (
            "student"
        )

        st.query_params["student"] = (
            str(student_id)
        )

        st.success(
            "🎉 تم تسجيل الطالب بنجاح."
        )

        st.rerun()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    except Exception as e:

        conn.rollback()

        st.error(
            f"❌ حدث خطأ: {e}"
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

    st.info(
        """
👨‍🎓 إذا كنت مسجلاً من قبل،
اكتب رقم هاتفك للدخول إلى حسابك.
        """
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

    phone = clean_phone(
        phone
    )

    if len(phone) < 8:

        st.error(
            "❌ رقم الهاتف غير صحيح."
        )

        return

    student = get_student_by_phone(
        phone
    )

    if not student:

        st.error(
            """
❌ لا يوجد حساب بهذا الرقم.

استخدم تسجيل طالب جديد.
            """
        )

        return

    st.session_state.student_id = (
        student["id"]
    )

    st.query_params["page"] = (
        "student"
    )

    st.query_params["student"] = (
        str(student["id"])
    )

    st.success(
        "✅ تم تسجيل الدخول."
    )

    st.rerun()


# =========================================================
# STUDENT ATTENDANCE HISTORY
# =========================================================

def get_student_attendance(
    student_id
):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT
                l.id AS lesson_id,
                l.lesson_name,
                l.grade,
                l.group_name,
                l.created_at,
                l.ended_at,
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
# STUDENT STATISTICS
# =========================================================

def student_stats(
    student_id
):

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
            (present / total) * 100
            if total > 0
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


# =========================================================
# STUDENT PROFILE
# =========================================================

def student_profile(
    student
):

    st.subheader(
        "👤 بيانات الطالب"
    )

    c1, c2 = st.columns(2)

    with c1:

        st.write(
            f"**👨‍🎓 الاسم:** "
            f"{student['name']}"
        )

        st.write(
            f"**🎓 الصف:** "
            f"{student['grade']}"
        )

    with c2:

        st.write(
            f"**👥 المجموعة:** "
            f"{student['group_name']}"
        )

        st.write(
            f"**📱 الهاتف:** "
            f"{student['phone']}"
        )

    st.divider()

    total, present, absent, percentage = (
        student_stats(
            student["id"]
        )
    )

    st.subheader(
        "📊 إحصائيات الحضور"
    )

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

    if total > 0:

        if percentage >= 75:

            st.success(
                f"🟢 نسبة حضورك ممتازة: {percentage:.1f}%"
            )

        elif percentage >= 50:

            st.warning(
                f"🟡 نسبة حضورك: {percentage:.1f}%"
            )

        else:

            st.error(
                f"🔴 نسبة حضورك منخفضة: {percentage:.1f}%"
            )


# =========================================================
# STUDENT CAMERA
# =========================================================

def student_attendance_page(
    student
):

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.info(
        """
📱 افتح الكاميرا ووجّهها إلى QR الموجود عند المدرس.

النظام سيحدد الحصة والصف والمجموعة تلقائياً.
        """
    )

    photo = st.camera_input(
        "📷 امسح QR الحصة",
        key="student_camera",
    )

    if photo:

        image_bytes = photo.getvalue()

        image_hash = hashlib.sha256(
            image_bytes
        ).hexdigest()

        # =================================================
        # منع إعادة معالجة نفس الصورة
        # =================================================

        already_processed = (
            st.session_state.get(
                "last_camera_hash"
            )
            == image_hash
        )

        if already_processed:

            st.info(
                "✅ تم التعامل مع هذه الصورة بالفعل."
            )

        else:

            st.session_state[
                "last_camera_hash"
            ] = image_hash

            raw = decode_qr(
                image_bytes
            )

            if not raw:

                st.error(
                    """
❌ لم يتم قراءة QR.

جرّب تقريب الكاميرا من الكود
وتأكد من وجود إضاءة جيدة.
                    """
                )

            else:

                token = extract_token(
                    raw
                )

                if not token:

                    st.error(
                        "❌ هذا QR غير صالح."
                    )

                else:

                    lesson = get_lesson_by_token(
                        token
                    )

                    if not lesson:

                        st.error(
                            """
❌ الحصة غير موجودة أو انتهت.
                            """
                        )

                    else:

                        st.info(
                            f"""
📚 الحصة: {lesson['lesson_name']}

🎓 الصف: {lesson['grade']}

👥 المجموعة: {lesson['group_name']}
                            """
                        )

                        ok, message = (
                            mark_attendance(
                                token,
                                student["id"],
                            )
                        )

                        if ok:

                            st.success(
                                message
                            )

                            st.balloons()

                        else:

                            st.error(
                                message
                            )

    st.divider()

    st.subheader(
        "🔗 تسجيل الحضور بالرابط"
    )

    manual_link = st.text_input(
        "🔗 الصق رابط الحصة هنا",
        key="manual_lesson_link",
    )

    if st.button(
        "✅ تسجيل الحضور بالرابط",
        use_container_width=True,
        key="manual_attendance_button",
    ):

        token = extract_token(
            manual_link
        )

        if not token:

            st.error(
                "❌ الرابط غير صحيح."
            )

        else:

            ok, message = (
                mark_attendance(
                    token,
                    student["id"],
                )
            )

            if ok:

                st.success(
                    message
                )

            else:

                st.error(
                    message
                )


# =========================================================
# STUDENT HISTORY
# =========================================================

def student_history(
    student
):

    st.subheader(
        "📋 سجل الحضور والغياب"
    )

    rows = get_student_attendance(
        student["id"]
    )

    if not rows:

        st.info(
            "📭 لا توجد حصص منتهية حتى الآن."
        )

        return

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            attendance_time = (
                row["marked_at"]
            )

        else:

            status = "❌ غائب"

            attendance_time = "-"

        table.append(
            {
                "الحصة":
                    row["lesson_name"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "تاريخ الحصة":
                    row["created_at"],

                "الحالة":
                    status,

                "وقت الحضور":
                    attendance_time,
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    student_id = get_student_id()

    # =====================================================
    # تسجيل / دخول
    # =====================================================

    if student_id is None:

        login_tab, register_tab = st.tabs(
            [
                "🔐 دخول الطالب",
                "📝 تسجيل لأول مرة",
            ]
        )

        with login_tab:

            student_login()

        with register_tab:

            student_register()

        return

    # =====================================================
    # الطالب
    # =====================================================

    student = get_student(
        student_id
    )

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.session_state.pop(
            "last_camera_hash",
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

    tabs = st.tabs(
        [
            "📷 تسجيل الحضور",
            "👤 حسابي",
            "📋 سجل الحضور",
        ]
    )

    with tabs[0]:

        student_attendance_page(
            student
        )

    with tabs[1]:

        student_profile(
            student
        )

    with tabs[2]:

        student_history(
            student
        )

    st.divider()

    if st.button(
        "🚪 تسجيل خروج الطالب",
        use_container_width=True,
        key="student_logout",
    ):

        st.session_state.pop(
            "student_id",
            None,
        )

        st.session_state.pop(
            "last_camera_hash",
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
        "👨‍🏫 لوحة تحكم المدرس",
    )

    st.info(
        "🔐 ادخل كلمة مرور المدرس."
    )

    password = st.text_input(
        "🔐 كلمة مرور المدرس",
        type="password",
        key="teacher_password_input",
    )

    if st.button(
        "👨‍🏫 دخول",
        use_container_width=True,
        key="teacher_login_button",
    ):

        if password == TEACHER_PASSWORD:

            st.session_state.teacher = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 اختر الصف",
        GRADES,
        key="lesson_grade",
    )

    st.write(
        "👥 عدد الطلاب في مجموعات الصف:"
    )

    cols = st.columns(3)

    for i, group in enumerate(
        GROUPS
    ):

        count = group_count(
            grade,
            group,
        )

        cols[i].metric(
            group,
            f"{count}/{GROUP_LIMIT}",
        )

    group = st.selectbox(
        "👥 اختر المجموعة",
        GROUPS,
        key="lesson_group",
    )

    count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 عدد طلاب {group}: "
        f"{count}/{GROUP_LIMIT}"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
        key="start_lesson_button",
    ):

        if count == 0:

            st.error(
                """
❌ لا يوجد طلاب في هذه المجموعة.

يجب تسجيل الطلاب أولاً.
                """
            )

            return

        conn = db()

        try:

            # =================================================
            # إنهاء الحصة القديمة لنفس الصف والمجموعة
            # =================================================

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

            token = secrets.token_urlsafe(
                32
            )

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

            lesson_id = (
                cursor.lastrowid
            )

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

            for student_row in students_rows:

                conn.execute(
                    """
                    INSERT OR IGNORE INTO
                    lesson_students
                    (
                        lesson_id,
                        student_id
                    )
                    VALUES (?, ?)
                    """,
                    (
                        lesson_id,
                        student_row["id"],
                    ),
                )

            conn.commit()

            st.success(
                "🎉 تم بدء الحصة بنجاح."
            )

            st.rerun()

        except Exception as e:

            conn.rollback()

            st.error(
                f"❌ حدث خطأ: {e}"
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
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    labels = []

    for lesson in lessons:

        labels.append(
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']}"
        )

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="current_lesson_select",
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

    waiting = max(
        0,
        total - present
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total,
    )

    c2.metric(
        "✅ حضر",
        present,
    )

    c3.metric(
        "⏳ لم يسجل",
        waiting,
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"📚 **الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📷 QR الحضور"
    )

    link = lesson_url(
        lesson["token"]
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            qrcode.constants.ERROR_CORRECT_H
        ),
        box_size=12,
        border=5,
    )

    qr.add_data(
        link
    )

    qr.make(
        fit=True
    )

    qr_image = qr.make_image()

    buffer = io.BytesIO()

    qr_image.save(
        buffer,
        format="PNG",
    )

    st.image(
        buffer.getvalue(),
        width=400,
        caption="📷 QR الحضور",
    )

    st.subheader(
        "🔗 رابط الحصة"
    )

    st.code(
        link,
        language="text",
    )

    # =====================================================
    # كشف الطلاب
    # =====================================================

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time_value = (
                row["marked_at"]
            )

        else:

            status = "⏳ لم يسجل"

            time_value = "-"

        table.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الحالة":
                    status,

                "وقت الحضور":
                    time_value,
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
            "لا يوجد طلاب."
        )

    # =====================================================
    # CSV
    # =====================================================

    csv_data = create_csv(
        table
    )

    st.download_button(
        "📥 تحميل كشف الحصة CSV",
        data=csv_data,
        file_name=(
            f"lesson_{lesson['id']}_attendance.csv"
        ),
        mime="text/csv",
        use_container_width=True,
        key=f"download_current_{lesson['id']}",
    )

    # =====================================================
    # تحديث
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True,
        key=f"refresh_{lesson['id']}",
    ):

        st.rerun()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    st.warning(
        """
⚠️ عند إنهاء الحصة سيتم اعتبار كل طالب لم يسجل
حضوراً = غائب في التقرير.
        """
    )

    if st.button(
        "⛔ إنهاء الحصة وحفظ الغياب",
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
            """
✅ تم إنهاء الحصة.

❌ الطلاب الذين لم يسجلوا حضورهم
أصبحوا غائبين في التقرير.
            """
        )

        st.rerun()


# =========================================================
# CSV HELPER
# =========================================================

def create_csv(
    rows
):

    output = io.StringIO()

    if not rows:

        return ""

    writer = csv.DictWriter(
        output,
        fieldnames=rows[0].keys(),
    )

    writer.writeheader()

    for row in rows:

        writer.writerow(
            row
        )

    return "\ufeff" + output.getvalue()


# =========================================================
# REPORTS
# =========================================================

def reports():

    st.subheader(
        "📋 التقارير"
    )

    lessons = get_all_lessons()

    finished_lessons = [
        lesson
        for lesson in lessons
        if lesson["active"] == 0
    ]

    if not finished_lessons:

        st.info(
            "📭 لا توجد حصص منتهية."
        )

        return

    labels = []

    for lesson in finished_lessons:

        labels.append(
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="report_lesson",
    )

    lesson = finished_lessons[
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

    percentage = (
        (present / total) * 100
        if total > 0
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
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
        "📈 نسبة الحضور",
        f"{percentage:.1f}%",
    )

    st.write(
        f"📚 **الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    st.write(
        f"⛔ **انتهت:** {lesson['ended_at'] or '-'}"
    )

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time_value = (
                row["marked_at"]
            )

        else:

            status = "❌ غائب"

            time_value = "-"

        table.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "الحالة":
                    status,

                "وقت الحضور":
                    time_value,
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    csv_data = create_csv(
        table
    )

    st.download_button(
        "📥 تحميل تقرير الحصة CSV",
        data=csv_data,
        file_name=(
            f"attendance_report_{lesson['id']}.csv"
        ),
        mime="text/csv",
        use_container_width=True,
        key=f"download_report_{lesson['id']}",
    )


# =========================================================
# STATISTICS
# =========================================================

def statistics():

    st.subheader(
        "📈 إحصائيات المنصة"
    )

    total = total_students()

    lessons = get_all_lessons()

    finished = [
        lesson
        for lesson in lessons
        if lesson["active"] == 0
    ]

    active = [
        lesson
        for lesson in lessons
        if lesson["active"] == 1
    ]

    conn = db()

    try:

        total_attendance = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            """
        ).fetchone()[0]

    finally:

        conn.close()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 الطلاب",
        total,
    )

    c2.metric(
        "📚 إجمالي الحصص",
        len(lessons),
    )

    c3.metric(
        "🟢 الحصص المفتوحة",
        len(active),
    )

    c4.metric(
        "✅ سجلات الحضور",
        total_attendance,
    )

    st.divider()

    st.subheader(
        "🎓 الطلاب حسب الصف والمجموعة"
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
                    "الصف":
                        grade,

                    "المجموعة":
                        group,

                    "الطلاب":
                        count,

                    "السعة":
                        GROUP_LIMIT,

                    "المتبقي":
                        max(
                            0,
                            GROUP_LIMIT - count,
                        ),
                }
            )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENTS SEARCH
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

            ORDER BY
                grade,
                group_name,
                name
            """
        ).fetchall()

    finally:

        conn.close()

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
        len(rows),
    )

    # =====================================================
    # SEARCH
    # =====================================================

    search = st.text_input(
        "🔎 ابحث بالاسم أو رقم الهاتف",
        key="student_search",
    )

    grade_filter = st.selectbox(
        "🎓 فلترة حسب الصف",
        ["كل الصفوف"] + GRADES,
        key="student_grade_filter",
    )

    group_filter = st.selectbox(
        "👥 فلترة حسب المجموعة",
        ["كل المجموعات"] + GROUPS,
        key="student_group_filter",
    )

    filtered = []

    search_value = (
        search.strip().lower()
    )

    for row in rows:

        if search_value:

            name_match = (
                search_value
                in row["name"].lower()
            )

            phone_match = (
                search_value
                in row["phone"]
            )

            if not (
                name_match
                or phone_match
            ):

                continue

        if (
            grade_filter != "كل الصفوف"
            and row["grade"]
            != grade_filter
        ):

            continue

        if (
            group_filter != "كل المجموعات"
            and row["group_name"]
            != group_filter
        ):

            continue

        filtered.append(
            row
        )

    st.info(
        f"🔎 النتائج: {len(filtered)} طالب"
    )

    table = []

    for row in filtered:

        total, present, absent, percentage = (
            student_stats(
                row["id"]
            )
        )

        table.append(
            {
                "ID":
                    row["id"],

                "الاسم":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "ولي الأمر":
                    row["parent_phone"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "الحصص":
                    total,

                "الحضور":
                    present,

                "الغياب":
                    absent
