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

DB_FILE = "teacher_system_final.db"
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
    initial_sidebar_state="collapsed",
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
        font-size: 45px;
        font-weight: 900;
        text-align: center;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 20px;
        opacity: 0.85;
        margin-bottom: 30px;
    }

    .small-note {
        text-align: center;
        opacity: 0.75;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def current_time():
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

    return (
        salt.hex()
        + ":"
        + digest.hex()
    )


def verify_password(password, stored):

    if not stored:
        return False

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
# إنشاء قاعدة البيانات
# =========================================================

def init_database():

    conn = get_db()

    cur = conn.cursor()

    # إعدادات
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # الطلاب
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

    # الحصص
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

    # الحضور
    cur.execute(
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

    # كلمة مرور المدرس
    row = cur.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        ("teacher_password_hash",),
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
                ),
            ),
        )

    conn.commit()
    conn.close()


# =========================================================
# Settings
# =========================================================

def get_setting(key):

    conn = get_db()

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


def save_setting(key, value):

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO settings
        (key, value)
        VALUES (?, ?)
        """,
        (key, value),
    )

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def get_student(student_id):

    conn = get_db()

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


def get_student_by_phone(phone):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE phone = ?
        """,
        (phone,),
    ).fetchone()

    conn.close()

    return row


def total_platform_students():

    conn = get_db()

    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM students
        """
    ).fetchone()

    conn.close()

    return row["total"]


def grade_students_count(grade):

    conn = get_db()

    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM students
        WHERE grade = ?
        """,
        (grade,),
    ).fetchone()

    conn.close()

    return row["total"]


# =========================================================
# الحصة الحالية
# =========================================================

def get_active_lesson():

    conn = get_db()

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
# إنهاء كل الحصص القديمة
# =========================================================

def close_all_active_lessons():

    conn = get_db()

    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = ?

        WHERE active = 1
        """,
        (current_time(),),
    )

    conn.commit()
    conn.close()


# =========================================================
# إنشاء حصة
# =========================================================

def start_new_lesson(grade, lesson_name):

    conn = get_db()

    # نقفل أي حصة قديمة بشكل إجباري
    conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = ?

        WHERE active = 1
        """,
        (current_time(),),
    )

    token = secrets.token_urlsafe(32)

    cursor = conn.execute(
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

        VALUES (?, ?, ?, NULL, 1, ?)
        """,
        (
            grade,
            lesson_name,
            current_time(),
            token,
        ),
    )

    lesson_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return lesson_id


# =========================================================
# إنهاء حصة
# =========================================================

def finish_lesson(lesson_id):

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE lessons

        SET
            active = 0,
            ended_at = ?

        WHERE id = ?
        AND active = 1
        """,
        (
            current_time(),
            lesson_id,
        ),
    )

    changed = cursor.rowcount

    conn.commit()
    conn.close()

    return changed > 0


# =========================================================
# تسجيل حضور
# =========================================================

def register_attendance(token, student_id):

    conn = get_db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
        """,
        (token,),
    ).fetchone()

    if lesson is None:

        conn.close()

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

        conn.close()

        return (
            False,
            "❌ الطالب غير موجود في المنصة.",
        )

    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست للصف الخاص بك.",
        )

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

        conn.close()

        return (
            True,
            "ℹ️ حضورك مسجل بالفعل.",
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
            current_time(),
        ),
    )

    conn.commit()
    conn.close()

    return (
        True,
        "🎉 تم تسجيل حضورك بنجاح.",
    )


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_statistics(lesson_id, grade):

    conn = get_db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM students
        WHERE grade = ?
        """,
        (grade,),
    ).fetchone()["c"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS c

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
    ).fetchone()["c"]

    conn.close()

    absent = max(total - present, 0)

    return total, present, absent


# =========================================================
# حالة الطلاب في الحصة
# =========================================================

