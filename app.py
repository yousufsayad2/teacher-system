import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


# =========================================================
# إعدادات النظام
# =========================================================

DB_FILE = "attendance_platform_final.db"

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
    initial_sidebar_state="collapsed"
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
        text-align: center;
        font-size: 48px;
        font-weight: 900;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 23px;
        margin-bottom: 30px;
    }

    .student-link {
        background: #172033;
        border: 2px solid #2d3d59;
        border-radius: 18px;
        padding: 22px;
        margin: 20px 0;
    }

    .student-link-title {
        font-size: 28px;
        font-weight: 800;
        margin-bottom: 10px;
    }

    .student-link-text {
        font-size: 17px;
        word-break: break-all;
    }

    .success-box {
        background: #103b25;
        border-radius: 15px;
        padding: 20px;
        margin: 15px 0;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# قاعدة البيانات
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =========================================================
# إنشاء قاعدة البيانات
# =========================================================

def init_db():

    conn = db()
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

            UNIQUE (
                lesson_id,
                student_id
            )
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
        ("teacher_password_hash",)
    ).fetchone()

    if row is None:

        cur.execute(
            """
            INSERT INTO settings
            (
                key,
                value
            )
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

    return (
        salt.hex()
        + ":"
        + digest.hex()
    )


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

    if row:
        return row["value"]

    return None


def set_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT INTO settings
        (
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
            value
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# رابط التطبيق
# =========================================================

def base_url():

    try:

        current = st.context.url

        parsed = urlsplit(current)

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                ""
            )
        )

    except Exception:

        return ""


def student_url():

    base = base_url()

    if base:
        return base + "?page=student"

    return "?page=student"


def teacher_url():

    base = base_url()

    if base:
        return base + "?page=teacher"

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
        (student_id,)
    ).fetchone()

    conn.close()

    return row


# =========================================================
# الحصة الحالية
# =========================================================

def get_active_lesson():

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
# إنهاء كل الحصص القديمة
# =========================================================

def close_all_active_lessons():

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

def create_lesson_in_db(
    grade,
    lesson_name
):

    close_all_active_lessons()

    token = secrets.token_urlsafe(32)

    conn = db()

    cur = conn.execute(
        """
        INSERT INTO lessons
        (
            grade,
            lesson_name,
            created_at,
            active,
            token
        )
        VALUES (?, ?, ?, 1, ?)
        """,
        (
            grade,
            lesson_name,
            now(),
            token
        )
    )

    conn.commit()

    lesson_id = cur.lastrowid

    conn.close()

    return lesson_id


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
            lesson_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# تسجيل الحضور
# =========================================================

def mark_attendance(
    token,
    student_id
):

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
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

    # التأكد من الصف
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست لصفك."
        )

    # التأكد هل حضر بالفعل
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
            "✅ أنت مسجل حضور بالفعل في هذه الحصة."
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

def decode_qr(uploaded_file):

    if uploaded_file is None:
        return None

    try:

        data = np.frombuffer(
            uploaded_file.getvalue(),
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
# إحصائيات حصة
# =========================================================

def lesson_statistics(
    lesson_id,
    grade
):

    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM students
        WHERE grade = ?
        """,
        (grade,)
    ).fetchone()["c"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM attendance a

        JOIN students s
        ON s.id = a.student_id

        WHERE a.lesson_id = ?
        AND s.grade = ?
        """,
        (
            lesson_id,
            grade
        )
    ).fetchone()["c"]

    conn.close()

    absent = total - present

    return (
        total,
        present,
        absent
    )


# =========================================================
# الطلاب المسجلين في صف الحصة
# =========================================================

def class_students_status(lesson):

    conn = db()

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,

            CASE
                WHEN a.id IS NOT NULL
                THEN 1
                ELSE 0
            END AS present,

            a.marked_at

        FROM students s

        LEFT JOIN attendance a
        ON
            a.student_id = s.id
            AND a.lesson_id = ?

        WHERE s.grade = ?

        ORDER BY s.name
        """,
        (
            lesson["id"],
            lesson["grade"]
        )
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# صفحة تسجيل الطالب
# =========================================================

def student_registration():

    st.markdown(
        '<div class="main-title">🎓 منصة الحضور</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">📝 تسجيل الطالب في المنصة</div>',
        unsafe_allow_html=True
    )

    st.info(
        """
        👋 أول مرة فقط:
        اكتب بياناتك وسجل في المنصة.

        بعد التسجيل لن تحتاج إلى التسجيل مرة أخرى.
        في كل حصة ستستخدم QR الخاص بالمدرس لتسجيل الحضور.
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
            "👨‍👩‍👦 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True
        )

    if not submit:
        return

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

    existing = conn.execute(
        """
        SELECT *
        FROM students
        WHERE phone = ?
        """,
        (phone,)
    ).fetchone()

    if existing:

        conn.close()

        st.session_state.student_id = existing["id"]

        st.query_params["page"] = "student"

        st.success(
            "✅ هذا الطالب مسجل بالفعل."
        )

        st.rerun()

        return

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

    student_id = cur.lastrowid

    conn.close()

    st.session_state.student_id = student_id

    st.query_params["page"] = "student"

    st.success(
        "🎉 تم تسجيلك في المنصة بنجاح."
    )

    st.rerun()


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    student_id = st.session_state.get(
        "student_id"
    )

    # محاولة استرجاع الطالب من الرابط
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

    # لو مفيش طالب -> تسجيل أول مرة
    if student_id is None:

        student_registration()

        return

    student = get_student(
        student_id
    )

    if student is None:

        st.session_state.pop(
            "student_id",
            None
        )

        student_registration()

        return

    # حفظ الطالب في الرابط
    st.query_params["page"] = "student"
    st.query_params["student"] = str(
        student["id"]
    )

    st.markdown(
        '<div class="main-title">🎓 منصة الحضور</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">👨‍🎓 واجهة الطالب</div>',
        unsafe_allow_html=True
    )

    st.success(
        f"""
        👋 أهلاً يا {student["name"]}

        🎓 الصف: {student["grade"]}

        🆔 رقم الطالب: {student["id"]}
        """
    )

    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة حالياً.

            عندما يبدأ المدرس الحصة ستظهر لك هنا
            إمكانية تسجيل الحضور.
            """
        )

        return

    # التأكد من الصف
    if lesson["grade"] != student["grade"]:

        st.warning(
            f"""
            ⚠️ يوجد حصة مفتوحة حالياً للصف:

            {lesson["grade"]}

            ولكن صفك هو:

            {student["grade"]}
            """
        )

        return

    st.divider()

    st.header(
        "📚 الحصة الحالية"
    )

    st.write(
        f"📖 **اسم الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    # =====================================================
    # هل الطالب حضر بالفعل؟
    # =====================================================

    conn = db()

    attendance = conn.execute(
        """
        SELECT *
        FROM attendance

        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student["id"]
        )
    ).fetchone()

    conn.close()

    if attendance:

        st.success(
            f"""
            ✅ تم تسجيل حضورك في هذه الحصة.

            🕐 وقت الحضور:
            {attendance["marked_at"]}
            """
        )

        return

    # =====================================================
    # فتح الكاميرا عند الضغط فقط
    # =====================================================

    if not st.session_state.get(
        "scanner_open",
        False
    ):

        st.info(
            """
            📷 اضغط على الزر التالي لفتح الكاميرا
            ومسح QR الموجود عند المدرس.
            """
        )

        if st.button(
            "📷 فتح الكاميرا لتسجيل الحضور",
            use_container_width=True
        ):

            st.session_state.scanner_open = True

            st.rerun()

        return

    # =====================================================
    # الكاميرا
    # =====================================================

    st.warning(
        "📷 وجّه الكاميرا إلى QR الخاص بالمدرس."
    )

    scan = st.camera_input(
        "📷 تصوير QR",
        key="student_qr_camera"
    )

    if scan is not None:

        token = decode_qr(
            scan
        )

        if not token:

            st.error(
                "❌ لم أستطع قراءة QR. حاول تصويره بشكل أوضح."
            )

        else:

            ok, message = mark_attendance(
                token,
                student["id"]
            )

            if ok:

                st.session_state.scanner_open = False

                st.success(
                    message
                )

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
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    st.markdown(
        '<div class="main-title">👨‍🏫 لوحة المدرس</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">🔐 دخول المدرس</div>',
        unsafe_allow_html=True
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "🔐 دخول",
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

            st.success(
                "✅ تم تسجيل الدخول."
            )

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.info(
        "كلمة المرور الافتراضية أول مرة: 1234"
    )


# =========================================================
# رابط الطالب عند المدرس
# =========================================================

def student_link_box():

    link = student_url()

    st.markdown(
        """
        <div class="student-link">

        <div class="student-link-title">
        🔗 رابط تسجيل الطلاب
        </div>

        <div class="student-link-text">
        أرسل هذا الرابط للطلاب حتى يسجلوا في المنصة.
        </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    st.code(
        link,
        language="text"
    )

    # QR لرابط الطالب
    qr = qrcode.make(
        link
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        caption="📱 يمكن للطالب مسح هذا الكود لفتح صفحة التسجيل",
        width=280
    )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.header(
        "➕ إنشاء حصة جديدة"
    )

    current = get_active_lesson()

    if current:

        st.warning(
            """
            ⚠️ توجد حصة مفتوحة حالياً.

            أنهِ الحصة الحالية أولاً ثم أنشئ حصة جديدة.
            """
        )

        st.write(
            f"📚 الحصة: {current['lesson_name']}"
        )

        st.write(
            f"🎓 الصف: {current['grade']}"
        )

        if st.button(
            "🔴 إنهاء الحصة الحالية وبدء حصة جديدة",
            use_container_width=True
        ):

            end_lesson(
                current["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة السابقة."
            )

            st.rerun()

        return

    st.write(
        "اختار الصف واسم الحصة ثم اضغط بدء الحصة."
    )

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

        create_lesson_in_db(
            grade,
            lesson_name
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

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    # =====================================================
    # الإحصائيات
    # =====================================================

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب المسجلون",
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
    # QR الحضور
    # =====================================================

    st.subheader(
        "📱 QR تسجيل الحضور"
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
        caption="📷 الطلاب يمسحون هذا الكود من صفحة الطالب",
        width=350
    )

    st.divider()

    # =====================================================
    # حالة الطلاب
    # =====================================================

    st.header(
        "📋 حالة طلاب الصف"
    )

    rows = class_students_status(
        lesson
    )

    if not rows:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    else:

        table = []

        for row in rows:

            if row["present"]:

                status = "✅ حاضر"

            else:

                status = "❌ غائب"

            table.append(
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "الحالة": status,
                    "وقت الحضور": (
                        row["marked_at"]
                        if row["marked_at"]
                        else "-"
                    )
                }
            )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # =====================================================
    # تحديث
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور الآن",
        use_container_width=True
    ):

        st.rerun()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    st.warning(
        """
        ⚠️ بعد إنهاء الحصة لن يستطيع أي طالب تسجيل حضور
        في هذه الحصة.
        """
    )

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True
    ):

        end_lesson(
            lesson["id"]
        )

        st.success(
            "✅ تم إنهاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الطلاب
# =========================================================

def students_page():

    st.header(
        "👨‍🎓 الطلاب المسجلون في المنصة"
    )

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
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
                "الرقم": row["id"],
                "الاسم": row["name"],
                "الهاتف": row["phone"],
                "ولي الأمر": row["parent_phone"],
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

    st.header(
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
            "لا توجد حصص سابقة."
        )

        return

    selected_id = st.selectbox(
        "اختار الحصة",
        [
            lesson["id"]
            for lesson in lessons
        ],
        format_func=lambda x: next(
            (
                f"{l['lesson_name']} - {l['grade']} - {l['created_at']}"
                for l in lessons
                if l["id"] == x
            ),
            str(x)
        )
    )

    lesson = next(
        l for l in lessons
        if l["id"] == selected_id
    )

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 المسجلون",
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

    rows = class_students_status(
        lesson
    )

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة": (
                    "✅ حاضر"
                    if row["present"]
                    else "❌ غائب"
                ),
                "وقت الحضور": (
                    row["marked_at"]
                    if row["marked_at"]
                    else "-"
                )
            }
        )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# إعدادات المدرس
