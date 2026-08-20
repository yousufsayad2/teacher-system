import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


# =========================================================
# إعدادات
# =========================================================

DB_FILE = "teacher_system_v5.db"
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
    page_title="نظام المدرس والطلاب",
    page_icon="🎓",
    layout="wide"
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1100px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .big-title {
        font-size: 42px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 10px;
    }

    .subtitle {
        text-align: center;
        font-size: 20px;
        margin-bottom: 30px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# أدوات عامة
# =========================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
        120000
    )

    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):

    try:
        salt_hex, digest_hex = stored.split(":")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            120000
        )

        return secrets.compare_digest(
            digest.hex(),
            digest_hex
        )

    except Exception:
        return False


# =========================================================
# إنشاء قاعدة البيانات من الصفر
# =========================================================

def init_db():

    conn = db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # settings
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
    # students
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
    # lessons
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
    # attendance
    # -----------------------------------------------------

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TEXT NOT NULL,

            UNIQUE(lesson_id, student_id),

            FOREIGN KEY(lesson_id)
                REFERENCES lessons(id),

            FOREIGN KEY(student_id)
                REFERENCES students(id)
        )
        """
    )

    # -----------------------------------------------------
    # إضافة الأعمدة لو كانت قاعدة البيانات موجودة
    # -----------------------------------------------------

    # students
    student_columns = {
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(students)"
        ).fetchall()
    }

    if "parent_phone" not in student_columns:
        cur.execute(
            "ALTER TABLE students ADD COLUMN parent_phone TEXT"
        )

    # lessons
    lesson_columns = {
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(lessons)"
        ).fetchall()
    }

    if "ended_at" not in lesson_columns:
        cur.execute(
            "ALTER TABLE lessons ADD COLUMN ended_at TEXT"
        )

    if "active" not in lesson_columns:
        cur.execute(
            "ALTER TABLE lessons ADD COLUMN active INTEGER DEFAULT 1"
        )

    if "token" not in lesson_columns:
        cur.execute(
            "ALTER TABLE lessons ADD COLUMN token TEXT"
        )

        # إنشاء Tokens للحصص القديمة إن وجدت
        old_lessons = cur.execute(
            """
            SELECT id
            FROM lessons
            WHERE token IS NULL
               OR token = ''
            """
        ).fetchall()

        for lesson in old_lessons:
            cur.execute(
                """
                UPDATE lessons
                SET token = ?
                WHERE id = ?
                """,
                (
                    secrets.token_urlsafe(32),
                    lesson["id"]
                )
            )

    # -----------------------------------------------------
    # كلمة مرور المدرس
    # -----------------------------------------------------

    row = cur.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        ("teacher_password_hash",)
    ).fetchone()

    if row is None:

        cur.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            """,
            (
                "teacher_password_hash",
                hash_password(
                    DEFAULT_TEACHER_PASSWORD
                )
            )
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
        (key,)
    ).fetchone()

    conn.close()

    return row["value"] if row else None


def set_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def get_student(student_id):

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    conn.close()

    return row