def lesson_student_status(lesson_id, grade):

    conn = get_db()

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

        ON a.student_id = s.id

        AND a.lesson_id = ?

        WHERE s.grade = ?

        ORDER BY s.name
        """,
        (
            lesson_id,
            grade,
        ),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def make_qr(token):

    qr = qrcode.make(token)

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


def read_qr(uploaded_file):

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

        value, points, _ = (
            detector.detectAndDecode(image)
        )

        if value:
            return value.strip()

    except Exception:

        return None

    return None


# =========================================================
# رابط المدرس
# =========================================================

def teacher_page_url():

    try:

        base = st.context.url

        if "?" in base:
            base = base.split("?")[0]

        return (
            base
            + "?page=teacher"
        )

    except Exception:

        return "?page=teacher"


# =========================================================
# الهيدر
# =========================================================

def header(title, subtitle=""):

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
# الصفحة الرئيسية للطالب
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "واجهة الطالب",
    )

    # -----------------------------------------------------
    # استرجاع الطالب
    # -----------------------------------------------------

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    if student_id is None and query_student:

        try:

            candidate = get_student(
                int(query_student)
            )

            if candidate:

                student_id = candidate["id"]

                st.session_state.student_id = (
                    student_id
                )

        except Exception:

            pass

    # -----------------------------------------------------
    # تسجيل أول مرة
    # -----------------------------------------------------

    if student_id is None:

        st.info(
            "📝 سجل بياناتك مرة واحدة فقط، وبعدها ستستخدم نفس الحساب في الحضور."
        )

        st.subheader(
            "👨‍🎓 تسجيل الطالب"
        )

        with st.form(
            "student_register"
        ):

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
                GRADES,
            )

            register = st.form_submit_button(
                "✅ تسجيل الطالب",
                use_container_width=True,
            )

        if register:

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

            existing = get_student_by_phone(
                phone
            )

            if existing:

                st.session_state.student_id = (
                    existing["id"]
                )

                st.query_params["student"] = (
                    str(existing["id"])
                )

                st.success(
                    "✅ الطالب مسجل بالفعل، تم الدخول لحسابه."
                )

                st.rerun()

            conn = get_db()

            try:

                cursor = conn.execute(
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
                        current_time(),
                    ),
                )

                new_id = cursor.lastrowid

                conn.commit()

                st.session_state.student_id = (
                    new_id
                )

                st.query_params["student"] = (
                    str(new_id)
                )

                st.success(
                    "🎉 تم التسجيل بنجاح."
                )

                st.rerun()

            except sqlite3.IntegrityError:

                st.error(
                    "❌ رقم الهاتف مسجل بالفعل."
                )

            finally:

                conn.close()

        return

    # -----------------------------------------------------
    # بيانات الطالب
    # -----------------------------------------------------

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
        f"**الصف:** {student['grade']}"
    )

    st.write(
        f"**رقم الطالب:** {student['id']}"
    )

    st.divider()

    # -----------------------------------------------------
    # الحصة الحالية
    # -----------------------------------------------------

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        st.caption(
            "عندما يبدأ المدرس الحصة، ستظهر هنا إمكانية تسجيل الحضور."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.warning(
            "⏳ لا توجد حصة حالية لصفك."
        )

        return

    st.subheader(
        "📚 الحصة الحالية"
    )

    st.write(
        f"**الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**بدأت:** {lesson['created_at']}"
    )

    st.divider()

    # -----------------------------------------------------
    # لا تفتح الكاميرا تلقائياً
    # -----------------------------------------------------

    if st.session_state.get(
        "scanner_open",
        False
    ):

        st.subheader(
            "📷 مسح باركود الحضور"
        )

        st.write(
            "وجّه الكاميرا إلى QR الموجود عند المدرس."
        )

        photo = st.camera_input(
            "اضغط لفتح الكاميرا وتصوير QR",
            key="attendance_camera",
        )

        if photo is not None:

            token = read_qr(photo)

            if not token:

                st.error(
                    "❌ لم يتم التعرف على QR. حاول تصويره بشكل أوضح."
                )

            else:

                ok, message = register_attendance(
                    token,
                    student["id"],
                )

                if ok:

                    st.success(message)

                    st.session_state.scanner_open = False

                    st.rerun()

                else:

                    st.error(message)

        if st.button(
            "❌ إغلاق الكاميرا",
            use_container_width=True,
        ):

            st.session_state.scanner_open = False

            st.rerun()

    else:

        st.info(
            "📷 الكاميرا مغلقة حالياً."
        )

        if st.button(
            "📷 تسجيل الحضور بالـ QR",
            use_container_width=True,
        ):

            st.session_state.scanner_open = True

            st.rerun()


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    header(
        "👨‍🏫 صفحة المدرس",
        "دخول المدرس فقط",
    )

    st.warning(
        "🔐 هذه الصفحة خاصة بالمدرس."
    )

    password = st.text_input(
        "كلمة مرور المدرس",
        type="password",
    )

    if st.button(
        "🔑 دخول المدرس",
        use_container_width=True,
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if verify_password(
            password,
            stored,
        ):

            st.session_state.teacher_logged_in = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# إحصائيات عامة للمنصة
# =========================================================

def platform_statistics():

    conn = get_db()

    total_students = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

    total_lessons = conn.execute(
        """
        SELECT COUNT(*)
        FROM lessons
        """
    ).fetchone()[0]

    total_attendance = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        """
    ).fetchone()[0]

    conn.close()

    return (
        total_students,
        total_lessons,
        total_attendance,
    )


