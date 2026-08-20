import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re
import time
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
# STREAMLIT CONFIG
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
        max-width: 1150px;
        padding-top: 25px;
        padding-bottom: 50px;
    }

    .main-title {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 26px;
        margin-bottom: 30px;
    }

    .student-card {
        padding: 18px;
        border-radius: 15px;
        margin: 10px 0;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    """
    إنشاء اتصال SQLite بطريقة أكثر أمانًا مع Streamlit.
    """

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass

    return conn


# =========================================================
# DATABASE INIT
# =========================================================

def init_db():

    conn = get_connection()

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

        # Indexes
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
            CREATE INDEX IF NOT EXISTS idx_lessons_active
            ON lessons(active)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_attendance_lesson
            ON attendance(lesson_id)
            """
        )

        conn.commit()

    except Exception:
        conn.rollback()

    finally:
        conn.close()


# =========================================================
# BASIC HELPERS
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


def page_url():

    try:
        return st.context.url
    except Exception:
        return ""


def base_url():

    current = page_url()

    if current:

        parsed = urlparse(current)

        return (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}"
        )

    return ""


def student_registration_url():

    base = base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def lesson_url(token):

    base = base_url()

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

def show_header(title, subtitle):

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
# STUDENT FUNCTIONS
# =========================================================

def get_student(student_id):

    conn = get_connection()

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


def group_count(grade, group_name):

    conn = get_connection()

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
                group_name,
            ),
        ).fetchone()

        return row["total"]

    finally:

        conn.close()


def group_is_full(grade, group_name):

    return (
        group_count(
            grade,
            group_name,
        )
        >= GROUP_LIMIT
    )


# =========================================================
# LESSON FUNCTIONS
# =========================================================

def get_lesson_by_token(token):

    if not token:
        return None

    conn = get_connection()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            LIMIT 1
            """,
            (token,),
        ).fetchone()

    finally:

        conn.close()


def get_open_lesson(
    grade,
    group_name,
):

    conn = get_connection()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE grade = ?
            AND group_name = ?
            AND active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                grade,
                group_name,
            ),
        ).fetchone()

    finally:

        conn.close()


def get_active_lessons():

    conn = get_connection()

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

    conn = get_connection()

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
# CREATE LESSON
# =========================================================

def create_lesson(
    lesson_name,
    grade,
    group_name,
):

    lesson_name = (
        lesson_name.strip()
        or "الحصة الحالية"
    )

    conn = get_connection()

    try:

        # لا نسمح بأكثر من حصة مفتوحة
        # لنفس الصف + المجموعة.
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
                group_name,
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
                lesson_name,
                grade,
                group_name,
                token,
                now(),
            ),
        )

        lesson_id = cursor.lastrowid

        students = conn.execute(
            """
            SELECT id
            FROM students
            WHERE grade = ?
            AND group_name = ?
            ORDER BY id
            """,
            (
                grade,
                group_name,
            ),
        ).fetchall()

        for student in students:

            conn.execute(
                """
                INSERT OR IGNORE INTO lesson_students
                (
                    lesson_id,
                    student_id
                )
                VALUES (?, ?)
                """,
                (
                    lesson_id,
                    student["id"],
                ),
            )

        conn.commit()

        return True, lesson_id

    except Exception as e:

        conn.rollback()

        return False, str(e)

    finally:

        conn.close()


# =========================================================
# END LESSON
# =========================================================

def end_lesson(lesson_id):

    conn = get_connection()

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
                lesson_id,
            ),
        )

        conn.commit()

    except Exception:

        conn.rollback()

    finally:

        conn.close()


# =========================================================
# LESSON STUDENTS
# =========================================================