def get_student_by_phone(phone):

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE phone = ?
        """,
        (phone,)
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
        SELECT
            id,
            grade,
            lesson_name,
            created_at,
            ended_at,
            active,
            token

        FROM lessons

        WHERE active = 1

        ORDER BY id DESC

        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


# =========================================================
# إغلاق الحصص القديمة
# =========================================================

def close_active_lessons():

    conn = db()

    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = ?

        WHERE active = 1
        """,
        (now(),)
    )

    conn.commit()
    conn.close()


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson(grade, lesson_name):

    # إغلاق أي حصة مفتوحة
    close_active_lessons()

    token = secrets.token_urlsafe(32)

    conn = db()

    cur = conn.execute(
        """
        INSERT INTO lessons
        (
            grade,
            lesson_name,
            created_at,
            ended_at,
            active,
            token
        )

        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            grade,
            lesson_name,
            now(),
            None,
            1,
            token
        )
    )

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id


# =========================================================
# إنهاء حصة
# =========================================================

def finish_lesson(lesson_id):

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
            lesson_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# تسجيل الحضور
# =========================================================

def mark_attendance(token, student_id):

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons

        WHERE token = ?

        AND active = 1

        LIMIT 1
        """,
        (token,)
    ).fetchone()

    if lesson is None:

        conn.close()

        return (
            False,
            "❌ QR غير صالح أو الحصة انتهت."
        )

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    if student is None:

        conn.close()

        return (
            False,
            "❌ الطالب غير موجود."
        )

    # الطالب لازم يكون في نفس صف الحصة
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست لصفك."
        )

    # هل سجل قبل كده؟
    existing = conn.execute(
        """
        SELECT id
        FROM attendance

        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student_id
        )
    ).fetchone()

    if existing:

        conn.close()

        return (
            True,
            "✅ تم تسجيل حضورك بالفعل."
        )

    # تسجيل الحضور
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
            now()
        )
    )

    conn.commit()
    conn.close()

    return (
        True,
        "🎉 تم تسجيل حضورك بنجاح."
    )


# =========================================================
# قراءة QR
# =========================================================

def decode_qr(uploaded):

    if uploaded is None:
        return None

    try:

        data = np.frombuffer(
            uploaded.getvalue(),
            dtype=np.uint8
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        value, points, _ = detector.detectAndDecode(
            image
        )

        if value:
            return value.strip()

    except Exception:
        return None

    return None


# =========================================================
# رابط المدرس
# =========================================================

def teacher_url():

    try:

        base = st.context.url

        parsed = urlparse(base)

        query = parse_qs(parsed.query)

        query["page"] = ["teacher"]

        new_query = urlencode(
            query,
            doseq=True
        )

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                ""
            )
        )

    except Exception:

        return "?page=teacher"


# =========================================================
# Header
# =========================================================

def header(title, subtitle=""):

    st.markdown(
        f"""
        <div class="big-title">
            {title}
        </div>
        """,
        unsafe_allow_html=True
    )

    if subtitle:

        st.markdown(
            f"""
            <div class="subtitle">
                {subtitle}
            </div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    header(
        "🎓 نظام الحضور الذكي",
        "صفحة الطالب"
    )

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    # محاولة استرجاع الطالب من الرابط
    if student_id is None and query_student:

        try:

            student = get_student(
                int(query_student)
            )

            if student:

                student_id = student["id"]

                st.session_state.student_id = student_id

        except Exception:
            pass

    # =====================================================
    # تسجيل الطالب أول مرة
    # =====================================================

    if student_id is None:

        st.subheader(
            "📝 تسجيل الطالب على المنصة"
        )

        st.info(
            "سجل بياناتك مرة واحدة فقط، وبعدها لن تحتاج لإعادة التسجيل."
        )

        with st.form("student_form"):

            name = st.text_input(
                "اسم الطالب"
            )

            phone = st.text_input(
                "رقم هاتف الطالب"
            )

            parent_phone = st.text_input(
                "رقم هاتف ولي الأمر"
            )

            grade = st.selectbox(
                "الصف",
                GRADES
            )

            submit = st.form_submit_button(
                "✅ تسجيل الطالب",
                use_container_width=True
            )

        if submit:

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

            # ---------------------------------------------
            # الرقم موجود بالفعل
            # ---------------------------------------------

            old_student = get_student_by_phone(
                phone
            )

            if old_student:

                if old_student["grade"] != grade:

                    st.error(
                        "❌ هذا الرقم مسجل بالفعل في صف آخر."
                    )

                    return

                st.session_state.student_id = (
                    old_student["id"]
                )

                st.query_params["student"] = (
                    str(old_student["id"])
                )

                st.success(
                    "✅ تم العثور على حسابك القديم."
                )

                st.rerun()

            # ---------------------------------------------
            # طالب جديد
            # ---------------------------------------------

            conn = db()

            try:

                cur = conn.execute(
                    """
                    INSERT INTO students
                    (
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
                        now()
                    )
                )

                conn.commit()

                new_id = cur.lastrowid

                st.session_state.student_id = new_id

                st.query_params["student"] = (
                    str(new_id)
                )

                st.success(
                    "🎉 تم تسجيل الطالب بنجاح."
                )

                st.rerun()

            except sqlite3.IntegrityError:

                st.error(
                    "❌ رقم الهاتف مستخدم بالفعل."
                )

            finally:

                conn.close()

        return

    # =====================================================
    # بيانات الطالب
    # =====================================================

    student = get_student(
        student_id
    )

    if student is None:

        st.session_state.pop(
            "student_id",
            None
        )

        st.query_params.clear()

        st.rerun()

    st.success(
        f"👨‍🎓 أهلاً {student['name']}"
    )

    st.write(
        f"🎓 الصف: **{student['grade']}**"
    )

    st.write(
        f"🆔 رقم الطالب: **{student['id']}**"
    )

    # =====================================================
    # الحصة
    # =====================================================

    if st.button(
        "🔄 تحديث الصفحة",
        use_container_width=True
    ):

        st.rerun()

    lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.warning(
            f"⚠️ توجد حصة حاليًا للـ {lesson['grade']} وليست لصفك."
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 بدأت: {lesson['created_at']}"
    )

    # =====================================================
    # هل حضر بالفعل؟
    # =====================================================

    conn = db()

    attendance = conn.execute(
        """
        SELECT
            id,
            marked_at

        FROM attendance

        WHERE lesson_id = ?

        AND student_id = ?
        """,
        (
            lesson["id"],
            student_id
        )
    ).fetchone()

    conn.close()

    if attendance:

        st.success(
            f"""
            ✅ تم تسجيل حضورك.

            🕐 وقت الحضور:
            {attendance['marked_at']}
            """
        )

        return

    # =====================================================
    # الكاميرا لا تفتح تلقائيًا
    # =====================================================

    st.subheader(
        "📷 تسجيل الحضور"
    )

    if "scanner_open" not in st.session_state:

        st.session_state.scanner_open = False

    if not st.session_state.scanner_open:

        st.info(
            "اضغط على الزر لفتح الكاميرا."
        )

        if st.button(
            "📷 فتح الكاميرا ومسح QR",
            use_container_width=True
        ):

            st.session_state.scanner_open = True

            st.rerun()

        return

    # =====================================================
    # فتح الكاميرا
    # =====================================================

    st.info(
        "وجّه الكاميرا إلى QR الموجود عند المدرس."
    )

    photo = st.camera_input(
        "📷 امسح QR الحضور",
        key="attendance_camera"
    )

    if photo is not None:

        token = decode_qr(
            photo
        )

        if token is None:

            st.error(
                "❌ لم يتم التعرف على QR. حاول تصويره بشكل أوضح."
            )

        else:

            ok, message = mark_attendance(
                token,
                student_id
            )

            if ok:

                st.success(
                    message
                )

                st.session_state.scanner_open = False

                st.rerun()

            else:

                st.error(
                    message
                )

    if st.button(
        "❌ إغلاق الكاميرا",
        use_container_width=True
    ):

        st.session_state.scanner_open = False

        st.rerun()


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    header(
        "👨‍🏫 صفحة المدرس",
        "تسجيل دخول المدرس"
    )

    password = st.text_input(
        "🔐 كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "🔑 دخول المدرس",
        use_container_width=True
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if stored and verify_password(
            password,
            stored
        ):

            st.session_state.teacher_logged_in = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    current = active_lesson()

    # =====================================================
    # لو فيه حصة مفتوحة
    # =====================================================

    if current is not None:

        st.warning(
            "⚠️ توجد حصة مفتوحة بالفعل."
        )

        st.write(
            f"📚 الحصة: **{current['lesson_name']}**"
        )

        st.write(
            f"🎓 الصف: **{current['grade']}**"
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية",
            use_container_width=True
        ):

            finish_lesson(
                current["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    # =====================================================
    # إنشاء حصة جديدة
    # =====================================================

    grade = st.selectbox(
        "🎓 الصف",
        GRADES
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية"
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True
    ):

        lesson_name = lesson_name.strip()

        if not lesson_name:
            lesson_name = "الحصة الحالية"

        create_lesson(
            grade,
            lesson_name
        )

        st.success(
            "🎉 بدأت الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصة الحالية
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة."
        )

        return

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

    # =====================================================
    # الطلاب
    # =====================================================

    conn = db()

    students = conn.execute(
        """
        SELECT *
        FROM students

        WHERE grade = ?

        ORDER BY name
        """,
        (lesson["grade"],)
    ).fetchall()

    attendance_rows = conn.execute(
        """
        SELECT
            student_id,
            marked_at

        FROM attendance

        WHERE lesson_id = ?
        """,
        (lesson["id"],)
    ).fetchall()

    conn.close()

    attendance_map = {
        row["student_id"]: row["marked_at"]
        for row in attendance_rows
    }

    total = len(students)
    present = len(attendance_map)
    absent = total - present

    # =====================================================
    # الأرقام
    # =====================================================

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total
    )

    c2.metric(
        "✅ الحاضرون",
        present
    )

    c3.metric(
        "❌ الغائبون",
        absent
    )

    st.divider()

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📱 QR الحضور"
    )

    qr = qrcode.make(
        lesson["token"]
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        caption="الطلاب يمسحون هذا الكود",
        width=320
    )

    # =====================================================
    # تحديث
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True
    ):

        st.rerun()

    st.divider()

    # =====================================================
    # جدول الطلاب
    # =====================================================

    st.subheader(
        "📋 حالة الطلاب"
    )

    data = []

    for student in students:

        if student["id"] in attendance_map:

            status = "✅ حاضر"

            time = attendance_map[
                student["id"]
            ]

        else:

            status = "❌ غائب"

            time = "-"

        data.append(
            {
                "الطالب": student["name"],
                "الهاتف": student["phone"],
                "الحالة": status,
                "وقت الحضور": time
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    st.divider()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    if st.button(
        "⛔ إنهاء الحصة",
        use_container_width=True
    ):

        finish_lesson(
            lesson["id"]
        )

        st.session_state.finished_lesson_id = (
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
        "👨‍🎓 الطلاب"
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

        WHERE grade IN (
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )

        ORDER BY id DESC
        """,
        tuple(GRADES)
    ).fetchall()

    conn.close()

    st.metric(
        "إجمالي الطلاب",
        len(rows)
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
                "هاتف ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "تاريخ التسجيل": row["created_at"]
            }
        )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 تقارير الحصص"
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

    options = {}

    for lesson in lessons:

        label = (
            f"{lesson['lesson_name']} | "
            f"{lesson['grade']} | "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys())
    )

    lesson_id = options[selected]

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (lesson_id,)
    ).fetchone()

    students = conn.execute(
        """
        SELECT *
        FROM students
        WHERE grade = ?
        ORDER BY name
        """,
        (lesson["grade"],)
    ).fetchall()

    attendance = conn.execute(
        """
        SELECT
            student_id,
            marked_at

        FROM attendance

        WHERE lesson_id = ?
        """,
        (lesson_id,)
    ).fetchall()

    conn.close()

    attendance_map = {
        row["student_id"]: row["marked_at"]
        for row in attendance
    }

    total = len(students)
    present = len(attendance_map)
    absent = total - present

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total
    )

    c2.metric(
        "✅ حضر",
        present
    )

    c3.metric(
        "❌ غاب",
        absent
    )

    if lesson["ended_at"]:

        st.write(
            f"⏱️ **انتهت الحصة:** {lesson['ended_at']}"
        )

    st.divider()

    report = []

    for student in students:

        if student["id"] in attendance_map:

            status = "✅ حضر"

            attendance_time = attendance_map[
                student["id"]
            ]

        else:

            status = "❌ غائب"

            attendance_time = "-"

        report.append(
            {
                "الاسم": student["name"],
                "الهاتف": student["phone"],
                "الحالة": status,
                "وقت الحضور": attendance_time
            }
        )

    if report:

        st.dataframe(
            report,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# الإعدادات
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    with st.form(
        "password_form"
    ):

        old = st.text_input(
            "كلمة المرور الحالية",
            type="password"
        )

        new = st.text_input(
            "كلمة المرور الجديدة",
            type="password"
        )

        confirm = st.text_input(
            "تأكيد كلمة المرور",
            type="password"
        )

        save = st.form_submit_button(
            "🔐 تغيير كلمة المرور",
            use_container_width=True
        )

    if save:

        stored = get_setting(
            "teacher_password_hash"
        )

        if not verify_password(
            old,
            stored
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

        elif len(new) < 4:

            st.error(
                "❌ كلمة المرور لازم تكون 4 أحرف أو أرقام على الأقل."
            )

        elif new != confirm:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

        else:

            set_setting(
                "teacher_password_hash",
                hash_password(new)
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
        False
    ):

        teacher_login()

        return

    header(
        "👨‍🏫 لوحة تحكم المدرس"
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "📋 التقارير",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        create_lesson_page()

    with tabs[1]:

        current_lesson_page()

    with tabs[2]:

        students_page()

    with tabs[3]:

        reports_page()

    with tabs[4]:

        settings_page()

    st.divider()

    st.subheader(
        "🔗 رابط صفحة المدرس"
    )

    st.code(
        teacher_url(),
        language="text"
    )


# =========================================================
# تشغيل
# =========================================================

def main():

    # مهم جدًا:
    # قاعدة البيانات يتم تجهيزها قبل أي صفحة
    init_db()

    page = st.query_params.get(
        "page",
        "student"
    )

    if page == "teacher":

        teacher_dashboard()

    else:

        student_page()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