# =========================================================
# صفحة إنشاء حصة
# =========================================================

def create_lesson_page():

    st.header(
        "➕ إنشاء حصة جديدة"
    )

    active = get_active_lesson()

    if active:

        st.warning(
            "⚠️ توجد حصة مفتوحة حالياً."
        )

        st.write(
            f"**الحصة:** {active['lesson_name']}"
        )

        st.write(
            f"**الصف:** {active['grade']}"
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية وبدء حصة جديدة",
            use_container_width=True,
        ):

            finish_lesson(
                active["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة القديمة."
            )

            st.rerun()

        st.info(
            "يمكنك أيضاً الانتقال إلى تبويب «الحصة الحالية» وإنهائها."
        )

        return

    grade = st.selectbox(
        "الصف",
        GRADES,
    )

    lesson_name = st.text_input(
        "اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        lesson_name = lesson_name.strip()

        if not lesson_name:

            lesson_name = "الحصة الحالية"

        start_new_lesson(
            grade,
            lesson_name,
        )

        st.success(
            "🎉 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصة الحالية للمدرس
# =========================================================

def current_lesson_page():

    st.header(
        "📊 الحصة الحالية"
    )

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    total, present, absent = (
        lesson_statistics(
            lesson["id"],
            lesson["grade"],
        )
    )

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**وقت البداية:** {lesson['created_at']}"
    )

    st.divider()

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 طلاب الصف",
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

    qr_image = make_qr(
        lesson["token"]
    )

    st.image(
        qr_image,
        caption="الطلاب يمسحون هذا الكود",
        width=330,
    )

    st.divider()

    # -----------------------------------------------------
    # تحديث الحضور
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث الحضور الآن",
        use_container_width=True,
    ):

        st.rerun()

    # -----------------------------------------------------
    # حالة الطلاب
    # -----------------------------------------------------

    st.subheader(
        "📋 حالة طلاب الحصة"
    )

    rows = lesson_student_status(
        lesson["id"],
        lesson["grade"],
    )

    if rows:

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
                    "الحالة": status,
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
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
            "لا يوجد طلاب مسجلون في هذا الصف حتى الآن."
        )

    st.divider()

    # -----------------------------------------------------
    # إنهاء الحصة
    # -----------------------------------------------------

    st.subheader(
        "⛔ إنهاء الحصة"
    )

    st.warning(
        f"عند إنهاء الحصة سيعتبر {absent} طالباً غائباً من طلاب الصف المسجلين."
    )

    if st.button(
        "🔴 إنهاء الحصة نهائياً",
        use_container_width=True,
    ):

        success = finish_lesson(
            lesson["id"]
        )

        if success:

            st.success(
                "✅ تم إنهاء الحصة بنجاح. يمكنك الآن إنشاء حصة جديدة."
            )

            st.rerun()

        else:

            st.error(
                "❌ الحصة انتهت بالفعل."
            )