def refresh_lesson_students(
    lesson_id,
    grade,
    group_name,
):

    conn = get_connection()

    try:

        students = conn.execute(
            """
            SELECT id
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group_name,
            ),
        ).fetchall()

        for student in students:

            conn.execute(
                """
                INSERT OR IGNORE INTO lesson_students
                (
                    lesson_id,
                    student_id
                )
                VALUES (?, ?)
                """,
                (
                    lesson_id,
                    student["id"],
                ),
            )

        conn.commit()

    except Exception:

        conn.rollback()

    finally:

        conn.close()


# =========================================================
# LESSON STATS
# =========================================================

def lesson_stats(lesson_id):

    conn = get_connection()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["total"]

        present = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["total"]

        absent = total - present

        return total, present, absent

    finally:

        conn.close()


# =========================================================
# QR TOKEN
# =========================================================

def extract_token(value):

    if not value:
        return None

    value = str(value).strip()

    # Token فقط
    if (
        "://" not in value
        and "page=" not in value
        and "lesson=" not in value
    ):
        return value

    try:

        parsed = urlparse(value)

        query = parse_qs(
            parsed.query
        )

        token_list = query.get(
            "lesson"
        )

        if token_list:

            return unquote(
                token_list[0]
            ).strip()

    except Exception:
        pass

    # محاولة إضافية
    match = re.search(
        r"(?:lesson=)([^&\s]+)",
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

        # 1
        value, points, _ = (
            detector.detectAndDecode(
                image
            )
        )

        if value:
            return value.strip()

        # 2 grayscale
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        value, points, _ = (
            detector.detectAndDecode(
                gray
            )
        )

        if value:
            return value.strip()

        # 3 resize
        h, w = gray.shape[:2]

        resized = cv2.resize(
            gray,
            (
                w * 2,
                h * 2,
            ),
            interpolation=cv2.INTER_CUBIC,
        )

        value, points, _ = (
            detector.detectAndDecode(
                resized
            )
        )

        if value:
            return value.strip()

        # 4 threshold
        _, threshold = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY
            + cv2.THRESH_OTSU,
        )

        value, points, _ = (
            detector.detectAndDecode(
                threshold
            )
        )

        if value:
            return value.strip()

        # 5 Multi QR
        try:

            found, values, points, _ = (
                detector.detectAndDecodeMulti(
                    image
                )
            )

            if found and values:

                for item in values:

                    if item:
                        return item.strip()

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

    token = extract_token(token)

    if not token:

        return False, "❌ كود QR غير صحيح."

    student = get_student(
        student_id
    )

    if not student:

        return False, "❌ الطالب غير موجود."

    lesson = get_lesson_by_token(
        token
    )

    if not lesson:

        return False, (
            "❌ الحصة غير موجودة."
        )

    if not lesson["active"]:

        return False, (
            "❌ هذه الحصة انتهت."
        )

    # الصف والمجموعة
    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        return False, (
            "❌ هذا الرابط خاص بصف أو مجموعة أخرى."
        )

    # الطالب لازم يكون ضمن قائمة الحصة
    refresh_lesson_students(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

    conn = get_connection()

    try:

        registered = conn.execute(
            """
            SELECT 1
            FROM lesson_students
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if not registered:

            return False, (
                "❌ الطالب غير مسجل في هذه الحصة."
            )

        # هل حضر بالفعل؟
        already = conn.execute(
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

        if already:

            return True, (
                f"✅ حضورك مسجل بالفعل "
                f"في {already['marked_at']}."
            )

        try:

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
                    now(),
                ),
            )

            conn.commit()

            return True, (
                "🎉 تم تسجيل حضورك بنجاح."
            )

        except sqlite3.IntegrityError:

            conn.rollback()

            return True, (
                "✅ حضورك مسجل بالفعل."
            )

    except Exception as e:

        conn.rollback()

        return False, (
            f"❌ حدث خطأ أثناء تسجيل الحضور: {e}"
        )

    finally:

        conn.close()


# =========================================================
# STUDENT REGISTRATION
# =========================================================