# =========================================================

def settings_page():

    st.header(
        "⚙️ إعدادات المدرس"
    )

    st.subheader(
        "🔐 تغيير كلمة المرور"
    )

    with st.form(
        "change_password_form"
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
            "تأكيد كلمة المرور الجديدة",
            type="password"
        )

        save = st.form_submit_button(
            "💾 حفظ كلمة المرور",
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
                "❌ كلمة المرور يجب أن تكون 4 أحرف أو أرقام على الأقل."
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

    st.markdown(
        '<div class="main-title">👨‍🏫 لوحة تحكم المدرس</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">إدارة الحصص والحضور</div>',
        unsafe_allow_html=True
    )

    # =====================================================
    # رابط الطالب - في قلب واجهة المدرس
    # =====================================================

    st.markdown(
        """
        <div class="student-link">

        <div class="student-link-title">
        🔗 رابط الطالب
        </div>

        <div class="student-link-text">
        ابعت الرابط ده للطلاب علشان يسجلوا في المنصة.
        الطالب يسجل مرة واحدة فقط، وبعدها يستخدم QR
        في كل حصة.
        </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    st.code(
        student_url(),
        language="text"
    )

    if st.button(
        "📋 عرض QR الخاص برابط الطالب",
        use_container_width=True
    ):

        qr = qrcode.make(
            student_url()
        )

        buffer = io.BytesIO()

        qr.save(
            buffer,
            format="PNG"
        )

        st.image(
            buffer.getvalue(),
            caption="📱 QR تسجيل الطلاب في المنصة",
            width=300
        )

    st.divider()

    # =====================================================
    # خروج
    # =====================================================

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    # =====================================================
    # التبويبات
    # =====================================================

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


# =========================================================
# تشغيل التطبيق
# =========================================================

def main():

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
