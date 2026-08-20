import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote


# =========================================================
# CONFIG
# =========================================================

APP_DIR = Path(__file__).resolve().parent
DB_FILE = APP_DIR / "attendance_platform.db"

TEACHER_PASSWORD = "1234"

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


# =========================================================
# STREAMLIT CONFIG
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1100px;
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

    div.stButton > button {
        min-height: 48px;
        font-size: 18px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
# =========================================================

def get_connection():
    """
    إنشاء اتصال SQLite بشكل آمن نسبيًا مع Streamlit.
    """

    conn = sqlite3.connect(
        str(DB_FILE),
        timeout=60,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    # تحسين التعامل مع تعدد الاتصالات
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")

    return conn


def init_db():
    """
    إنشاء قاعدة البيانات والجداول والفهارس.
    """

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                parent_phone TEXT DEFAULT '',
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_name TEXT NOT NULL,
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS lesson_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                UNIQUE(lesson_id, student_id),
                FOREIGN KEY(lesson_id)
                    REFERENCES lessons(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(student_id)
                    REFERENCES students(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TEXT NOT NULL,
                UNIQUE(lesson_id, student_id),
                FOREIGN KEY(lesson_id)
                    REFERENCES lessons(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(student_id)
                    REFERENCES students(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_students_grade_group
            ON students(grade, group_name);

            CREATE INDEX IF NOT EXISTS idx_lessons_grade_group
            ON lessons(grade, group_name);

            CREATE INDEX IF NOT EXISTS idx_lessons_active
            ON lessons(active);

            CREATE INDEX IF NOT EXISTS idx_attendance_lesson
            ON attendance(lesson_id);

            CREATE INDEX IF NOT EXISTS idx_lesson_students_lesson
            ON lesson_students(lesson_id);

            CREATE INDEX IF NOT EXISTS idx_lesson_students_student
            ON lesson_students(student_id);
            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# GENERAL HELPERS
# =========================================================

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def clean_phone(value):
    return re.sub(
        r"\D",
        "",
        value or "",
    )


def page_url():
    """
    الحصول على رابط التطبيق الحالي.
    """

    try:
        return st.context.url
    except Exception:
        return ""


def build_base_url():
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
    base = build_base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def lesson_url(token):
    base = build_base_url()

    if base:
        return (
            f"{base}"
            f"?page=student"
            f"&lesson={token}"
        )

    return f"?page=student&lesson={token}"


# =========================================================
# QR HELPERS
# =========================================================

def extract_token(value):
    """
    استخراج Token من:
    1- Token فقط
    2- رابط كامل
    3- أي نص يحتوي lesson=
    """

    if not value:
        return None

    value = str(value).strip()

    # Token فقط
    if (
        "://" not in value
        and "lesson=" not in value
        and "page=" not in value
    ):
        return value

    try:

        parsed = urlparse(value)

        params = parse_qs(
            parsed.query
        )

        token_list = params.get(
            "lesson"
        )

        if token_list:

            token = unquote(
                token_list[0]
            ).strip()

            if token:
                return token

    except Exception:
        pass

    match = re.search(
        r"(?:^|[?&])lesson=([^&\s]+)",
        value,
    )

    if match:

        return unquote(
            match.group(1)
        ).strip()

    return None


def decode_qr(image_bytes):
    """
    قراءة QR من صورة الكاميرا.
    """

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

        # -------------------------
        # 1
        # -------------------------

        value, points, _ = (
            detector.detectAndDecode(
                image
            )
        )

        if value:
            return value.strip()

        # -------------------------
        # 2 - grayscale
        # -------------------------

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

        # -------------------------
        # 3 - resize
        # -------------------------

        h, w = gray.shape[:2]

        resized = cv2.resize(
            gray,
            (w * 2, h * 2),
            interpolation=cv2.INTER_CUBIC,
        )

        value, points, _ = (
            detector.detectAndDecode(
                resized
            )
        )

        if value:
            return value.strip()

        # -------------------------
        # 4 - threshold
        # -------------------------

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

        # -------------------------
        # 5 - multi QR
        # -------------------------

        try:

            ok, values, points, _ = (
                detector.detectAndDecodeMulti(
                    image
                )
            )

            if ok and values:

                for item in values:

                    if item:
                        return item.strip()

        except Exception:
            pass

        return None

    except Exception:
        return None


# =========================================================
# STUDENTS / GROUPS
# =========================================================

def group_count(
    grade,
    group_name,
):

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

        return int(
            row["total"]
        )

    finally:

        conn.close()


def group_is_full(
    grade,
    group_name,
):

    return (
        group_count(
            grade,
            group_name,
        )
        >= GROUP_LIMIT
    )


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


# =========================================================
# LESSONS
# =========================================================

def get_open_lessons():

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
            WHERE active = 1
            AND grade = ?
            AND group_name = ?
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


def get_lesson_by_token(token):

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


def create_lesson(
    lesson_name,
    grade,
    group_name,
):

    conn = get_connection()

    try:

        # منع وجود حصتين مفتوحتين لنفس الصف والمجموعة
        existing = conn.execute(
            """
            SELECT id
            FROM lessons
            WHERE active = 1
            AND grade = ?
            AND group_name = ?
            LIMIT 1
            """,
            (
                grade,
                group_name,
            ),
        ).fetchone()

        if existing:

            return (
                False,
                "توجد حصة مفتوحة بالفعل لهذه المجموعة.",
            )

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

        if not students:

            return (
                False,
                "لا يوجد طلاب في هذه المجموعة.",
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

        return (
            True,
            lesson_id,
        )

    except sqlite3.OperationalError as e:

        conn.rollback()

        return (
            False,
            "مشكلة في قاعدة البيانات: "
            + str(e),
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            str(e),
        )

    finally:

        conn.close()


def finish_lesson(lesson_id):

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

    finally:

        conn.close()


# =========================================================
# ATTENDANCE
# =========================================================

def get_lesson_stats(lesson_id):

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

        return (
            total,
            present,
            absent,
        )

    finally:

        conn.close()


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

    conn = get_connection()

    try:

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

        if not lesson:

            return (
                False,
                "❌ الـQR غير صالح أو الحصة انتهت.",
            )

        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()

        if not student:

            return (
                False,
                "❌ الطالب غير موجود.",
            )

        # الصف والمجموعة
        if (
            student["grade"]
            != lesson["grade"]
            or
            student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذا الـQR خاص بمجموعة أخرى.",
            )

        # هل الطالب موجود في كشف الحصة؟
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

            return (
                False,
                "❌ الطالب غير موجود في كشف هذه الحصة.",
            )

        # منع التكرار
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
                "✅ حضورك مسجل بالفعل في "
                + existing["marked_at"],
            )

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

        return (
            True,
            "🎉 تم تسجيل حضورك بنجاح.",
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except sqlite3.OperationalError as e:

        conn.rollback()

        return (
            False,
            "❌ مشكلة في قاعدة البيانات: "
            + str(e),
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            "❌ حدث خطأ: "
            + str(e),
        )

    finally:

        conn.close()


# =========================================================
# HEADER
# =========================================================

def show_header(
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
# STUDENT REGISTER
# =========================================================

def student_register():

    show_header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    st.info(
        """
        التسجيل يتم مرة واحدة.
        بعد ذلك الطالب يدخل مباشرة إلى واجهته
        ويستخدم QR الخاص بالحصة.
        """
    )

    with st.form(
        "register_student",
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

        current_count = group_count(
            grade,
            group,
        )

        st.info(
            f"👥 {group}: "
            f"{current_count}/{GROUP_LIMIT}"
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submitted:
        return

    name = name.strip()
    phone = clean_phone(phone)
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

        existing = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

        if existing:

            st.session_state.student_id = (
                existing["id"]
            )

            st.query_params["page"] = "student"
            st.query_params["student"] = str(
                existing["id"]
            )

            st.success(
                "✅ رقم الهاتف مسجل بالفعل، تم فتح حساب الطالب."
            )

            st.rerun()

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

        st.query_params["page"] = "student"
        st.query_params["student"] = str(
            student_id
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
            "❌ حدث خطأ: "
            + str(e)
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

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    if student_id is None and query_student:

        try:

            student_id = int(
                query_student
            )

            st.session_state.student_id = (
                student_id
            )

        except Exception:

            student_id = None

    if student_id is None:

        student_register()

        return

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

    st.success(
        f"👨‍🎓 {student['name']}  |  "
        f"{student['grade']}  |  "
        f"{student['group_name']}"
    )

    # -----------------------------------------------------
    # QR lesson from URL
    # -----------------------------------------------------

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

            if lesson and not lesson["active"]:

                lesson = None

    # -----------------------------------------------------
    # Otherwise get current lesson
    # -----------------------------------------------------

    if lesson is None:

        lesson = get_open_lesson(
            student["grade"],
            student["group_name"],
        )

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة لمجموعتك حالياً.
            """
        )

        return

    # -----------------------------------------------------
    # Verify group
    # -----------------------------------------------------

    if (
        lesson["grade"]
        != student["grade"]
        or
        lesson["group_name"]
        != student["group_name"]
    ):

        st.error(
            "❌ هذه الحصة ليست لمجموعتك."
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 الصف: {lesson['grade']}"
    )

    st.write(
        f"👥 المجموعة: {lesson['group_name']}"
    )

    st.write(
        f"🕐 بدأت: {lesson['created_at']}"
    )

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

        st.write(
            f"🕐 وقت الحضور: "
            f"{already['marked_at']}"
        )

        return

    st.info(
        """
        📷 صوّر QR الخاص بالحصة.
        """

    )

    photo = st.camera_input(
        "📷 تصوير QR",
        key=f"camera_{lesson['id']}",
    )

    if not photo:
        return

    raw_value = decode_qr(
        photo.getvalue()
    )

    if not raw_value:

        st.error(
            """
            ❌ لم أستطع قراءة QR.

            حاول أن يكون الكود كاملًا
            وواضحًا داخل الكاميرا.
            """
        )

        return

    token = extract_token(
        raw_value
    )

    if not token:

        st.error(
            "❌ هذا QR ليس تابعًا لمنصة الحضور."
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

    st.rerun()


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    show_header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
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
# CREATE LESSON
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 اختر الصف",
        GRADES,
        key="create_grade",
    )

    st.markdown(
        "### 👥 مجموعات الصف"
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
        key="create_group",
    )

    count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 عدد طلاب {group}: "
        f"{count}/{GROUP_LIMIT}"
    )

    if count == 0:

        st.warning(
            """
            ⚠️ لا يوجد طلاب في المجموعة.
            سجل الطلاب أولًا.
            """
        )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if count == 0:

            st.error(
                "❌ لا يمكن إنشاء حصة لمجموعة بدون طلاب."
            )

            return

        success, result = create_lesson(
            lesson_name.strip()
            or "الحصة الحالية",
            grade,
            group,
        )

        if not success:

            st.error(
                "❌ " + str(result)
            )

            return

        st.success(
            "🎉 تم إنشاء الحصة."
        )

        st.rerun()


# =========================================================
# CURRENT LESSONS
# =========================================================

def current_lessons_page():

    st.subheader(
        "📊 الحصص المفتوحة حاليًا"
    )

    lessons = get_open_lessons()

    if not lessons:

        st.info(
            "⏳ لا توجد حصص مفتوحة حاليًا."
        )

        return

    for lesson in lessons:

        total, present, absent = (
            get_lesson_stats(
                lesson["id"]
            )
        )

        with st.container(
            border=True
        ):

            st.markdown(
                f"### 📚 {lesson['lesson_name']}"
            )

            st.write(
                f"🎓 {lesson['grade']}"
            )

            st.write(
                f"👥 {lesson['group_name']}"
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "الطلاب",
                total,
            )

            c2.metric(
                "الحضور",
                present,
            )

            c3.metric(
                "الغياب",
                absent,
            )

            st.write(
                f"🕐 {lesson['created_at']}"
            )

            link = lesson_url(
                lesson["token"]
            )

            st.write(
                "🔗 رابط الحصة:"
            )

            st.code(
                link,
                language="text",
            )

            # QR بالرابط الكامل
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
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
                caption="📷 QR الخاص بهذه الحصة",
                width=320,
            )

            # الطلاب
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

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "⛔ إنهاء وحفظ الحصة",
                key=f"finish_{lesson['id']}",
                use_container_width=True,
            ):

                finish_lesson(
                    lesson["id"]
                )

                st.success(
                    """
                    ✅ انتهت الحصة.

                    تم حفظ الحضور والغياب
                    والتاريخ والوقت.
                    """
                )

                st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.subheader(
        "📋 التقارير والحصص السابقة"
    )

    conn = get_connection()

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
            "لا توجد حصص محفوظة حتى الآن."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "📚 اختر الحصة",
        list(options.keys()),
    )

    lesson_id = options[
        selected
    ]

    total, present, absent = (
        get_lesson_stats(
            lesson_id
        )
    )

    c1, c2, c3 = st.columns(3)

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

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STATISTICS
# =========================================================

def statistics_page():

    st.subheader(
        "📈 إحصائيات الطلاب"
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
                    "عدد الطلاب": total,
                    "السعة": GROUP_LIMIT,
                    "المتبقي":
                        max(
                            0,
                            GROUP_LIMIT - total
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
        "👨‍🎓 الطلاب"
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

    if table:

        st.dataframe(
            table,
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
        "🚪 تسجيل خروج"
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
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_registration_url(),
        language="text",
    )

    st.info(
        """
        📱 ابعت الرابط للطلاب.

        الطالب يسجل بياناته مرة واحدة،
        وبعدها كل حصة لها QR خاص بها.
        """
    )


# =========================================================
# MAIN
# =========================================================

def main():

    try:

        init_db()

    except Exception as e:

        st.error(
            "❌ تعذر تشغيل قاعدة البيانات."
        )

        st.code(
            str(e)
        )

        st.stop()

    page = st.query_params.get(
        "page",
        "teacher",
    )

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