def student_registration(lesson=None):

    show_header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    if lesson:

        st.success(
            f"📚 أنت داخل رابط: "
            f"{lesson['lesson_name']}"
        )

        st.info(
            f"""
            🎓 الصف: {lesson['grade']}

            👥 المجموعة: {lesson['group_name']}

            🕐 بداية الحصة: {lesson['created_at']}
            """
        )

        st.warning(
            """
            ⚠️ سجل بياناتك مرة واحدة فقط.
            بعد التسجيل سيتم فتح نفس الحصة تلقائيًا.
            """
        )

    else:

        st.info(
            """
            👋 التسجيل يتم مرة واحدة.

            بعد التسجيل يمكنك استخدام رابط أي حصة
            يرسله لك المدرس.
            """
        )

    with st.form(
        "student_registration_form"
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

        if lesson:

            st.text_input(
                "🎓 الصف",
                value=lesson["grade"],
                disabled=True,
            )

            st.text_input(
                "👥 المجموعة",
                value=lesson["group_name"],
                disabled=True,
            )

            grade = lesson["grade"]
            group = lesson["group_name"]

        else:

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
                f"👨‍🎓 {group}: "
                f"{count}/{GROUP_LIMIT} طالب"
            )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submitted:
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
            "❌ رقم هاتف الطالب غير صحيح."
        )

        return

    # لو المجموعة ممتلئة
    # نستثني الحالة التي يكون فيها الطالب
    # موجود بالفعل.
    conn = get_connection()

    try:

        existing = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

    finally:

        conn.close()

    if existing:

        # الطالب موجود بالفعل
        # لا نسجله مرة أخرى.

        st.session_state.student_id = (
            existing["id"]
        )

        st.query_params["page"] = (
            "student"
        )

        st.query_params["student"] = (
            str(existing["id"])
        )

        if lesson:

            st.query_params["lesson"] = (
                lesson["token"]
            )

        st.success(
            "✅ الطالب مسجل بالفعل."
        )

        st.rerun()

    # التأكد من السعة
    if group_is_full(
        grade,
        group,
    ):

        st.error(
            f"❌ {group} وصلت إلى "
            f"{GROUP_LIMIT} طالب."
        )

        return

    conn = get_connection()

    try:

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

        if lesson:

            st.query_params["lesson"] = (
                lesson["token"]
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
# STUDENT PAGE
# =========================================================

def student_page():

    show_header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    # =====================================================
    # LESSON FROM URL
    # =====================================================

    lesson_token = st.query_params.get(
        "lesson"
    )

    lesson = None

    if lesson_token:

        token = extract_token(
            lesson_token
        )

        if token:

            lesson = get_lesson_by_token(
                token
            )

    # =====================================================
    # STUDENT ID
    # =====================================================

    student_id = (
        st.session_state.get(
            "student_id"
        )
    )

    query_student = st.query_params.get(
        "student"
    )

    if (
        student_id is None
        and query_student
    ):

        try:

            student_id = int(
                query_student
            )

            st.session_state.student_id = (
                student_id
            )

        except Exception:

            student_id = None

    # =====================================================
    # NOT REGISTERED
    # =====================================================

    if student_id is None:

        student_registration(
            lesson=lesson
        )

        return

    # =====================================================
    # GET STUDENT
    # =====================================================

    student = get_student(
        student_id
    )

    if not student:

        st.session_state.pop(
            "student_id",
            None
        )

        st.query_params.clear()

        st.rerun()

    # =====================================================
    # STUDENT INFO
    # =====================================================

    st.success(
        f"""
        👨‍🎓 {student['name']}

        🎓 {student['grade']}

        👥 {student['group_name']}
        """
    )

    # =====================================================
    # IF NO LESSON IN URL
    # =====================================================

    if lesson is None:

        lesson = get_open_lesson(
            student["grade"],
            student["group_name"],
        )

    # =====================================================
    # NO LESSON
    # =====================================================

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة لمجموعتك حالياً.

            📱 عندما يبدأ المدرس الحصة،
            افتح رابط الحصة الذي سيرسله لك.
            """
        )

        return

    # =====================================================
    # LESSON ENDED
    # =====================================================

    if not lesson["active"]:

        st.error(
            """
            ❌ هذه الحصة انتهت.
            """
        )

        return

    # =====================================================
    # CHECK GROUP
    # =====================================================

    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        st.error(
            """
            ❌ هذا الرابط خاص بصف أو مجموعة أخرى.

            لا يمكن تسجيل حضورك في هذه الحصة.
            """
        )

        st.info(
            f"""
            صفك: {student['grade']}

            مجموعتك: {student['group_name']}
            """
        )

        return

    # =====================================================
    # LESSON INFO
    # =====================================================

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    c1, c2 = st.columns(2)

    with c1:

        st.info(
            f"🎓 الصف\n\n{lesson['grade']}"
        )

    with c2:

        st.info(
            f"👥 المجموعة\n\n{lesson['group_name']}"
        )

    st.write(
        f"🕐 **بداية الحصة:** "
        f"{lesson['created_at']}"
    )

    # =====================================================
    # CHECK ATTENDANCE
    # =====================================================

    conn = get_connection()

    try:

        already = conn.execute(
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

    finally:

        conn.close()

    if already:

        st.success(
            "✅ حضورك مسجل بالفعل."
        )

        st.info(
            f"🕐 وقت تسجيل الحضور: "
            f"{already['marked_at']}"
        )

        return

    # =====================================================
    # DIRECT ATTENDANCE
    # =====================================================

    st.success(
        """
        🟢 أنت داخل رابط الحصة الصحيح.
        """
    )

    if st.button(
        "✅ تسجيل حضوري الآن",
        use_container_width=True,
    ):

        ok, message = mark_attendance(
            lesson["token"],
            student_id,
        )

        if ok:

            st.success(message)

            st.balloons()

            time.sleep(0.5)

            st.rerun()

        else:

            st.error(message)

    # =====================================================
    # QR SCANNER
    # =====================================================

    st.divider()

    st.subheader(
        "📷 تسجيل الحضور بالـQR"
    )

    st.info(
        """
        لو المدرس يستخدم QR،
        صوّر الكود الموجود عنده.
        """
    )

    photo = st.camera_input(
        "📷 تصوير QR",
        key=f"qr_camera_{lesson['id']}",
    )

    if photo:

        raw_value = decode_qr(
            photo.getvalue()
        )

        if not raw_value:

            st.error(
                """
                ❌ لم يتم قراءة QR.

                حاول أن يكون الكود كاملًا وواضحًا
                داخل الكاميرا.
                """
            )

            return

        token = extract_token(
            raw_value
        )

        if not token:

            st.error(
                "❌ هذا QR غير صالح."
            )

            return

        # لازم QR يكون لنفس الحصة
        if token != lesson["token"]:

            st.error(
                """
                ❌ هذا QR خاص بحصة أخرى.
                """
            )

            return

        ok, message = mark_attendance(
            token,
            student_id,
        )

        if ok:

            st.success(message)

            st.balloons()

        else:

            st.error(message)

        time.sleep(0.5)

        st.rerun()


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    show_header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    st.info(
        "🔐 سجل دخول المدرس لإدارة الحصص."
    )

    password = st.text_input(
        "🔐 كلمة مرور المدرس",
        type="password",
    )

    if st.button(
        "👨‍🏫 دخول المدرس",
        use_container_width=True,
    ):

        if password == TEACHER_PASSWORD:

            st.session_state.teacher = True

            st.success(
                "✅ تم تسجيل الدخول."
            )

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.caption(
        "كلمة المرور الافتراضية: 1234"
    )


# =========================================================
# CREATE LESSON PAGE
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="create_grade",
    )

    st.write(
        "👥 الطلاب في كل مجموعة:"
    )

    cols = st.columns(3)

    for i, group in enumerate(GROUPS):

        count = group_count(
            grade,
            group,
        )

        with cols[i]:

            st.metric(
                group,
                f"{count}/{GROUP_LIMIT}",
            )

    group = st.selectbox(
        "👥 اختر مجموعة الحصة",
        GROUPS,
        key="create_group",
    )

    selected_count = group_count(
        grade,
        group,
    )

    st.info(
        f"""
        👨‍🎓 عدد الطلاب في {group}:
        {selected_count}/{GROUP_LIMIT}
        """
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    active_same_group = get_open_lesson(
        grade,
        group,
    )

    if active_same_group:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة بالفعل لهذه المجموعة:

            📚 {active_same_group['lesson_name']}

            🕐 {active_same_group['created_at']}
            """
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية",
            use_container_width=True,
        ):

            end_lesson(
                active_same_group["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if selected_count == 0:

            st.error(
                """
                ❌ لا يوجد طلاب في هذه المجموعة.

                سجل الطلاب أولًا.
                """
            )

            return

        success, result = create_lesson(
            lesson_name,
            grade,
            group,
        )

        if not success:

            st.error(
                f"❌ {result}"
            )

            return

        st.success(
            "🎉 تم إنشاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# CURRENT LESSON PAGE
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصص الحالية"
    )

    lessons = get_active_lessons()

    if not lessons:

        st.info(
            "⏳ لا توجد حصص مفتوحة حاليًا."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']}"
        )

        options[label] = lesson

    selected_label = st.selectbox(
        "اختر الحصة",
        list(options.keys()),
        key="current_lesson_selector",
    )

    lesson = options[
        selected_label
    ]

    # تحديث قائمة الطلاب
    refresh_lesson_students(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

    total, present, absent = (
        lesson_stats(
            lesson["id"]
        )
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "👨‍🎓 إجمالي الطلاب",
            total,
        )

    with c2:

        st.metric(
            "✅ الحضور",
            present,
        )

    with c3:

        st.metric(
            "❌ الغياب",
            absent,
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
        f"🕐 **وقت البداية:** {lesson['created_at']}"
    )

    # =====================================================
    # LESSON LINK
    # =====================================================

    link = lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الحصة للطلاب"
    )

    st.code(
        link,
        language="text",
    )

    st.success(
        """
        📱 ابعت الرابط ده لطلاب المجموعة.
        الطالب الذي يفتح الرابط سيتم توجيهه لهذه الحصة نفسها.
        """
    )

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📷 QR الخاص بالحصة"
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=5,
    )

    # مهم جدًا:
    # QR يحتوي رابط الحصة الكامل
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
        caption="📷 امسح هذا الكود لتسجيل الحضور",
        width=350,
    )

    # =====================================================
    # STUDENTS TABLE
    # =====================================================

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    conn = get_connection()

    try:

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

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )

    # =====================================================
    # BUTTONS
    # =====================================================

    c1, c2 = st.columns(2)

    with c1:

        if st.button(
            "🔄 تحديث الحضور",
            use_container_width=True,
        ):

            st.rerun()

    with c2:

        if st.button(
            "⛔ إنهاء الحصة وحفظها",
            use_container_width=True,
        ):

            end_lesson(
                lesson["id"]
            )

            st.success(
                """
                ✅ تم إنهاء الحصة وحفظ الحضور والغياب.
                """
            )

            st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.subheader(
        "📋 التقارير والحصص المحفوظة"
    )

    lessons = get_all_lessons()

    if not lessons:

        st.info(
            "لا توجد حصص محفوظة."
        )

        return

    options = {}

    for lesson in lessons:

        status = (
            "🟢 مفتوحة"
            if lesson["active"]
            else "⚫ منتهية"
        )

        label = (
            f"#{lesson['id']} | "
            f"{status} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys()),
        key="report_lesson_selector",
    )

    lesson_id = options[
        selected
    ]

    total, present, absent = (
        lesson_stats(
            lesson_id
        )
    )

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "👨‍🎓 إجمالي الطلاب",
            total,
        )

    with c2:

        st.metric(
            "✅ الحضور",
            present,
        )

    with c3:

        st.metric(
            "❌ الغياب",
            absent,
        )

    conn = get_connection()

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
            (lesson_id,),
        ).fetchall()

    finally:

        conn.close()

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# STATISTICS
# =========================================================

