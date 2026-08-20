import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re
import html
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

# من أولى إعدادي إلى ثالثة ثانوي
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
    initial_sidebar_state="collapsed",
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

    .small-note {
        text-align: center;
        opacity: 0.8;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
# =========================================================

def db():
    """
    إنشاء اتصال SQLite بطريقة أكثر أمانًا
    وتقليل مشاكل database locked / operational errors.
    """

    conn = sqlite3.connect(
        DB_FILE,
        timeout=60,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass

    return conn


def safe_close(conn):
    try:
        if conn:
            conn.close()
    except Exception:
        pass


def init_db():

    conn = db()

    try:

        # -------------------------------------------------
        # الطلاب
        # -------------------------------------------------

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

        # -------------------------------------------------
        # الحصص
        # -------------------------------------------------

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

        # -------------------------------------------------
        # الطلاب المسجلون في كل حصة
        # -------------------------------------------------

        conn.execute(
            """
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
            )
            """
        )

        # -------------------------------------------------
        # الحضور
        # -------------------------------------------------

        conn.execute(
            """
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
            )
            """
        )

        # -------------------------------------------------
        # Indexes
        # -------------------------------------------------

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_students_grade_group
            ON students(grade, group_name)
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
            CREATE INDEX IF NOT EXISTS idx_lessons_grade_group
            ON lessons(grade, group_name)
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

    except Exception as e:

        try:
            conn.rollback()
        except Exception:
            pass

        st.error(
            f"❌ حدث خطأ أثناء تجهيز قاعدة البيانات:\n\n{e}"
        )

    finally:

        safe_close(conn)


# =========================================================
# GENERAL HELPERS
# =========================================================

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def clean_phone(phone):
    return re.sub(
        r"\D",
        "",
        phone or "",
    )


def safe_html(value):
    return html.escape(
        str(value or "")
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

        if parsed.scheme and parsed.netloc:

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    return ""


# =========================================================
# URLS
# =========================================================

def student_url():

    base = base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def make_lesson_url(token):

    base = base_url()

    if base:
        return (
            f"{base}"
            f"?page=student"
            f"&lesson={token}"
        )

    return f"?page=student&lesson={token}"


# =========================================================
# QR TOKEN EXTRACTION
# =========================================================

def extract_token(value):

    if not value:
        return None

    value = clean_text(value)

    if not value:
        return None

    # -----------------------------------------------------
    # لو QR يحتوي Token فقط
    # -----------------------------------------------------

    if (
        "://" not in value
        and "lesson=" not in value
        and "page=" not in value
        and "?" not in value
    ):
        return value

    # -----------------------------------------------------
    # لو QR يحتوي رابط كامل
    # -----------------------------------------------------

    try:

        parsed = urlparse(value)

        query = parse_qs(
            parsed.query
        )

        lesson_values = query.get(
            "lesson"
        )

        if lesson_values:

            token = unquote(
                lesson_values[0]
            ).strip()

            if token:
                return token

    except Exception:
        pass

    # -----------------------------------------------------
    # محاولة Regex
    # -----------------------------------------------------

    match = re.search(
        r"(?:[?&]lesson=)([^&#\s]+)",
        value,
        re.IGNORECASE,
    )

    if match:

        token = unquote(
            match.group(1)
        ).strip()

        if token:
            return token

    # -----------------------------------------------------
    # لو المستخدم لصق الرابط وفيه lesson=
    # -----------------------------------------------------

    if "lesson=" in value:

        try:

            token = value.split(
                "lesson=",
                1
            )[1]

            token = token.split(
                "&",
                1
            )[0]

            token = token.split(
                "#",
                1
            )[0]

            token = unquote(
                token
            ).strip()

            if token:
                return token

        except Exception:
            pass

    return None


# =========================================================
# GROUP MANAGEMENT
# =========================================================

def group_count(
    grade,
    group_name,
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
                group_name,
            ),
        ).fetchone()

        return int(
            row["total"]
            if row
            else 0
        )

    except Exception:

        return 0

    finally:

        safe_close(conn)


def group_full(
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


# =========================================================
# ACTIVE LESSON
# =========================================================

def active_lesson():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    except Exception:

        return None

    finally:

        safe_close(conn)


# =========================================================
# LESSON STATS
# =========================================================

def lesson_stats(
    lesson_id,
):

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

        total = int(total or 0)
        present = int(present or 0)

        absent = max(
            0,
            total - present,
        )

        return (
            total,
            present,
            absent,
        )

    except Exception:

        return 0, 0, 0

    finally:

        safe_close(conn)


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson(
    lesson_name,
    grade,
    group_name,
):

    lesson_name = (
        clean_text(lesson_name)
        or "الحصة الحالية"
    )

    conn = db()

    try:

        # -------------------------------------------------
        # إنهاء أي حصة مفتوحة
        # -------------------------------------------------

        conn.execute(
            """
            UPDATE lessons
            SET active = 0,
                ended_at = COALESCE(
                    ended_at,
                    ?
                )
            WHERE active = 1
            """,
            (now(),),
        )

        # -------------------------------------------------
        # Token جديد للحصة
        # -------------------------------------------------

        token = secrets.token_urlsafe(
            32
        )

        created_at = now()

        cursor = conn.execute(
            """
            INSERT INTO lessons
            (
                lesson_name,
                grade,
                group_name,
                token,
                created_at,
                ended_at,
                active
            )
            VALUES (
                ?, ?, ?, ?, ?, NULL, 1
            )
            """,
            (
                lesson_name,
                grade,
                group_name,
                token,
                created_at,
            ),
        )

        lesson_id = cursor.lastrowid

        # -------------------------------------------------
        # تثبيت طلاب المجموعة داخل الحصة
        # -------------------------------------------------

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

        try:
            conn.rollback()
        except Exception:
            pass

        return False, str(e)

    finally:

        safe_close(conn)


# =========================================================
# END LESSON
# =========================================================

def end_lesson(
    lesson_id,
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
                lesson_id,
            ),
        )

        conn.commit()

        return True

    except Exception:

        try:
            conn.rollback()
        except Exception:
            pass

        return False

    finally:

        safe_close(conn)


# =========================================================
# QR DECODER
# =========================================================

def decode_qr(
    image_bytes,
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

        # -------------------------------------------------
        # 1 - الصورة الأصلية
        # -------------------------------------------------

        value, points, _ = (
            detector.detectAndDecode(
                image
            )
        )

        if value:

            return value.strip()

        # -------------------------------------------------
        # 2 - Grayscale
        # -------------------------------------------------

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

        # -------------------------------------------------
        # 3 - تكبير الصورة
        # -------------------------------------------------

        h, w = gray.shape[:2]

        if h > 0 and w > 0:

            scale = 3

            resized = cv2.resize(
                gray,
                (
                    w * scale,
                    h * scale,
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

        # -------------------------------------------------
        # 4 - Threshold
        # -------------------------------------------------

        try:

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

        except Exception:
            pass

        # -------------------------------------------------
        # 5 - Multi QR
        # -------------------------------------------------

        try:

            result = (
                detector.detectAndDecodeMulti(
                    image
                )
            )

            if result:

                retval = result[0]
                decoded_info = result[1]

                if retval and decoded_info:

                    for item in decoded_info:

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

def register_attendance(
    token,
    student_id,
):

    token = extract_token(
        token
    )

    if not token:

        return (
            False,
            "❌ كود QR غير صحيح."
        )

    conn = db()

    try:

        # -------------------------------------------------
        # البحث عن الحصة
        # -------------------------------------------------

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
                "❌ هذا QR غير صالح أو أن الحصة انتهت."
            )

        # -------------------------------------------------
        # الطالب
        # -------------------------------------------------

        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()

        if not student:

            return (
                False,
                "❌ الطالب غير موجود."
            )

        # -------------------------------------------------
        # التأكد من الصف والمجموعة
        # -------------------------------------------------

        if (
            student["grade"]
            != lesson["grade"]
            or
            student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذا QR خاص بصف أو مجموعة أخرى."
            )

        # -------------------------------------------------
        # التأكد أن الطالب موجود ضمن قائمة الحصة
        # -------------------------------------------------

        registered = conn.execute(
            """
            SELECT 1
            FROM lesson_students
            WHERE lesson_id = ?
            AND student_id = ?
            LIMIT 1
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if not registered:

            return (
                False,
                "❌ الطالب غير مسجل في هذه الحصة."
            )

        # -------------------------------------------------
        # منع تكرار الحضور
        # -------------------------------------------------

        already = conn.execute(
            """
            SELECT marked_at
            FROM attendance
            WHERE lesson_id = ?
            AND student_id = ?
            LIMIT 1
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if already:

            return (
                True,
                "✅ حضورك مسجل بالفعل."
            )

        # -------------------------------------------------
        # تسجيل الحضور
        # -------------------------------------------------

        marked_at = now()

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
                marked_at,
            ),
        )

        conn.commit()

        return (
            True,
            f"🎉 تم تسجيل حضورك بنجاح الساعة {marked_at}."
        )

    except sqlite3.IntegrityError:

        try:
            conn.rollback()
        except Exception:
            pass

        return (
            True,
            "✅ حضورك مسجل بالفعل."
        )

    except sqlite3.OperationalError as e:

        try:
            conn.rollback()
        except Exception:
            pass

        return (
            False,
            "❌ حصلت مشكلة مؤقتة في قاعدة البيانات. "
            "حاول مرة أخرى."
        )

    except Exception as e:

        try:
            conn.rollback()
        except Exception:
            pass

        return (
            False,
            f"❌ حدث خطأ: {e}"
        )

    finally:

        safe_close(conn)


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
            {safe_html(title)}
        </div>

        <div class="sub-title">
            {safe_html(subtitle)}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# STUDENT REGISTRATION
# =========================================================

def student_registration():

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    st.info(
        """
        👋 التسجيل يتم مرة واحدة فقط.

        بعد التسجيل، بياناتك تفضل محفوظة،
        وفي كل حصة تستخدم رابط أو QR الحصة.
        """
    )

    with st.form(
        "student_register_form",
        clear_on_submit=False,
    ):

        name = st.text_input(
            "👨‍🎓 اسم الطالب",
            placeholder="اكتب الاسم كاملًا",
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب",
            placeholder="01xxxxxxxxx",
        )

        parent_phone = st.text_input(
            "👪 رقم هاتف ولي الأمر",
            placeholder="01xxxxxxxxx",
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
            f"👥 {grade} - {group}: "
            f"{count}/{GROUP_LIMIT} طالب"
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submitted:
        return

    name = clean_text(name)
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

    if group_full(
        grade,
        group,
    ):

        st.error(
            f"❌ {group} وصلت للحد الأقصى "
            f"وهو {GROUP_LIMIT} طالب."
        )

        return

    conn = db()

    try:

        # -------------------------------------------------
        # هل الرقم مسجل بالفعل؟
        # -------------------------------------------------

        existing = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            LIMIT 1
            """,
            (phone,),
        ).fetchone()

        if existing:

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
                "✅ هذا الرقم مسجل بالفعل، تم فتح حساب الطالب."
            )

            st.rerun()

        # -------------------------------------------------
        # تسجيل طالب جديد
        # -------------------------------------------------

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

        try:
            conn.rollback()
        except Exception:
            pass

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    except Exception as e:

        try:
            conn.rollback()
        except Exception:
            pass

        st.error(
            f"❌ حدث خطأ أثناء التسجيل: {e}"
        )

    finally:

        safe_close(conn)


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    student_id = (
        st.session_state.get(
            "student_id"
        )
    )

    query_student = (
        st.query_params.get(
            "student"
        )
    )

    # -----------------------------------------------------
    # استعادة الطالب من الرابط
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # لو مفيش طالب
    # -----------------------------------------------------

    if student_id is None:

        student_registration()

        return

    # -----------------------------------------------------
    # جلب الطالب
    # -----------------------------------------------------

    conn = db()

    try:

        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()

    except Exception:

        student = None

    finally:

        safe_close(conn)

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

    # -----------------------------------------------------
    # بيانات الطالب
    # -----------------------------------------------------

    st.success(
        f"👨‍🎓 {student['name']} | "
        f"{student['grade']} | "
        f"{student['group_name']}"
    )

    lesson_token = (
        st.query_params.get(
            "lesson"
        )
    )

    lesson = None

    # -----------------------------------------------------
    # لو الطالب دخل من رابط حصة
    # -----------------------------------------------------

    if lesson_token:

        token = extract_token(
            lesson_token
        )

        if token:

            conn = db()

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

            except Exception:

                lesson = None

            finally:

                safe_close(conn)

    # -----------------------------------------------------
    # لو مفيش رابط، شوف الحصة المفتوحة
    # -----------------------------------------------------

    if lesson is None:

        lesson = active_lesson()

    # -----------------------------------------------------
    # مفيش حصة
    # -----------------------------------------------------

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        st.write(
            "عندما يبدأ المدرس الحصة، افتح رابط الحصة الذي أرسله لك."
        )

        return

    # -----------------------------------------------------
    # التأكد من الصف والمجموعة
    # -----------------------------------------------------

    if (
        lesson["grade"]
        != student["grade"]
        or
        lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            "⚠️ هذه الحصة ليست مخصصة لصفك أو مجموعتك."
        )

        return

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

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
        f"🕐 بداية الحصة: {lesson['created_at']}"
    )

    # -----------------------------------------------------
    # هل حضر بالفعل؟
    # -----------------------------------------------------

    conn = db()

    try:

        already = conn.execute(
            """
            SELECT marked_at
            FROM attendance
            WHERE lesson_id = ?
            AND student_id = ?
            LIMIT 1
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

    except Exception:

        already = None

    finally:

        safe_close(conn)

    if already:

        st.success(
            f"✅ تم تسجيل حضورك بالفعل "
            f"بتاريخ ووقت: {already['marked_at']}"
        )

        return

    # -----------------------------------------------------
    # تعليمات
    # -----------------------------------------------------

    st.info(
        """
        📷 لتسجيل الحضور:
        
        1️⃣ اضغط الكاميرا.
        
        2️⃣ وجّه الكاميرا إلى QR الخاص بهذه الحصة.
        
        3️⃣ انتظر تسجيل الحضور.
        """
    )

    # -----------------------------------------------------
    # QR Scanner
    # -----------------------------------------------------

    photo = st.camera_input(
        "📷 امسح QR الحصة",
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

                حاول تقريب الكاميرا،
                وتأكد أن الكود كامل وواضح.
                """
            )

        else:

            token = extract_token(
                raw_value
            )

            if not token:

                st.error(
                    "❌ هذا ليس QR خاص بمنصة الحضور."
                )

            else:

                ok, message = (
                    register_attendance(
                        token,
                        student_id,
                    )
                )

                if ok:

                    st.success(
                        message
                    )

                    st.balloons()

                    st.rerun()

                else:

                    st.error(
                        message
                    )

    # -----------------------------------------------------
    # إدخال الرابط يدويًا كحل احتياطي
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "🔗 لم تعمل الكاميرا؟"
    )

    manual_value = st.text_input(
        "الصق رابط الحصة أو كود QR هنا",
        key=f"manual_qr_{lesson['id']}",
        placeholder="https://... ?page=student&lesson=...",
    )

    if st.button(
        "✅ تسجيل الحضور بالكود",
        key=f"manual_btn_{lesson['id']}",
        use_container_width=True,
    ):

        token = extract_token(
            manual_value
        )

        if not token:

            st.error(
                "❌ الرابط أو الكود غير صحيح."
            )

        else:

            ok, message = (
                register_attendance(
                    token,
                    student_id,
                )
            )

            if ok:

                st.success(
                    message
                )

                st.rerun()

            else:

                st.error(
                    message
                )


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    st.info(
        "🔐 هذه الصفحة خاصة بالمدرس."
    )

    password = st.text_input(
        "🔐 كلمة مرور المدرس",
        type="password",
        placeholder="اكتب كلمة المرور",
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

    active = active_lesson()

    if active:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حاليًا:

            🎓 {active['grade']}

            👥 {active['group_name']}

            📚 {active['lesson_name']}

            🕐 {active['created_at']}
            """
        )

        total, present, absent = (
            lesson_stats(
                active["id"]
            )
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "👨‍🎓 إجمالي",
            total,
        )

        c2.metric(
            "✅ حضر",
            present,
        )

        c3.metric(
            "❌ غاب",
            absent,
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية",
            use_container_width=True,
        ):

            if end_lesson(
                active["id"]
            ):

                st.success(
                    "✅ تم إنهاء الحصة وحفظها."
                )

                st.rerun()

            else:

                st.error(
                    "❌ لم يتم إنهاء الحصة."
                )

        return

    # -----------------------------------------------------
    # اختيار الصف
    # -----------------------------------------------------

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="create_grade",
    )

    # -----------------------------------------------------
    # عرض المجموعات الثلاث
    # -----------------------------------------------------

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

        remaining = max(
            0,
            GROUP_LIMIT - count,
        )

        cols[i].metric(
            group,
            f"{count}/{GROUP_LIMIT}",
            f"متبقي {remaining}",
        )

    # -----------------------------------------------------
    # اختيار المجموعة
    # -----------------------------------------------------

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
        f"👨‍🎓 عدد الطلاب في "
        f"{grade} - {group}: "
        f"{selected_count}/{GROUP_LIMIT}"
    )

    if selected_count == 0:

        st.warning(
            """
            ⚠️ لا يوجد طلاب مسجلون في هذه المجموعة حاليًا.

            ابعت رابط تسجيل الطلاب لهم أولًا،
            وبعد ما يسجلوا هتظهر أعدادهم هنا.
            """
        )

    # -----------------------------------------------------
    # اسم الحصة
    # -----------------------------------------------------

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="lesson_name",
    )

    # -----------------------------------------------------
    # بدء الحصة
    # -----------------------------------------------------

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if selected_count <= 0:

            st.error(
                "❌ لا يمكن بدء الحصة لأن المجموعة لا تحتوي على طلاب."
            )

            return

        success, result = (
            create_lesson(
                lesson_name,
                grade,
                group,
            )
        )

        if not success:

            st.error(
                f"❌ لم يتم إنشاء الحصة:\n\n{result}"
            )

            return

        st.success(
            "🎉 تم إنشاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# CURRENT LESSON
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = active_lesson()

    if not lesson:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    total, present, absent = (
        lesson_stats(
            lesson["id"]
        )
    )

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي طلاب المجموعة",
        total,
    )

    c2.metric(
        "✅ الطلاب الذين سجلوا حضور",
        present,
    )

    c3.metric(
        "❌ الطلاب الغائبون حاليًا",
        absent,
    )

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"📚 **اسم الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"📅 **تاريخ ووقت البداية:** {lesson['created_at']}"
    )

    # -----------------------------------------------------
    # رابط الحصة
    # -----------------------------------------------------

    lesson_link = make_lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الحصة للطلاب"
    )

    st.code(
        lesson_link,
        language="text",
    )

    st.success(
        """
        📱 ابعت الرابط ده لطلاب المجموعة.
        الرابط يفتح مباشرة صفحة الطالب الخاصة بهذه الحصة.
        """
    )

    # -----------------------------------------------------
    # QR
    # -----------------------------------------------------

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
    # هنا QR يحتوي رابط الحصة الكامل
    # وليس Token فقط.
    # وبالتالي الطالب عندما يمسحه يحصل على
    # رابط واضح يحتوي page=student و lesson=TOKEN.

    qr.add_data(
        lesson_link
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
        caption="📷 QR الحصة - امسحه من موبايل الطالب",
        width=350,
    )

    # -----------------------------------------------------
    # الطلاب والحضور
    # -----------------------------------------------------

    st.subheader(
        "👨‍🎓 حضور وغياب الطلاب"
    )

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                s.id,
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

            ORDER BY s.name COLLATE NOCASE
            """,
            (lesson["id"],),
        ).fetchall()

    except Exception as e:

        rows = []

        st.error(
            f"❌ تعذر تحميل الطلاب: {e}"
        )

    finally:

        safe_close(conn)

    data = []

    for index, row in enumerate(
        rows,
        start=1,
    ):

        data.append(
            {
                "رقم": index,
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت تسجيل الحضور":
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

    else:

        st.info(
            "لا يوجد طلاب داخل قائمة هذه الحصة."
        )

    # -----------------------------------------------------
    # تحديث / إنهاء
    # -----------------------------------------------------

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

            if end_lesson(
                lesson["id"]
            ):

                st.success(
                    """
                    ✅ تم إنهاء الحصة.

                    تم حفظ:
                    • إجمالي الطلاب
                    • الحضور
                    • الغياب
                    • الصف
                    • المجموعة
                    • اسم الحصة
                    • تاريخ ووقت البداية
                    • تاريخ ووقت النهاية
                    """
                )

                st.rerun()

            else:

                st.error(
                    "❌ حدث خطأ أثناء حفظ الحصة."
                )


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.subheader(
        "📋 سجل الحصص المحفوظة"
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

    except Exception as e:

        lessons = []

        st.error(
            f"❌ تعذر تحميل التقارير: {e}"
        )

    finally:

        safe_close(conn)

    if not lessons:

        st.info(
            "📋 لا توجد حصص محفوظة حتى الآن."
        )

        return

    # -----------------------------------------------------
    # قائمة الحصص
    # -----------------------------------------------------

    options = {}

    for lesson in lessons:

        ended = (
            lesson["ended_at"]
            or "-"
        )

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"بدأ: {lesson['created_at']} | "
            f"انتهى: {ended}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "📚 اختر الحصة التي تريد تقريرها",
        list(options.keys()),
    )

    lesson_id = options[
        selected
    ]

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    total, present, absent = (
        lesson_stats(
            lesson_id
        )
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total,
    )

    c2.metric(
        "✅ سجل حضور",
        present,
    )

    c3.metric(
        "❌ غياب",
        absent,
    )

    # -----------------------------------------------------
    # تفاصيل الحصة
    # -----------------------------------------------------

    selected_lesson = None

    conn = db()

    try:

        selected_lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE id = ?
            LIMIT 1
            """,
            (lesson_id,),
        ).fetchone()

    finally:

        safe_close(conn)

    if selected_lesson:

        st.write(
            f"🎓 **الصف:** "
            f"{selected_lesson['grade']}"
        )

        st.write(
            f"👥 **المجموعة:** "
            f"{selected_lesson['group_name']}"
        )

        st.write(
            f"📚 **الحصة:** "
            f"{selected_lesson['lesson_name']}"
        )

        st.write(
            f"📅 **بدأت:** "
            f"{selected_lesson['created_at']}"
        )

        st.write(
            f"⏰ **انتهت:** "
            f"{selected_lesson['ended_at'] or '-'}"
        )

    # -----------------------------------------------------
    # الطلاب
    # -----------------------------------------------------

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

            ORDER BY s.name COLLATE NOCASE
            """,
            (lesson_id,),
        ).fetchall()

    finally:

        safe_close(conn)

    data = []

    for index, row in enumerate(
        rows,
        start=1,
    ):

        data.append(
            {
                "رقم": index,
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

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذه الحصة."
        )


# =========================================================
# STATISTICS
# =========================================================

def statistics_page():

    st.subheader(
        "📈 إحصائيات الصفوف والمجموعات"
    )

    # -----------------------------------------------------
    # إجمالي الطلاب
    # -----------------------------------------------------

    conn = db()

    try:

        total_students = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            """
        ).fetchone()["total"]

    except Exception:

        total_students = 0

  
