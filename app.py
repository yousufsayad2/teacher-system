import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
from datetime import datetime


# =========================================================
# إعدادات النظام
# =========================================================

DB_FILE = "attendance_platform.db"

DEFAULT_TEACHER_PASSWORD = "1234"

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]


# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1100px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .main-title {
        font-size: 48px;
        font-weight: 900;
        text-align: center;
        margin-bottom: 5px;
    }

    .main-subtitle {
        text-align: center;
        font-size: 23px;
        margin-bottom: 30px;
    }

    .student-link {
        padding: 18px;
        border-radius: 15px;
        background: rgba(50, 120, 200, 0.15);
        font-size: 18px;
        word-break: break-all;
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
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    return conn


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =========================================================
# كلمة المرور
# =========================================================

def hash_password(password, salt=None):

    if salt is None:
        salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120000,
    )

    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):

    try:

        salt_hex, digest_hex = stored.split(":")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            120000,
        )

        return secrets.compare_digest(
            digest.hex(),
            digest_hex,
        )

    except Exception:
        return False


# =========================================================
# إعداد قاعدة البيانات
# =========================================================

def init_db():

    conn = db()

    cur = conn.cursor()

    # -----------------------------------------------------
    # الإعدادات
    # -----------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # -----------------------------------------------------
    # الطلاب
    # -----------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT,
            grade TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # -----------------------------------------------------
    # الحصص
    # -----------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            token TEXT NOT NULL UNIQUE
        )
        """
    )

    # -----------------------------------------------------
    # الحضور
    # -----------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TEXT NOT NULL,

            UNIQUE (
                lesson_id,
                student_id
            ),

            FOREIGN KEY(lesson_id)
                REFERENCES lessons(id),

            FOREIGN KEY(student_id)
                REFERENCES students(id)
        )
        """
    )

    # -----------------------------------------------------
    # ترقية قاعدة البيانات القديمة
    # -----------------------------------------------------

    columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(lessons)"
        ).fetchall()
    ]

    if "ended_at" not in columns:

        cur.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN ended_at TEXT
            """
        )

    # -----------------------------------------------------
    # كلمة مرور المدرس
    # -----------------------------------------------------

    password_row = cur.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        ("teacher_password_hash",),
    ).fetchone()

    if password_row is None:

        cur.execute(
            """
            INSERT INTO settings (
                key,
                value
            )

            VALUES (?, ?)
            """,
            (
                "teacher_password_hash",
                hash_password(
                    DEFAULT_TEACHER_PASSWORD
                ),
            ),
        )

    conn.commit()

    conn.close()


# =========================================================
# Settings
# =========================================================

def get_setting(key):

    conn = db()

    row = conn.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,),
    ).fetchone()

    conn.close()

    if row:
        return row["value"]

    return None


def set_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT INTO settings (
            key,
            value
        )

        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value
        """,
        (
            key,
            value,
        ),
    )

    conn.commit()

    conn.close()


# =========================================================
# الروابط
# =========================================================

def base_url():

    try:

        url = str(st.context.url)

        if "?" in url:
            url = url.split("?")[0]

        return url

    except Exception:

        return ""


def student_url():

    url = base_url()

    if url:
        return url + "?page=student"

    return "?page=student"


def teacher_url():

    url = base_url()

    if url:
        return url + "?page=teacher"

    return "?page=teacher"


# =========================================================
# بيانات الطالب
# =========================================================

def get_student(student_id):

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,),
    ).fetchone()

    conn.close()

    return row


# =========================================================
# الحصة الحالية
# =========================================================

def active_lesson():

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM lessons

        WHERE active = 1

        ORDER BY id DESC

        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


# =========================================================
# إنهاء جميع الحصص المفتوحة
# =========================================================

