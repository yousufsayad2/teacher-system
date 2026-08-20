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

DB_FILE = "teacher_system_v2.db"

DEFAULT_TEACHER_PASSWORD = "1234"

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

GROUPS = [
    "المجموعة الأولى",
    "المجموعة الثانية",
    "المجموعة الثالثة",
    "المجموعة الرابعة",
    "المجموعة الخامسة",
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

    .big-title {
        font-size: 44px;
        font-weight: 900;
        text-align: center;
        margin-bottom: 10px;
    }

    .subtitle {
        text-align: center;
        font-size: 21px;
        margin-bottom: 30px;
    }

    .student-card {
        padding: 20px;
        border-radius: 15px;
        background: rgba(50,50,60,0.35);
        margin-bottom: 20px;
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
        timeout=30,
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
# إعدادات النظام
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
        INSERT INTO settings(key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )

    conn.commit()
    conn.close()


# =========================================================
# إنشاء قاعدة البيانات
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

            group_name TEXT DEFAULT 'المجموعة الأولى',

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

            group_name TEXT DEFAULT 'المجموعة الأولى',

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

            UNIQUE(
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
    # كلمة مرور المدرس
    # -----------------------------------------------------

    row = cur.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (
            "teacher_password_hash",
        ),
    ).fetchone()

    if row is None:

        cur.execute(
            """
            INSERT INTO settings(
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
# ترقية قاعدة البيانات القديمة
# =========================================================

def upgrade_database():

    conn = db()

    cur = conn.cursor()

    # -----------------------------------------------------
    # students
    # -----------------------------------------------------

    student_columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(students)"
        ).fetchall()
    ]

    if "group_name" not in student_columns:

        cur.execute(
            """
            ALTER TABLE students
            ADD COLUMN group_name TEXT
            DEFAULT 'المجموعة الأولى'
            """
        )

    # -----------------------------------------------------
    # lessons
    # -----------------------------------------------------

    lesson_columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(lessons)"
        ).fetchall()
    ]

    if "group_name" not in lesson_columns:

        cur.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN group_name TEXT
            DEFAULT 'المجموعة الأولى'
            """
        )

    if "ended_at" not in lesson_columns:

        cur.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN ended_at TEXT
            """
        )

    conn.commit()

    # -----------------------------------------------------
    # تنظيف القيم القديمة
    # -----------------------------------------------------

    try:

        conn.execute(
            """
            UPDATE students
            SET group_name = 'المجموعة الأولى'
            WHERE group_name IS NULL
               OR TRIM(group_name) = ''
            """
        )

        conn.execute(
            """
            UPDATE lessons
            SET group_name = 'المجموعة الأولى'
            WHERE group_name IS NULL
               OR TRIM(group_name) = ''
            """
        )

        conn.commit()

    except Exception:
        pass

    conn.close()


# =========================================================
# الطالب
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
# الحصة المفتوحة
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
# عدد طلاب الصف والمجموعة
# =========================================================

def lesson_statistics(
    lesson_id,
    grade,
    group_name,
):

    conn = db()

    total = conn.execute(
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
    ).fetchone()["total"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS total

        FROM attendance a

        INNER JOIN students s
        ON s.id = a.student_id

        WHERE a.lesson_id = ?

        AND s.grade = ?

        AND s.group_name = ?
        """,
        (
            lesson_id,
            grade,
            group_name,
        ),
    ).fetchone()["total"]

    absent = total - present

    conn.close()

    return total, present, absent


# =========================================================
# تسجيل حضور الطالب
# =========================================================

def mark_attendance(
    token,
    student_id,
):

    conn = db()

    try:

        # -------------------------------------------------
        # الحصة
        # -------------------------------------------------

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

            return (
                False,
                "❌ QR غير صالح أو الحصة انتهت.",
            )

        # -------------------------------------------------
        # الطالب
        # -------------------------------------------------

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
                "❌ الطالب غير مسجل في المنصة.",
            )

        # -------------------------------------------------
        # الصف
        # -------------------------------------------------

        if student["grade"] != lesson["grade"]:

            return (
                False,
                "❌ هذه الحصة ليست لصفك.",
            )

        # -------------------------------------------------
        # المجموعة
        # -------------------------------------------------

        if (
            student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذه الحصة ليست لمجموعتك.",
            )

        # -------------------------------------------------
        # هل حضر بالفعل؟
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
                "✅ أنت سجلت حضورك بالفعل.",
            )

        # -------------------------------------------------
        # تسجيل الحضور
        # -------------------------------------------------

        conn.execute(
            """
            INSERT INTO attendance(
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

        return (
            True,
            "✅ تم تسجيل حضورك بالفعل.",
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ أثناء تسجيل الحضور: {e}",
        )

    finally:

        conn.close()


# =========================================================
# QR
# =========================================================

def decode_qr(uploaded):

    if uploaded is None:
        return None

    try:

        data = np.frombuffer(
            uploaded.getvalue(),
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
        pass

    return None


# =========================================================
# روابط الصفحات
# =========================================================

def base_url():

    try:

        url = st.context.url

        if "?" in url:
            url = url.split("?")[0]

        return url

    except Exception:

        return ""


def student_url():

    return (
        base_url()
        + "?page=student"
    )


def teacher_url():

    return (
        base_url()
        + "?page=teacher"
    )


# =========================================================
# Header
# =========================================================

def render_header(
    title,
    subtitle,
):

    st.markdown(
        f"""
        <div class="big-title">
            {title}
        </div>

        <div class="subtitle">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# صفحة تسجيل الطالب
# =========================================================

def student_registration_page():

    render_header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب في المنصة",
    )

    st.info(
        """
        👋 التسجيل هنا يتم مرة واحدة فقط.

        بعد التسجيل لن تحتاج إلى كتابة بياناتك مرة أخرى.

        📱 في كل حصة ستستخدم QR الخاص بالمدرس لتسجيل الحضور.
        """
    )

    with st.form(
        "student_register",
        clear_on_submit=False,
    ):

        name = st.text_input(
            "👨‍🎓 اسم الطالب",
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب",
        )

        parent_phone = st.text_input(
            "👨‍👩‍👦 رقم هاتف ولي الأمر",
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES,
        )

        group_name = st.selectbox(
            "👥 المجموعة",
            GROUPS,
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
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

        conn = db()

        try:

            cur = conn.execute(
                """
                INSERT INTO students(
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
                    group_name,
                    now(),
                ),
            )

            conn.commit()

            student_id = cur.lastrowid

            st.session_state.student_id = (
                student_id
            )

            st.query_params["student"] = (
                str(student_id)
            )

            st.success(
                "🎉 تم تسجيل الطالب بنجاح."
            )

            st.rerun()

        except sqlite3.IntegrityError:

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

                st.query_params["student"] = (
                    str(existing["id"])
                )

                st.success(
                    "✅ هذا الطالب مسجل بالفعل. تم فتح حسابه."
                )

                st.rerun()

            else:

                st.error(
                    "❌ حدث خطأ أثناء التسجيل."
                )

        finally:

            conn.close()


# =========================================================
# صفحة حضور الطالب
# =========================================================

def student_attendance_page(
    student,
):

    render_header(
        "🎓 منصة الحضور",
        "📱 تسجيل حضور الطالب",
    )

    st.success(
        f"👨‍🎓 أهلاً يا {student['name']}"
    )

    st.write(
        f"🎓 **الصف:** {student['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {student['group_name']}"
    )

    st.write(
        f"🆔 **رقم الطالب:** {student['id']}"
    )

    st.divider()

    lesson = active_lesson()

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة حاليًا.

            عندما يبدأ المدرس الحصة،
            ستظهر هنا إمكانية تسجيل الحضور.
            """
        )

        return

    # -----------------------------------------------------
    # التأكد من الصف والمجموعة
    # -----------------------------------------------------

    if (
        lesson["grade"] != student["grade"]
        or lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            f"""
            ⏳ توجد حصة مفتوحة حاليًا،
            لكنها ليست لمجموعتك.

            الحصة:
            {lesson['lesson_name']}

            الصف:
            {lesson['grade']}

            المجموعة:
            {lesson['group_name']}
            """
        )

        return

    # -----------------------------------------------------
    # الحصة
    # -----------------------------------------------------

    st.success(
        f"""
        🟢 توجد حصة مفتوحة الآن

        📚 {lesson['lesson_name']}

        🎓 {lesson['grade']}

        👥 {lesson['group_name']}
        """
    )

    st.write(
        f"🕐 بدأت الحصة: {lesson['created_at']}"
    )

    # -----------------------------------------------------
    # هل سجل بالفعل؟
    # -----------------------------------------------------

    conn = db()

    already_present = conn.execute(
        """
        SELECT id, marked_at
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student["id"],
        ),
    ).fetchone()

    conn.close()

    if already_present:

        st.success(
            f"""
            ✅ تم تسجيل حضورك في هذه الحصة.

            🕐 وقت الحضور:
            {already_present['marked_at']}
            """
        )

        return

    # -----------------------------------------------------
    # QR
    # -----------------------------------------------------

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        """
        اضغط على زر الكاميرا ثم صوّر QR الموجود عند المدرس.

        الكاميرا **لن تعمل تلقائيًا**.
        """
    )

    scan_key = st.session_state.get(
        "scan_key",
        0,
    )

    scan = st.camera_input(
        "📷 تصوير QR الحضور",
        key=f"attendance_camera_{scan_key}",
    )

    if scan is None:
        return

    token = decode_qr(scan)

    if not token:

        st.error(
            "❌ لم يتم التعرف على QR. حاول تصويره بوضوح."
        )

        return

    ok, message = mark_attendance(
        token,
        student["id"],
    )

    if ok:

        st.success(message)

        st.session_state["scan_key"] = (
            scan_key + 1
        )

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

    query_student = st.query_params.get(
        "student"
    )

    # -----------------------------------------------------
    # استعادة الطالب
    # -----------------------------------------------------

    if (
        student_id is None
        and query_student
    ):

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
    # تسجيل جديد
    # -----------------------------------------------------

    if student_id is None:

        student_registration_page()

        return

    student = get_student(
        student_id
    )

    if student is None:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

        return

    student_attendance_page(
        student
    )


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 لوحة المدرس",
        "🔐 إدارة الحصص والحضور",
    )

    st.info(
        """
        هذه الصفحة خاصة بالمدرس فقط.
        """
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password",
    )

    if st.button(
        "🔐 دخول المدرس",
        use_container_width=True,
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if (
            stored
            and verify_password(
                password,
                stored,
            )
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
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    current = active_lesson()

    if current:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حاليًا.

            📚 الحصة: {current['lesson_name']}

            🎓 الصف: {current['grade']}

            👥 المجموعة: {current['group_name']}

            🕐 بدأت: {current['created_at']}
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

        st.info(
            "بعد إنهاء الحصة يمكنك إنشاء حصة جديدة."
        )

        return

    # -----------------------------------------------------
    # إنشاء
    # -----------------------------------------------------

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="new_lesson_grade",
    )

    group_name = st.selectbox(
        "👥 المجموعة",
        GROUPS,
        key="new_lesson_group",
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="new_lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        lesson_name = (
            lesson_name.strip()
            or "الحصة الحالية"
        )

        create_new_lesson(
            grade,
            group_name,
            lesson_name,
        )

        st.success(
            "🎉 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# إنشاء الحصة فعليًا
# =========================================================

def create_new_lesson(
    grade,
    group_name,
    lesson_name,
):

    conn = db()

    try:

        # -------------------------------------------------
        # لا تسمح بحصتين مفتوحتين
        # -------------------------------------------------

        existing = conn.execute(
            """
            SELECT id
            FROM lessons
            WHERE active = 1
            LIMIT 1
            """
        ).fetchone()

        if existing:

            raise RuntimeError(
                "توجد حصة مفتوحة بالفعل."
            )

        token = secrets.token_urlsafe(
            32
        )

        conn.execute(
            """
            INSERT INTO lessons(
                grade,
                group_name,
                lesson_name,
                created_at,
                ended_at,
                active,
                token
            )

            VALUES (?, ?, ?, ?, NULL, 1, ?)
            """,
            (
                grade,
                group_name,
                lesson_name,
                now(),
                token,
            ),
        )

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# =========================================================
# إنهاء حصة
# =========================================================

def end_lesson(
    lesson_id
):

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

    conn.commit()
    conn.close()


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
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    # -----------------------------------------------------
    # معلومات
    # -----------------------------------------------------

    st.markdown(
        f"""
        ## 📚 {lesson['lesson_name']}

        🎓 **الصف:** {lesson['grade']}

        👥 **المجموعة:** {lesson['group_name']}

        🕐 **بدأت:** {lesson['created_at']}
        """
    )

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب المسجلون",
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

    if total == 0:

        st.warning(
            "⚠️ لا يوجد طلاب مسجلون في هذه المجموعة."
        )

    elif present == total:

        st.success(
            "🎉 جميع الطلاب سجلوا الحضور."
        )

    else:

        st.info(
            f"📌 الموجود حاليًا: {present} من {total}"
        )

    st.divider()

    # -----------------------------------------------------
    # QR
    # -----------------------------------------------------

    st.subheader(
        "📱 QR الحضور"
    )

    qr = qrcode.make(
        lesson["token"]
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG",
    )

    st.image(
        buffer.getvalue(),
        caption="📱 الطلاب يمسحون هذا الكود",
        width=350,
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
    # حالة الطلاب
    # -----------------------------------------------------

    st.subheader(
        "📋 حالة طلاب الحصة"
    )

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

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

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب في هذه المجموعة."
        )

    st.divider()

    # -----------------------------------------------------
    # إنهاء
    # -----------------------------------------------------

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True,
    ):

        end_lesson(
            lesson["id"]
        )

        st.success(
            "✅ تم إنهاء الحصة وحفظ نتائجها."
        )

        st.rerun()


# =========================================================
# الحصول على الطلاب
# =========================================================

def get_lesson_students(
    lesson_id,
    grade,
    group_name,
):

    conn = db()

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,
            s.grade,
            s.group_name,
            a.marked_at

        FROM students s

        LEFT JOIN attendance a

        ON
            a.student_id = s.id
            AND a.lesson_id = ?

        WHERE s.grade = ?
        AND s.group_name = ?

        ORDER BY s.id
        """,
        (
            lesson_id,
            grade,
            group_name,
        ),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# جميع الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون في المنصة"
    )

    conn = db()

    total_platform = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

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

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "👨‍🎓 إجمالي طلاب المنصة",
        total_platform,
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
                "ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "تاريخ التسجيل": row["created_at"],
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    # -----------------------------------------------------
    # إحصائيات الصفوف
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "📊 عدد الطلاب حسب الصف"
    )

    conn = db()

    grade_rows = conn.execute(
        """
        SELECT
            grade,
            COUNT(*) AS total

        FROM students

        GROUP BY grade

        ORDER BY grade
        """
    ).fetchall()

    conn.close()

    if grade_rows:

        st.dataframe(
            [
                {
                    "الصف": row["grade"],
                    "عدد الطلاب": row["total"],
                }
                for row in grade_rows
            ],
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 سجل الحصص والتقارير"
    )

    conn = db()

    lessons = conn.execute(
        """
        SELECT *
        FROM lessons
        ORDER BY id DESC
        """
    ).fetchall()

    total_platform = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

    conn.close()

    # -----------------------------------------------------
    # إجمالي المنصة
    # -----------------------------------------------------

    st.metric(
        "👨‍🎓 إجمالي الطلاب في المنصة",
        total_platform,
    )

    st.divider()

    if not lessons:

        st.info(
            "📭 لا توجد حصص محفوظة حتى الآن."
        )

        return

    # -----------------------------------------------------
    # ملخص جميع الحصص
    # -----------------------------------------------------

    summary = []

    for lesson in lessons:

        total, present, absent = (
            lesson_statistics(
                lesson["id"],
                lesson["grade"],
                lesson["group_name"],
            )
        )

        status = (
            "🟢 مفتوحة"
            if lesson["active"]
            else "🔴 منتهية"
        )

        summary.append(
            {
                "الحالة": status,
                "الحصة": lesson["lesson_name"],
                "الصف": lesson["grade"],
                "المجموعة": lesson["group_name"],
                "التاريخ والوقت": lesson["created_at"],
                "وقت الانتهاء": (
                    lesson["ended_at"]
                    or "-"
                ),
                "المسجلون": total,
                "الحضور": present,
                "الغياب": absent,
            }
        )

    st.subheader(
        "📚 جميع الحصص"
    )

    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # -----------------------------------------------------
    # اختيار حصة
    # -----------------------------------------------------

    options = {}

    for lesson in lessons:

        label = (
            f"{lesson['lesson_name']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "📚 اختر حصة لعرض تفاصيلها",
        list(options.keys()),
    )

    lesson_id = options[selected]

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

    # -----------------------------------------------------
    # تفاصيل الحصة
    # -----------------------------------------------------

    st.subheader(
        "📖 تفاصيل الحصة"
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
        f"📅 **تاريخ البداية:** {lesson['created_at']}"
    )

    st.write(
        f"⏰ **وقت النهاية:** "
        f"{lesson['ended_at'] or 'الحصة ما زالت مفتوحة'}"
    )

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

    st.divider()

    # -----------------------------------------------------
    # الأرقام
    # -----------------------------------------------------

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 المسجلون",
        total,
    )

    c2.metric(
        "📱 سجلوا حضور",
        present,
    )

    c3.metric(
        "✅ حضروا",
        present,
    )

    c4.metric(
        "❌ غابوا",
        absent,
    )

    st.divider()

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"],
        lesson["group_name"],
    )

    # -----------------------------------------------------
    # الحاضرون
    # -----------------------------------------------------

    st.subheader(
        "✅ الطلاب الذين حضروا"
    )

    present_rows = [
        row
        for row in rows
        if row["marked_at"]
    ]

    if present_rows:

        st.dataframe(
            [
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "وقت الحضور": row["marked_at"],
                }
                for row in present_rows
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد حضور مسجل."
        )

    # -----------------------------------------------------
    # الغائبون
    # -----------------------------------------------------

    st.subheader(
        "❌ الطلاب الذين غابوا"
    )

    absent_rows = [
        row
        for row in rows
        if not row["marked_at"]
    ]

    if absent_rows:

        st.dataframe(
            [
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "الحالة": "❌ غائب",
                }
                for row in absent_rows
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.success(
            "🎉 جميع الطلاب حضروا هذه الحصة."
        )


# =========================================================
# رابط الطالب
# =========================================================

def student_link_page():

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    link = student_url()

    st.write(
        """
        ابعت الرابط ده للطلاب.

        الطالب يفتحه ويسجل بياناته أول مرة.

        بعد التسجيل بياناته تفضل محفوظة،
        وفي كل حصة يستخدم QR لتسجيل الحضور.
        """
    )

    st.code(
        link,
        language="text",
    )

    st.success(
        "📱 هذا هو الرابط الذي ترسله للطلاب."
    )

    st.divider()

    st.markdown(
        """
        ### 👨‍🎓 طريقة استخدام الطالب

        **1️⃣** يفتح الرابط.

        **2️⃣** يسجل اسمه ورقم هاتفه والصف والمجموعة.

        **3️⃣** بعد التسجيل لا يحتاج لتسجيل بياناته مرة أخرى.

        **4️⃣** عندما يبدأ المدرس حصة مناسبة لصفه ومجموعته،
        تظهر له الحصة.

        **5️⃣** يضغط على الكاميرا ويصور QR الخاص بالمدرس.

        **6️⃣** يتم تسجيل حضوره فورًا عند المدرس.
        """
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

        old = st.text_input(
            "كلمة المرور الحالية",
            type="password",
        )

        new = st.text_input(
            "كلمة المرور الجديدة",
            type="password",
        )

        confirm = st.text_input(
            "تأكيد كلمة المرور",
            type="password",
        )

        save = st.form_submit_button(
            "🔐 تغيير كلمة المرور",
            use_container_width=True,
        )

    if save:

        stored = get_setting(
            "teacher_password_hash"
        )

        if not verify_password(
            old,
            stored,
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

            return

        if len(new) < 4:

            st.error(
                "❌ كلمة المرور الجديدة يجب أن تكون 4 أحرف/أرقام على الأقل."
            )

            return

        if new != confirm:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

            return

        set_setting(
            "teacher_password_hash",
            hash_password(new),
        )

        st.success(
            "✅ تم تغيير كلمة المرور بنجاح."
        )


# =========================================================
# لوحة تحكم المدرس
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher_logged_in",
        False,
    ):

        teacher_login()

        return

    render_header(
        "👨‍🏫 لوحة تحكم المدرس",
        "إدارة الحصص والحضور",
    )

    # -----------------------------------------------------
    # خروج
    # -----------------------------------------------------

    if st.button(
        "🚪 تسجيل خروج",
    ):

        st.session_state.teacher_logged_in = (
            False
        )

        st.rerun()

    # -----------------------------------------------------
    # الرابط
    # -----------------------------------------------------

    st.markdown(
        "### 🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text",
    )

    st.caption(
        "📱 ابعت الرابط ده للطلاب للتسجيل في المنصة."
    )

    st.divider()

    # -----------------------------------------------------
    # التبويبات
    # -----------------------------------------------------

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "⚙️ الإعدادات",
        ]
    )

    with tabs[0]:

        create_lesson_page()

    with tabs[1]:

        current_lesson_page()

    with tabs[2]:

        reports_page()

    with tabs[3]:

        students_page()

    with tabs[4]:

        settings_page()


# =========================================================
# MAIN
# =========================================================

def main():

    # إنشاء قاعدة البيانات
    init_db()

    # ترقية قاعدة البيانات القديمة
    upgrade_database()

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
