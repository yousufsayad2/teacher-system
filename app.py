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
# إعدادات النظام
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
# إعداد Streamlit
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
)


# =========================================================
# التصميم
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

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# قاعدة البيانات
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass

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
            CREATE INDEX IF NOT EXISTS idx_lesson_students_lesson
            ON lesson_students(lesson_id)
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
# أدوات عامة
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


def get_page_url():

    try:
        return st.context.url
    except Exception:
        return ""


def get_base_url():

    current = get_page_url()

    if not current:
        return ""

    parsed = urlparse(current)

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
    )


def student_registration_url():

    base = get_base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def make_lesson_url(token):

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
# الطلاب
# =========================================================

def get_student(student_id):

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


def group_count(grade, group_name):

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
                group_name,
            ),
        ).fetchone()

        return int(row["total"])

    finally:

        conn.close()


def group_full(grade, group_name):

    return (
        group_count(
            grade,
            group_name,
        )
        >= GROUP_LIMIT
    )


# =========================================================
# الحصص
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

    conn = db()

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
# إنشاء حصة
# =========================================================

def create_lesson(
    lesson_name,
    grade,
    group_name,
):

    conn = db()

    try:

        # نغلق أي حصة قديمة لنفس الصف والمجموعة فقط
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
                lesson_name.strip()
                or "الحصة الحالية",
                grade,
                group_name,
                token,
                now(),
            ),
        )

        lesson_id = cursor.lastrowid

        # لو فيه طلاب موجودين بالفعل
        # يتم ربطهم بالحصة مباشرة.
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
# إنهاء الحصة
# =========================================================

def end_lesson(lesson_id):

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
                lesson_id,
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
# إضافة طالب للحصة
# =========================================================

def add_student_to_lesson(
    lesson_id,
    student_id,
):

    conn = db()

    try:

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
                student_id,
            ),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()

        return False

    finally:

        conn.close()


def sync_lesson_students(
    lesson_id,
    grade,
    group_name,
):

    conn = db()

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
# إحصائيات الحصة
# =========================================================

def lesson_stats(lesson_id):

    conn = db()

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

        return (
            int(total),
            int(present),
            int(absent),
        )

    finally:

        conn.close()


# =========================================================
# QR
# =========================================================

def extract_token(value):

    if not value:
        return None

    value = str(value).strip()

    # لو QR فيه Token فقط
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

        values = query.get(
            "lesson"
        )

        if values:

            return unquote(
                values[0]
            ).strip()

    except Exception:
        pass

    match = re.search(
        r"lesson=([^&\s]+)",
        value,
    )

    if match:

        return unquote(
            match.group(1)
        ).strip()

    return None


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

        # محاولة 1
        value, points, _ = (
            detector.detectAndDecode(
                image
            )
        )

        if value:
            return value.strip()

        # محاولة 2 - Gray
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

        # محاولة 3 - تكبير
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

        # محاولة 4 - Threshold
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

        # محاولة 5 - Multi QR
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
# تسجيل الحضور
# =========================================================

def mark_attendance(
    token,
    student_id,
):

    token = extract_token(token)

    if not token:

        return (
            False,
            "❌ كود QR غير صحيح."
        )

    student = get_student(
        student_id
    )

    if not student:

        return (
            False,
            "❌ الطالب غير موجود."
        )

    lesson = get_lesson_by_token(
        token
    )

    if not lesson:

        return (
            False,
            "❌ الحصة غير موجودة."
        )

    if not lesson["active"]:

        return (
            False,
            "❌ هذه الحصة انتهت."
        )

    # =====================================================
    # التحقق من الصف والمجموعة
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
            "❌ هذا الرابط خاص بصف أو مجموعة أخرى."
        )

    # =====================================================
    # إضافة الطالب لقائمة الحصة
    # =====================================================

    add_student_to_lesson(
        lesson["id"],
        student["id"],
    )

    # =====================================================
    # هل الحضور مسجل؟
    # =====================================================

    conn = db()

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
                student["id"],
            ),
        ).fetchone()

        if already:

            return (
                True,
                "✅ حضورك مسجل بالفعل "
                f"في {already['marked_at']}."
            )

        # =================================================
        # تسجيل الحضور
        # =================================================

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
                student["id"],
                now(),
            ),
        )

        conn.commit()

        return (
            True,
            "🎉 تم تسجيل حضورك بنجاح."
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل."
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ أثناء تسجيل الحضور: {e}"
        )

    finally:

        conn.close()


# =========================================================
# تسجيل الطالب
# =========================================================