def close_all_active_lessons():

    conn = db()

    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = COALESCE(
                ended_at,
                ?
            )

        WHERE active = 1
        """,
        (now(),),
    )

    conn.commit()

    conn.close()


# =========================================================
# بدء حصة جديدة
# =========================================================

def start_new_lesson(grade, lesson_name):

    conn = db()

    try:

        # -------------------------------------------------
        # أهم نقطة:
        # إغلاق أي حصة قديمة أولاً
        # -------------------------------------------------

        conn.execute(
            """
            UPDATE lessons

            SET
                active = 0,
                ended_at = COALESCE(
                    ended_at,
                    ?
                )

            WHERE active = 1
            """,
            (now(),),
        )

        token = secrets.token_urlsafe(32)

        cur = conn.execute(
            """
            INSERT INTO lessons (
                grade,
                lesson_name,
                created_at,
                ended_at,
                active,
                token
            )

            VALUES (?, ?, ?, NULL, 1, ?)
            """,
            (
                grade,
                lesson_name,
                now(),
                token,
            ),
        )

        lesson_id = cur.lastrowid

        conn.commit()

        return lesson_id

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# =========================================================
# إنهاء حصة
# =========================================================

def end_lesson(lesson_id):

    conn = db()

    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = ?

        WHERE id = ?
        """,
        (
            now(),
            lesson_id,
        ),
    )

    # -----------------------------------------------------
    # أمان إضافي:
    # لا تسمح بوجود أكثر من حصة مفتوحة
    # -----------------------------------------------------

    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = COALESCE(
                ended_at,
                ?
            )

        WHERE active = 1
        AND id != ?
        """,
        (
            now(),
            lesson_id,
        ),
    )

    conn.commit()

    conn.close()


# =========================================================
# تسجيل طالب
# =========================================================

def register_student(
    name,
    phone,
    parent_phone,
    grade,
):

    conn = db()

    try:

        cur = conn.execute(
            """
            INSERT INTO students (
                name,
                phone,
                parent_phone,
                grade,
                created_at
            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                parent_phone,
                grade,
                now(),
            ),
        )

        conn.commit()

        return cur.lastrowid, None

    except sqlite3.IntegrityError:

        existing = conn.execute(
            """
            SELECT id
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

        conn.close()

        if existing:

            return existing["id"], "EXISTS"

        return None, "ERROR"

    except Exception:

        conn.rollback()

        conn.close()

        return None, "ERROR"

    finally:

        try:
            conn.close()
        except Exception:
            pass


# =========================================================
# تسجيل الحضور
# =========================================================

def mark_attendance(token, student_id):

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

        if lesson is None:

            return (
                False,
                "❌ QR غير صالح أو الحصة انتهت.",
            )

        student = conn.execute(
            """
            SELECT *
            FROM students

            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()

        if student is None:

            return (
                False,
                "❌ الطالب غير موجود.",
            )

        # -------------------------------------------------
        # الطالب لازم يكون في نفس الصف
        # -------------------------------------------------

        if student["grade"] != lesson["grade"]:

            return (
                False,
                "❌ هذه الحصة ليست لصفك.",
            )

        # -------------------------------------------------
        # منع تسجيل نفس الطالب مرتين
        # -------------------------------------------------

        existing = conn.execute(
            """
            SELECT id
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
                "✅ أنت مسجل حضور بالفعل في هذه الحصة.",
            )

        # -------------------------------------------------
        # تسجيل الحضور
        # -------------------------------------------------

        conn.execute(
            """
            INSERT INTO attendance (
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
            "✅ تم تسجيل حضورك بالفعل.",
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
# قراءة QR
# =========================================================

def decode_qr(uploaded_file):

    if uploaded_file is None:
        return None

    try:

        data = np.frombuffer(
            uploaded_file.getvalue(),
            dtype=np.uint8,
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR,
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        value, points, _ = detector.detectAndDecode(
            image
        )

        if value:
            return value.strip()

        return None

    except Exception:

        return None


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_statistics(lesson_id, grade):

    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS total

        FROM students

        WHERE grade = ?
        """,
        (grade,),
    ).fetchone()["total"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS total

        FROM attendance a

        INNER JOIN students s
        ON s.id = a.student_id

        WHERE a.lesson_id = ?
        AND s.grade = ?
        """,
        (
            lesson_id,
            grade,
        ),
    ).fetchone()["total"]

    absent = total - present

    conn.close()

    return total, present, absent


# =========================================================
# حالة الطلاب في الحصة
# =========================================================

def get_lesson_students(lesson_id, grade):

    conn = db()

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,
            s.grade,
            a.marked_at

        FROM students s

        LEFT JOIN attendance a
        ON
            a.student_id = s.id
            AND a.lesson_id = ?

        WHERE s.grade = ?

        ORDER BY s.name COLLATE NOCASE
        """,
        (
            lesson_id,
            grade,
        ),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# Header الطالب
# =========================================================

def student_header():

    st.markdown(
        """
        <div class="main-title">
            🎓 منصة الحضور
        </div>

        <div class="main-subtitle">
            واجهة الطالب
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# Header المدرس
# =========================================================

def teacher_header():

    st.markdown(
        """
        <div class="main-title">
            👨‍🏫 لوحة تحكم المدرس
        </div>

        <div class="main-subtitle">
            إدارة الحصص والحضور
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# صفحة تسجيل الطالب
# =========================================================

def student_registration():

    student_header()

    st.info(
        """
        📝 التسجيل يتم مرة واحدة فقط.

        بعد التسجيل، في كل حصة ستستخدم QR الخاص بالمدرس
        لتسجيل الحضور.
        """
    )

    with st.form("student_registration_form"):

        name = st.text_input(
            "👨‍🎓 اسم الطالب"
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "👨‍👩‍👦 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES,
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if submitted:

        name = name.strip()
        phone = phone.strip()
        parent_phone = parent_phone.strip()

        if not name:

            st.error(
                "❌ اكتب اسم الطالب."
            )

            return

        if not phone:

            st.error(
                "❌ اكتب رقم هاتف الطالب."
            )

            return

        student_id, result = register_student(
            name,
            phone,
            parent_phone,
            grade,
        )

        if result == "EXISTS":

            st.session_state.student_id = student_id

            st.success(
                "✅ الطالب مسجل بالفعل، تم فتح حسابه."
            )

            st.rerun()

        elif result is None:

            st.error(
                "❌ حدث خطأ أثناء التسجيل."
            )

        else:

            st.session_state.student_id = student_id

            st.success(
                "🎉 تم تسجيل الطالب بنجاح."
            )

            st.rerun()


# =========================================================
# صفحة حضور الطالب
# =========================================================

def student_attendance_page(student):

    student_header()

    st.success(
        f"👨‍🎓 أهلاً يا {student['name']}"
    )

    st.write(
        f"🎓 الصف: **{student['grade']}**"
    )

    st.write(
        f"🆔 رقم الطالب: **{student['id']}**"
    )

    st.divider()

    lesson = active_lesson()

    # -----------------------------------------------------
    # لا توجد حصة
    # -----------------------------------------------------

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة حالياً.

            عندما يبدأ المدرس الحصة، ستظهر هنا
            إمكانية تسجيل الحضور.
            """
        )

        if st.button(
            "🔄 تحديث",
            use_container_width=True,
        ):

            st.rerun()

        return

    # -----------------------------------------------------
    # الحصة ليست للطالب
    # -----------------------------------------------------

    if lesson["grade"] != student["grade"]:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حالياً،
            لكنها للصف: {lesson['grade']}

            أنت مسجل في: {student['grade']}
            """
        )

        if st.button(
            "🔄 تحديث",
            use_container_width=True,
        ):

            st.rerun()

        return

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

    st.subheader(
        "📚 الحصة الحالية"
    )

    st.write(
        f"**اسم الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**بدأت:** {lesson['created_at']}"
    )

    st.divider()

    # -----------------------------------------------------
    # حالة الكاميرا
    # -----------------------------------------------------

    if not st.session_state.get(
        "scanner_open",
        False,
    ):

        st.info(
            """
            📷 اضغط الزر عندما تكون مستعداً لمسح QR.

            الكاميرا **لن تفتح تلقائياً**.
            """
        )

        if st.button(
            "📷 تسجيل الحضور بالـ QR",
            use_container_width=True,
        ):

            st.session_state.scanner_open = True

            st.rerun()

        return

    # -----------------------------------------------------
    # الكاميرا مفتوحة فقط بعد الضغط
    # -----------------------------------------------------

    st.warning(
        "📷 وجّه الكاميرا إلى QR الخاص بالمدرس."
    )

    photo = st.camera_input(
        "مسح QR الحضور",
        key="student_qr_camera",
        resolution="720p",
    )

    # -----------------------------------------------------
    # إغلاق الكاميرا
    # -----------------------------------------------------

    if st.button(
        "❌ إغلاق الكاميرا",
        use_container_width=True,
    ):

        st.session_state.scanner_open = False

        st.rerun()

    # -----------------------------------------------------
    # معالجة الصورة
    # -----------------------------------------------------

    if photo is not None:

        token = decode_qr(photo)

        if not token:

            st.error(
                "❌ لم أستطع قراءة QR. حاول تصويره بوضوح."
            )

            return

        success, message = mark_attendance(
            token,
            student["id"],
        )

        if success:

            st.success(message)

            # -------------------------------------------------
            # إغلاق الكاميرا بعد نجاح الحضور
            # -------------------------------------------------

            st.session_state.scanner_open = False

            st.rerun()

        else:

            st.error(message)


# =========================================================
# صفحة الطالب الرئيسية
# =========================================================

def student_page():

    student_id = st.session_state.get(
        "student_id"
    )

    # -----------------------------------------------------
    # استرجاع الطالب من الرابط
    # -----------------------------------------------------

    query_student = st.query_params.get(
        "student"
    )

    if student_id is None and query_student:

        try:

            candidate = get_student(
                int(query_student)
            )

            if candidate:

                st.session_state.student_id = (
                    candidate["id"]
                )

                student_id = candidate["id"]

        except Exception:

            pass

    # -----------------------------------------------------
    # لو الطالب غير مسجل
    # -----------------------------------------------------

    if student_id is None:

        student_registration()

        return

    student = get_student(
        student_id
    )

    if student is None:

        st.session_state.pop(
            "student_id",
            None,
        )

        student_registration()

        return

    # -----------------------------------------------------
    # تثبيت الطالب في الرابط
    # -----------------------------------------------------

    try:

        st.query_params["student"] = str(
            student["id"]
        )

    except Exception:

        pass

    student_attendance_page(
        student
    )


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    teacher_header()

    st.info(
        "🔐 هذه الصفحة خاصة بالمدرس."
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password",
    )

    if st.button(
        "دخول المدرس",
        use_container_width=True,
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if stored and verify_password(
            password,
            stored,
        ):

            st.session_state.teacher_logged_in = True

            st.success(
                "✅ تم تسجيل الدخول."
            )

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# رابط الطالب
# =========================================================

def student_link_page():

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.write(
        """
        ابعت الرابط ده للطلاب.

        الطالب يفتحه ويسجل بياناته أول مرة فقط،
        وبعدها يستخدم نفس الرابط لتسجيل الحضور.
        """
    )

    link = student_url()

    st.code(
        link,
        language="text",
    )

    st.success(
        "📱 ده رابط الطالب — وليس رابط المدرس."
    )

    st.info(
        """
        الطالب:
        1️⃣ يفتح الرابط.
        2️⃣ يسجل بياناته أول مرة.
        3️⃣ بعد التسجيل يدخل على نفس الرابط.
        4️⃣ عند وجود حصة يضغط «تسجيل الحضور بالـ QR».
        5️⃣ يصور QR الموجود عند المدرس.
        """
    )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    current = active_lesson()

    # -----------------------------------------------------
    # لو فيه حصة مفتوحة
    # -----------------------------------------------------

    if current is not None:

        st.warning(
            "⚠️ توجد حصة مفتوحة حالياً."
        )

        st.write(
            f"📚 الحصة: {current['lesson_name']}"
        )

        st.write(
            f"🎓 الصف: {current['grade']}"
        )

        st.write(
            f"🕐 بدأت: {current['created_at']}"
        )

        st.divider()

        st.info(
            """
            يمكنك إنهاء الحصة الحالية.

            وبعد إنهائها ستتمكن من إنشاء حصة جديدة.
            """
        )

        if st.button(
            "🔴 إنهاء الحصة الحالية",
            use_container_width=True,
        ):

            end_lesson(
                current["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة الحالية."
            )

            st.rerun()

        return

    # -----------------------------------------------------
    # إنشاء حصة جديدة
    # -----------------------------------------------------

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        lesson_name = lesson_name.strip()

        if not lesson_name:

            lesson_name = "الحصة الحالية"

        try:

            start_new_lesson(
                grade,
                lesson_name,
            )

            st.success(
                "🎉 تم بدء الحصة بنجاح."
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"❌ حدث خطأ: {e}"
            )


# =========================================================
# صفحة الحصة الحالية للمدرس
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

    st.write(
        f"📚 **الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    st.divider()

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"],
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي طلاب الصف",
        total,
    )

    c2.metric(
        "✅ الحاضرون",
        present,
    )

    c3.metric(
        "❌ الغائبون",
        absent,
    )

    st.divider()

    # -----------------------------------------------------
    # QR
    # -----------------------------------------------------

    st.subheader(
        "📱 QR الحضور"
    )

    qr_image = qrcode.make(
        lesson["token"]
    )

    buffer = io.BytesIO()

    qr_image.save(
        buffer,
        format="PNG",
    )

    st.image(
        buffer.getvalue(),
        caption="الطلاب يمسحون هذا الكود",
        width=350,
    )

    st.divider()

    # -----------------------------------------------------
    # حالة الطلاب
    # -----------------------------------------------------

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"],
    )

    present_rows = [
        row
        for row in rows
        if row["marked_at"] is not None
    ]

    absent_rows = [
        row
        for row in rows
        if row["marked_at"] is None
    ]

    st.subheader(
        "📋 حالة طلاب الصف"
    )

    if rows:

        table = []

        for row in rows:

            if row["marked_at"]:

                status = "✅ حاضر"

                attendance_time = row[
                    "marked_at"
                ]

            else:

                status = "❌ غائب"

                attendance_time = "-"

            table.append(
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "الحالة": status,
                    "وقت الحضور": attendance_time,
                }
            )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    st.divider()

    # -----------------------------------------------------
    # تحديث
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True,
    ):

        st.rerun()

    # -----------------------------------------------------
    # إنهاء الحصة
    # -----------------------------------------------------

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True,
    ):

        end_lesson(
            lesson["id"]
        )

        st.success(
            "✅ تم إنهاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# صفحة الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون في المنصة"
    )

    conn = db()

    rows = conn.execute(
        """
        SELECT
            id,
            name,
            phone,
            parent_phone,
            grade,
            created_at

        FROM students

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "📊 إجمالي الطلاب في المنصة",
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
                "الطالب": row["name"],
                "هاتف الطالب": row["phone"],
                "هاتف ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "تاريخ التسجيل": row["created_at"],
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 التقارير"
    )

    conn = db()

    lessons = conn.execute(
        """
        SELECT *
        FROM lessons

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    if not lessons:

        st.info(
            "لا توجد حصص حتى الآن."
        )

        return

    lesson_options = {
        f"{row['lesson_name']} - {row['grade']} - {row['created_at']}":
        row["id"]
        for row in lessons
    }

    selected = st.selectbox(
        "اختر الحصة",
        list(lesson_options.keys()),
    )

    lesson_id = lesson_options[selected]

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (lesson_id,),
    ).fetchone()

    conn.close()

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"],
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

    st.write(
        f"📚 **الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    st.write(
        f"⛔ **انتهت:** {lesson['ended_at'] or 'مفتوحة'}"
    )

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"],
    )

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time_value = row["marked_at"]

        else:

            status = "❌ غائب"

            time_value = "-"

        table.append(
            {
                "الطالب": row["name"],
                "الصف": row["grade"],
                "الحالة": status,
                "وقت الحضور": time_value,
            }
        )

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# إعدادات المدرس
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    st.write(
        "🔐 تغيير كلمة مرور المدرس"
    )

    with st.form(
        "change_teacher_password"
    ):

        old_password = st.text_input(
            "كلمة المرور الحالية",
            type="password",
        )

        new_password = st.text_input(
            "كلمة المرور الجديدة",
            type="password",
        )

        confirm_password = st.text_input(
            "تأكيد كلمة المرور",
            type="password",
        )

        save = st.form_submit_button(
            "💾 حفظ كلمة المرور",
            use_container_width=True,
        )

    if save:

        stored = get_setting(
            "teacher_password_hash"
        )

        if not stored:

            st.error(
                "❌ لم يتم العثور على كلمة المرور."
            )

            return

        if not verify_password(
            old_password,
            stored,
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

            return

        if len(new_password) < 4:

            st.error(
                "❌ كلمة المرور الجديدة يجب أن تكون 4 أحرف/أرقام على الأقل."
            )

            return

        if new_password != confirm_password:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

            return

        set_setting(
            "teacher_password_hash",
            hash_password(
                new_password
            ),
        )

        st.success(
            "✅ تم تغيير كلمة المرور."
        )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher_logged_in",
        False,
    ):

        teacher_login()

        return

    teacher_header()

    # -----------------------------------------------------
    # تسجيل الخروج
    # -----------------------------------------------------

    if st.button(
        "🚪 تسجيل خروج",
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    st.divider()

    # -----------------------------------------------------
    # التبويبات
    # -----------------------------------------------------

    tabs = st.tabs(
        [
            "🔗 رابط الطلاب",
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "📋 التقارير",
            "⚙️ الإعدادات",
        ]
    )

    # -----------------------------------------------------
    # رابط الطالب
    # -----------------------------------------------------

    with tabs[0]:

        student_link_page()

    # -----------------------------------------------------
    # إنشاء الحصة
    # -----------------------------------------------------

    with tabs[1]:

        create_lesson_page()

    # -----------------------------------------------------
    # الحصة الحالية
    # -----------------------------------------------------

    with tabs[2]:

        current_lesson_page()

    # -----------------------------------------------------
    # الطلاب
    # -----------------------------------------------------

    with tabs[3]:

        students_page()

    # -----------------------------------------------------
    # التقارير
    # -----------------------------------------------------

    with tabs[4]:

        reports_page()

    # -----------------------------------------------------
    # الإعدادات
    # -----------------------------------------------------

    with tabs[5]:

        settings_page()

    # -----------------------------------------------------
    # رابط المدرس
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "👨‍🏫 رابط المدرس"
    )

    st.code(
        teacher_url(),
        language="text",
    )

    st.caption(
        "هذا الرابط خاص بالمدرس."
    )


# =========================================================
# تشغيل النظام
# =========================================================

def main():

    init_db()

    page = st.query_params.get(
        "page",
        "teacher",
    )

    # -----------------------------------------------------
    # صفحة الطالب
    # -----------------------------------------------------

    if page == "student":

        student_page()

        return

    # -----------------------------------------------------
    # أي شيء آخر = المدرس
    # -----------------------------------------------------

    teacher_dashboard()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