def statistics_page():

    st.subheader(
        "📈 إحصائيات الصفوف والمجموعات"
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                grade,
                group_name,
                COUNT(*) AS total
            FROM students
            GROUP BY grade, group_name
            """
        ).fetchall()

    finally:

        conn.close()

    counts = {}

    for row in rows:

        counts[
            (
                row["grade"],
                row["group_name"],
            )
        ] = row["total"]

    table = []

    for grade in GRADES:

        for group in GROUPS:

            total = counts.get(
                (
                    grade,
                    group,
                ),
                0,
            )

            table.append(
                {
                    "الصف": grade,
                    "المجموعة": group,
                    "الطلاب": total,
                    "السعة": GROUP_LIMIT,
                    "المتبقي":
                        max(
                            GROUP_LIMIT - total,
                            0,
                        ),
                }
            )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENTS PAGE
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
    )

    conn = get_connection()

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

    if not rows:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )

        return

    data = []

    for row in rows:

        data.append(
            {
                "ID": row["id"],
                "الاسم": row["name"],
                "هاتف الطالب": row["phone"],
                "هاتف ولي الأمر":
                    row["parent_phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "تاريخ التسجيل":
                    row["created_at"],
            }
        )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# TEACHER DASHBOARD
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher",
        False,
    ):

        teacher_login()

        return

    show_header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    if st.button(
        "🚪 تسجيل خروج المدرس"
    ):

        st.session_state.teacher = False

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصص الحالية",
            "📋 التقارير",
            "📈 الإحصائيات",
            "👨‍🎓 الطلاب",
        ]
    )

    with tabs[0]:

        create_lesson_page()

    with tabs[1]:

        current_lesson_page()

    with tabs[2]:

        reports_page()

    with tabs[3]:

        statistics_page()

    with tabs[4]:

        students_page()

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_registration_url(),
        language="text",
    )

    st.info(
        """
        📱 هذا الرابط يستخدم للتسجيل العام.

        أما عند إنشاء حصة، استخدم رابط الحصة
        الموجود داخل تبويب "الحصص الحالية".
        """
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    page = st.query_params.get(
        "page",
        "teacher",
    )

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