def student_registration(lesson=None):

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    # =====================================================
    # لو الطالب داخل من رابط حصة
    # =====================================================

    if lesson:

        st.success(
            f"""
            📚 الحصة: {lesson['lesson_name']}

            🎓 الصف: {lesson['grade']}

            👥 المجموعة: {lesson['group_name']}
            """
        )

        st.info(
            """
            👋 اكتب بياناتك مرة واحدة فقط.

            الصف والمجموعة سيتم تحديدهم تلقائيًا
            من رابط الحصة.
            """
        )

    else:

        st.info(
            """
            👋 التسجيل العام للطالب.

            اختر الصف والمجموعة التي تنتمي إليها.
            """
        )

    # =====================================================
    # FORM
    # =====================================================

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

        # =================================================
        # لو التسجيل من رابط حصة
        # =================================================

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

            # =============================================
            # التسجيل العام
            # =============================================

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
                f"""
                👨‍🎓 عدد الطلاب في {group}:
                {count}/{GROUP_LIMIT}
                """
            )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submitted:
        return

    # =====================================================
    # تنظيف البيانات
    # =====================================================

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

    # =====================================================
    # هل الطالب مسجل بالفعل؟
    # =====================================================

    existing = get_student_by_phone(
        phone
    )

    if existing:

        # =================================================
        # لو جاي من رابط حصة
        # =================================================

        if lesson:

            # لازم بيانات الطالب تطابق الحصة
            if (
                existing["grade"]
                != lesson["grade"]
                or
                existing["group_name"]
                != lesson["group_name"]
            ):

                st.error(
                    """
                    ❌ رقم الهاتف مسجل بالفعل
                    ببيانات صف أو مجموعة مختلفة.

                    لا يمكن استخدام هذا الحساب
                    في مجموعة أخرى.
                    """
                )

                return

            student_id = existing["id"]

            add_student_to_lesson(
                lesson["id"],
                student_id,
            )

            st.session_state.student_id = (
                student_id
            )

            st.query_params["page"] = (
                "student"
            )

            st.query_params["student"] = (
                str(student_id)
            )

            st.query_params["lesson"] = (
                lesson["token"]
            )

            st.success(
                "✅ الطالب مسجل بالفعل، تم فتح الحصة."
            )

            st.rerun()

        else:

            st.session_state.student_id = (
                existing["id"]
            )

            st.query_params["page"] = (
                "student"
            )

            st.query_params["student"] = (
                str(existing["id"])
            )

            st.success(
                "✅ الطالب مسجل بالفعل."
            )

            st.rerun()

    # =====================================================
    # التأكد من سعة المجموعة
    # =====================================================

    if group_full(
        grade,
        group,
    ):

        st.error(
            f"""
            ❌ {group} وصلت إلى الحد الأقصى
            وهو {GROUP_LIMIT} طالب.
            """
        )

        return

    # =====================================================
    # إضافة الطالب
    # =====================================================

    conn = db()

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

        student_id = cursor.lastrowid

        conn.commit()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

        return

    except Exception as e:

        conn.rollback()

        st.error(
            f"❌ حدث خطأ: {e}"
        )

        return

    finally:

        conn.close()

    # =====================================================
    # ربط الطالب بالحصة
    # =====================================================

    if lesson:

        add_student_to_lesson(
            lesson["id"],
            student_id,
        )

    # =====================================================
    # حفظ Session
    # =====================================================

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


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    # =====================================================
    # قراءة رابط الحصة
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
    # قراءة الطالب
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
    # لو الطالب غير مسجل
    # =====================================================

    if student_id is None:

        student_registration(
            lesson=lesson
        )

        return

    # =====================================================
    # بيانات الطالب
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
    # بطاقة الطالب
    # =====================================================

    st.success(
        f"""
        👨‍🎓 {student['name']}

        🎓 {student['grade']}

        👥 {student['group_name']}
        """
    )

    # =====================================================
    # لو مفيش حصة في الرابط
    # =====================================================

    if lesson is None:

        lesson = get_open_lesson(
            student["grade"],
            student["group_name"],
        )

    # =====================================================
    # لا توجد حصة
    # =====================================================

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة لمجموعتك حاليًا.

            📱 عندما يبدأ المدرس الحصة،
            افتح رابط الحصة الذي سيرسله لك.
            """
        )

        return

    # =====================================================
    # الحصة منتهية
    # =====================================================

    if not lesson["active"]:

        st.error(
            """
            ❌ هذه الحصة انتهت.
            """
        )

        return

    # =====================================================
    # التحقق من الصف والمجموعة
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
            """
        )

        return

    # =====================================================
    # معلومات الحصة
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
    # هل حضر بالفعل؟
    # =====================================================

    conn = db()

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
            "✅ تم تسجيل حضورك بالفعل."
        )

        st.info(
            f"""
            🕐 وقت تسجيل الحضور:

            {already['marked_at']}
            """
        )

        return

    # =====================================================
    # تسجيل الحضور بالزر
    # =====================================================

    st.success(
        "🟢 الحصة مفتوحة ويمكنك تسجيل حضورك."
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
    # QR
    # =====================================================

    st.divider()

    st.subheader(
        "📷 تسجيل الحضور بالـQR"
    )

    st.info(
        """
        📷 صوّر QR الموجود عند المدرس.
        """
    )

    photo = st.camera_input(
        "📷 تصوير QR",
        key=f"qr_{lesson['id']}",
    )

    if photo:

        raw_value = decode_qr(
            photo.getvalue()
        )

        if not raw_value:

            st.error(
                """
                ❌ لم يتم قراءة QR.

                حاول تقريب الكاميرا
                وجعل الكود كاملًا واضحًا.
                """
            )

            return

        token = extract_token(
            raw_value
        )

        if not token:

            st.error(
                "❌ QR غير صالح."
            )

            return

        # QR لازم يكون لنفس الحصة
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
# دخول المدرس
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    st.info(
        "🔐 سجل دخول المدرس لإدارة النظام."
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

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.caption(
        "كلمة المرور الافتراضية: 1234"
    )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="lesson_grade",
    )

    st.write(
        "👥 مجموعات هذا الصف:"
    )

    cols = st.columns(3)

    for i, group in enumerate(
        GROUPS
    ):

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
        key="lesson_group",
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

    active = get_open_lesson(
        grade,
        group,
    )

    if active:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة بالفعل لهذه المجموعة:

            📚 {active['lesson_name']}

            🕐 {active['created_at']}
            """
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية",
            use_container_width=True,
        ):

            end_lesson(
                active["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    # =====================================================
    # بدء الحصة
    # =====================================================

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        # مهم:
        # لا نشترط وجود طلاب.
        # يمكن إنشاء الحصة وهي 0/70.

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
# الحصص الحالية
# =========================================================

def current_lessons_page():

    st.subheader(
        "📊 الحصص الحالية"
    )

    lessons = get_active_lessons()

    if not lessons:

        st.info(
            """
            ⏳ لا توجد حصص مفتوحة حاليًا.
            """
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

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys()),
        key="active_lesson_select",
    )

    lesson = options[
        selected
    ]

    # =====================================================
    # مزامنة الطلاب الموجودين
    # =====================================================

    sync_lesson_students(
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
    # رابط الحصة
    # =====================================================

    link = make_lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الحصة"
    )

    st.code(
        link,
        language="text",
    )

    st.success(
        """
        📱 ابعت الرابط ده لطلاب هذه المجموعة.
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

    # =====================================================
    # مهم جدًا:
    # QR يحتوي على رابط الحصة نفسه
    # =====================================================

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
        caption="📷 QR تسجيل الحضور",
        width=350,
    )

    # =====================================================
    # كشف الطلاب
    # =====================================================

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    conn = db()

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

    table = []

    for row in rows:

        table.append(
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

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            """
            لا يوجد طلاب في الحصة حتى الآن.
            """
        )

    # =====================================================
    # أزرار
    # =====================================================

    c1, c2 = st.columns(2)

    with c1:

        if st.button(
            "🔄 تحديث",
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
                ✅ تم إنهاء الحصة.

                تم حفظ الحضور والغياب والتاريخ والوقت.
                """
            )

            st.rerun()


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 التقارير"
    )

    lessons = get_all_lessons()

    if not lessons:

        st.info(
            "لا توجد حصص حتى الآن."
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
        key="report_select",
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
            "👨‍🎓 الإجمالي",
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
            (lesson_id,),
        ).fetchall()

    finally:

        conn.close()

    table = []

    for row in rows:

        table.append(
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

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# الإحصائيات
# =========================================================

def statistics_page():

    st.subheader(
        "📈 إحصائيات الطلاب"
    )

    conn = db()

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
        ] = int(row["total"])

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
                    "عدد الطلاب": total,
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
# صفحة الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب"
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

    if not rows:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )

        return

    table = []

    for row in rows:

        table.append(
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
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher",
        False,
    ):

        teacher_login()

        return

    header(
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

        current_lessons_page()

    with tabs[2]:

        reports_page()

    with tabs[3]:

        statistics_page()

    with tabs[4]:

        students_page()

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب العام"
    )

    st.code(
        student_registration_url(),
        language="text",
    )

    st.info(
        """
        📱 الرابط العام لتسجيل الطلاب.

        وبعد إنشاء حصة استخدم رابط الحصة
        الموجود في تبويب "الحصص الحالية".
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
# تشغيل البرنامج
# =========================================================

if __name__ == "__main__":
    main()