# =========================================================
# صفحة الطلاب
# =========================================================

def teacher_students_page():

    st.header(
        "👨‍🎓 الطلاب المسجلون"
    )

    total = total_platform_students()

    st.metric(
        "👥 إجمالي الطلاب في المنصة",
        total,
    )

    conn = get_db()

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
                "تاريخ التسجيل": row["created_at"],
            }
        )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.header(
        "📋 التقارير"
    )

    total_students, total_lessons, total_attendance = (
        platform_statistics()
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👥 الطلاب في المنصة",
        total_students,
    )

    c2.metric(
        "📚 عدد الحصص",
        total_lessons,
    )

    c3.metric(
        "✅ إجمالي عمليات الحضور",
        total_attendance,
    )

    st.divider()

    conn = get_db()

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

    for lesson in lessons:

        total, present, absent = (
            lesson_statistics(
                lesson["id"],
                lesson["grade"],
            )
        )

        status = (
            "🟢 مفتوحة"
            if lesson["active"]
            else "🔴 منتهية"
        )

        with st.expander(
            f"{status} — {lesson['lesson_name']} — {lesson['grade']}"
        ):

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "طلاب الصف",
                total,
            )

            c2.metric(
                "حاضر",
                present,
            )

            c3.metric(
                "غائب",
                absent,
            )

            st.write(
                f"بدأت: {lesson['created_at']}"
            )

            if lesson["ended_at"]:

                st.write(
                    f"انتهت: {lesson['ended_at']}"
                )

            rows = lesson_student_status(
                lesson["id"],
                lesson["grade"],
            )

            table = []

            for row in rows:

                table.append(
                    {
                        "الطالب": row["name"],
                        "الحالة": (
                            "✅ حاضر"
                            if row["marked_at"]
                            else "❌ غائب"
                        ),
                        "وقت الحضور": (
                            row["marked_at"]
                            if row["marked_at"]
                            else "-"
                        ),
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

def teacher_settings_page():

    st.header(
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
            "تأكيد كلمة المرور الجديدة",
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

        if not verify_password(
            old_password,
            stored,
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

        elif len(new_password) < 4:

            st.error(
                "❌ كلمة المرور الجديدة يجب أن تكون 4 أحرف أو أرقام على الأقل."
            )

        elif new_password != confirm_password:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

        else:

            save_setting(
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

    st.markdown(
        """
        <div class="main-title">
            👨‍🏫 لوحة تحكم المدرس
        </div>

        <div class="sub-title">
            إدارة الحصص والحضور والطلاب
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "🚪 تسجيل خروج",
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    # -----------------------------------------------------
    # إحصائيات سريعة
    # -----------------------------------------------------

    total_students, total_lessons, total_attendance = (
        platform_statistics()
    )

    active = get_active_lesson()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👥 إجمالي المنصة",
        total_students,
    )

    c2.metric(
        "📚 عدد الحصص",
        total_lessons,
    )

    c3.metric(
        "🟢 الحصة الحالية",
        "مفتوحة" if active else "لا توجد",
    )

    st.divider()

    # -----------------------------------------------------
    # Tabs
    # -----------------------------------------------------

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "📋 التقارير",
            "⚙️ الإعدادات",
        ]
    )

    with tabs[0]:

        create_lesson_page()

    with tabs[1]:

        current_lesson_page()

    with tabs[2]:

        teacher_students_page()

    with tabs[3]:

        reports_page()

    with tabs[4]:

        teacher_settings_page()

    # -----------------------------------------------------
    # رابط المدرس
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "🔗 رابط صفحة المدرس"
    )

    url = teacher_page_url()

    st.code(
        url,
        language="text",
    )

    st.caption(
        "هذا الرابط خاص بالمدرس. صفحة الطالب لا تحتوي على لوحة المدرس."
    )


# =========================================================
# تشغيل التطبيق
# =========================================================

def main():

    init_database()

    page = st.query_params.get(
        "page",
        "student",
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
