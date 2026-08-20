import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
import base64
import wave
import math
import struct
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


# =========================================================
# إعدادات النظام
# =========================================================

# قاعدة بيانات جديدة تمامًا
DB_FILE = "teacher_system_final.db"

DEFAULT_TEACHER_PASSWORD = "1234"

GRADES = [
    "الصف الأول الابتدائي",
    "الصف الثاني الابتدائي",
    "الصف الثالث الابتدائي",
    "الصف الرابع الابتدائي",
    "الصف الخامس الابتدائي",
    "الصف السادس الابتدائي",
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
        padding-bottom: 3rem;
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
# قاعدة البيانات
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def init_db():

    conn = db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # إعدادات
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

        if not stored:
            return False

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
# إنشاء حصة
# =========================================================

def create_lesson(grade, lesson_name):

    conn = db()

    # إغلاق أي حصة قديمة
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

    token = secrets.token_urlsafe(32)

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
# إنهاء الحصة
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
# إحصائيات الحضور
# =========================================================

def lesson_stats(lesson_id, grade):

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

    return total, present, absent


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
            "❌ الطالب غير مسجل على المنصة."
        )

    # التأكد من الصف
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذا الـQR خاص بصف مختلف."
        )

    # هل الطالب حضر بالفعل؟
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

        current_url = st.context.url

        parts = urlsplit(current_url)

        clean_url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                "",
                ""
            )
        )

        return (
            clean_url
            + "?page=teacher"
        )

    except Exception:

        return "?page=teacher"


# =========================================================
# عنوان الصفحة
# =========================================================

def render_header(title, subtitle=""):

    st.markdown(
        f"""
        <div class="big-title">
            {title}
        </div>

        <div class="subtitle">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# صوت حضور بسيط
# =========================================================

def play_attendance_sound():

    try:

        sample_rate = 44100
        duration = 0.25
        frequency = 880

        audio = io.BytesIO()

        with wave.open(audio, "wb") as wav:

            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)

            for i in range(
                int(sample_rate * duration)
            ):

                value = int(
                    10000
                    * math.sin(
                        2
                        * math.pi
                        * frequency
                        * i
                        / sample_rate
                    )
                )

                wav.writeframes(
                    struct.pack(
                        "<h",
                        value
                    )
                )

        encoded = base64.b64encode(
            audio.getvalue()
        ).decode()

        st.markdown(
            f"""
            <audio autoplay>
                <source
                    src="data:audio/wav;base64,{encoded}"
                    type="audio/wav"
                >
            </audio>
            """,
            unsafe_allow_html=True
        )

    except Exception:
        pass


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    render_header(
        "🎓 نظام الحضور الذكي",
        "صفحة الطالب"
    )

    # -----------------------------------------------------
    # تسجيل خروج الطالب
    # -----------------------------------------------------

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    # استرجاع الطالب من الرابط
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

    # =====================================================
    # تسجيل الطالب لأول مرة
    # =====================================================

    if student_id is None:

        st.info(
            """
            📝 سجل بياناتك أول مرة فقط.

            بعد التسجيل لن تحتاج لإعادة التسجيل
            كل مرة تدخل فيها المنصة.
            """
        )

        st.subheader(
            "📝 تسجيل الطالب"
        )

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
                "👨‍👩‍👦 رقم هاتف ولي الأمر"
            )

            grade = st.selectbox(
                "🎓 الصف",
                GRADES
            )

            submitted = st.form_submit_button(
                "✅ تسجيل الطالب",
                use_container_width=True
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

            # هل الرقم مسجل بالفعل؟
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
                    "✅ تم العثور على حسابك المسجل."
                )

                st.rerun()

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

                st.session_state.student_id = (
                    new_id
                )

                st.query_params["student"] = (
                    str(new_id)
                )

                st.success(
                    "🎉 تم تسجيلك بنجاح."
                )

                st.rerun()

            except sqlite3.IntegrityError:

                st.error(
                    "❌ رقم الهاتف مسجل بالفعل."
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
        f"""
        👋 أهلاً يا {student["name"]}

        🎓 الصف: {student["grade"]}
        """
    )

    # =====================================================
    # تسجيل خروج الطالب
    # =====================================================

    if st.button(
        "🚪 خروج من حساب الطالب",
        use_container_width=True
    ):

        st.session_state.pop(
            "student_id",
            None
        )

        st.query_params.clear()

        st.rerun()

    st.divider()

    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        st.write(
            "ارجع للصفحة عندما يبدأ المدرس الحصة."
        )

        return

    # التأكد أن الحصة لنفس الصف
    if lesson["grade"] != student["grade"]:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حالياً،
            لكنها للصف:

            {lesson["grade"]}
            """
        )

        return

    st.subheader(
        "📚 الحصة الحالية"
    )

    st.write(
        f"**اسم الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**وقت البداية:** {lesson['created_at']}"
    )

    st.divider()

    # =====================================================
    # حالة الحضور
    # =====================================================

    conn = db()

    already_present = conn.execute(
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

    conn.close()

    if already_present:

        st.success(
            "✅ تم تسجيل حضورك في هذه الحصة."
        )

        st.info(
            "لا تحتاج لتصوير QR مرة أخرى."
        )

        return

    # =====================================================
    # زر تشغيل الكاميرا
    # =====================================================

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        """
        اضغط الزر بالأسفل فقط عندما تكون جاهزًا
        لمسح QR الخاص بالمدرس.
        """
    )

    scan_enabled = st.session_state.get(
        "scan_enabled",
        False
    )

    if not scan_enabled:

        if st.button(
            "📷 ابدأ مسح QR",
            use_container_width=True
        ):

            st.session_state.scan_enabled = True

            st.rerun()

        return

    # =====================================================
    # الكاميرا لا تظهر إلا بعد الضغط
    # =====================================================

    st.warning(
        "📷 الكاميرا مفتوحة الآن. وجّهها إلى QR."
    )

    scan = st.camera_input(
        "مسح QR الحضور",
        key="student_qr_camera"
    )

    if scan is not None:

        token = decode_qr(scan)

        if not token:

            st.error(
                "❌ لم يتم قراءة QR. حاول مرة أخرى."
            )

        else:

            ok, message = mark_attendance(
                token,
                student_id
            )

            if ok:

                st.success(message)

                # إغلاق الكاميرا
                st.session_state.scan_enabled = False

                st.rerun()

            else:

                st.error(message)

    # زر إغلاق الكاميرا
    if st.button(
        "❌ إغلاق الكاميرا",
        use_container_width=True
    ):

        st.session_state.scan_enabled = False

        st.rerun()


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 نظام المدرس",
        "دخول المدرس"
    )

    st.info(
        "🔐 هذه الصفحة خاصة بالمدرس."
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "🔐 دخول المدرس",
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

    st.divider()

    st.caption(
        "كلمة المرور الافتراضية أول مرة: 1234"
    )


# =========================================================
# صفحة إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    current = active_lesson()

    if current is not None:

        st.warning(
            "⚠️ توجد حصة مفتوحة بالفعل."
        )

        st.write(
            f"📚 الحصة: {current['lesson_name']}"
        )

        st.write(
            f"🎓 الصف: {current['grade']}"
        )

        st.info(
            "اذهب إلى تبويب «📊 الحصة الحالية»."
        )

        return

    # -----------------------------------------------------
    # الصفوف
    # -----------------------------------------------------

    conn = db()

    rows = conn.execute(
        """
        SELECT DISTINCT grade

        FROM students

        WHERE grade IS NOT NULL

        AND grade != ''

        ORDER BY grade
        """
    ).fetchall()

    conn.close()

    available_grades = []

    for row in rows:

        try:

            value = row["grade"]

            if value and value not in available_grades:

                available_grades.append(value)

        except Exception:

            pass

    if not available_grades:

        available_grades = GRADES

    grade = st.selectbox(
        "🎓 الصف",
        available_grades
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

        lesson_id = create_lesson(
            grade,
            lesson_name
        )

        st.session_state.last_present_count = 0
        st.session_state.last_lesson_id = lesson_id

        st.success(
            "🎉 تم بدء الحصة بنجاح."
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
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    total, present, absent = lesson_stats(
        lesson["id"],
        lesson["grade"]
    )

    # -----------------------------------------------------
    # صوت عند زيادة الحضور
    # -----------------------------------------------------

    last_count = st.session_state.get(
        "last_present_count",
        0
    )

    if present > last_count and last_count > 0:

        play_attendance_sound()

        st.success(
            "🔔 تم تسجيل حضور طالب جديد!"
        )

    st.session_state.last_present_count = present

    # -----------------------------------------------------
    # الأرقام
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي طلاب الصف",
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

    # -----------------------------------------------------
    # معلومات
    # -----------------------------------------------------

    st.write(
        f"**🎓 الصف:** {lesson['grade']}"
    )

    st.write(
        f"**📚 الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**🕐 بدأت:** {lesson['created_at']}"
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
        caption="الطلاب يمسحون هذا الكود لتسجيل الحضور",
        width=350
    )

    # =====================================================
    # تحديث
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True
    ):

        st.rerun()

    st.caption(
        "اضغط تحديث بعد تسجيل الطلاب لرؤية الأسماء الجديدة."
    )

    st.divider()

    # =====================================================
    # الحاضرون
    # =====================================================

    conn = db()

    present_rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,
            s.grade,
            a.marked_at

        FROM attendance a

        JOIN students s
            ON s.id = a.student_id

        WHERE a.lesson_id = ?

        ORDER BY a.marked_at ASC
        """,
        (lesson["id"],)
    ).fetchall()

    # =====================================================
    # الغائبون
    # =====================================================

    absent_rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,
            s.grade

        FROM students s

        WHERE s.grade = ?

        AND NOT EXISTS (

            SELECT 1

            FROM attendance a

            WHERE a.lesson_id = ?

            AND a.student_id = s.id
        )

        ORDER BY s.name
        """,
        (
            lesson["grade"],
            lesson["id"]
        )
    ).fetchall()

    conn.close()

    # =====================================================
    # الحاضرون
    # =====================================================

    st.subheader(
        f"🟢 الحاضرون ({len(present_rows)})"
    )

    if present_rows:

        st.dataframe(
            [
                {
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"],
                    "وقت الحضور": row["marked_at"]
                }
                for row in present_rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لم يسجل أي طالب حضور حتى الآن."
        )

    # =====================================================
    # الغائبون
    # =====================================================

    st.subheader(
        f"🔴 الغائبون حتى الآن ({len(absent_rows)})"
    )

    if absent_rows:

        st.dataframe(
            [
                {
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"]
                }
                for row in absent_rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        if total > 0:

            st.success(
                "🎉 كل طلاب الصف سجلوا حضورهم!"
            )

    st.divider()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    st.subheader(
        "⛔ إنهاء الحصة"
    )

    st.warning(
        """
        بعد إنهاء الحصة لن يستطيع الطلاب تسجيل حضور
        جديد باستخدام QR الخاص بهذه الحصة.
        """
    )

    if st.button(
        "⛔ إنهاء الحصة الآن",
        use_container_width=True
    ):

        end_lesson(
            lesson["id"]
        )

        st.session_state.last_present_count = 0

        st.success(
            "✅ تم إنهاء الحصة."
        )

        st.rerun()


# =========================================================
# جميع الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون على المنصة"
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
        "إجمالي الطلاب",
        len(rows)
    )

    if not rows:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )

        return

    st.dataframe(
        [
            {
                "ID": row["id"],
                "الاسم": row["name"],
                "هاتف الطالب": row["phone"],
                "هاتف ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "تاريخ التسجيل": row["created_at"]
            }
            for row in rows
        ],
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
        SELECT
            id,
            grade,
            lesson_name,
            created_at,
            ended_at,
            active

        FROM lessons

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    if not lessons:

        st.info(
            "لا توجد حصص مسجلة حتى الآن."
        )

        return

    lesson_options = {}

    for lesson in lessons:

        status = (
            "🟢 مفتوحة"
            if lesson["active"]
            else "⚫ منتهية"
        )

        label = (
            f"{status} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['grade']} | "
            f"{lesson['created_at']}"
        )

        lesson_options[label] = lesson["id"]

    selected_label = st.selectbox(
        "اختر الحصة",
        list(lesson_options.keys())
    )

    selected_id = lesson_options[
        selected_label
    ]

    # -----------------------------------------------------
    # بيانات الحصة
    # -----------------------------------------------------

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (selected_id,)
    ).fetchone()

    # -----------------------------------------------------
    # الحاضرون
    # -----------------------------------------------------

    present_rows = conn.execute(
        """
        SELECT
            s.name,
            s.phone,
            s.parent_phone,
            a.marked_at

        FROM attendance a

        JOIN students s
            ON s.id = a.student_id

        WHERE a.lesson_id = ?

        ORDER BY a.marked_at
        """,
        (selected_id,)
    ).fetchall()

    # -----------------------------------------------------
    # الغائبون
    # -----------------------------------------------------

    absent_rows = conn.execute(
        """
        SELECT
            s.name,
            s.phone,
            s.parent_phone

        FROM students s

        WHERE s.grade = ?

        AND NOT EXISTS (

            SELECT 1

            FROM attendance a

            WHERE a.lesson_id = ?

            AND a.student_id = s.id
        )

        ORDER BY s.name
        """,
        (
            lesson["grade"],
            selected_id
        )
    ).fetchall()

    conn.close()

    total = (
        len(present_rows)
        + len(absent_rows)
    )

    present = len(present_rows)

    absent = len(absent_rows)

    # -----------------------------------------------------
    # الأرقام
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
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

    st.divider()

    st.write(
        f"**📚 الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**🎓 الصف:** {lesson['grade']}"
    )

    st.write(
        f"**🕐 البداية:** {lesson['created_at']}"
    )

    st.write(
        f"**⛔ النهاية:** {lesson['ended_at'] or 'الحصة ما زالت مفتوحة'}"
    )

    st.divider()

    # -----------------------------------------------------
    # تقرير الحضور
    # -----------------------------------------------------

    st.subheader(
        f"🟢 الطلاب الذين حضروا ({present})"
    )

    if present_rows:

        st.dataframe(
            [
                {
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"],
                    "وقت الحضور": row["marked_at"]
                }
                for row in present_rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد حضور."
        )

    # -----------------------------------------------------
    # تقرير الغياب
    # -----------------------------------------------------

    st.subheader(
        f"🔴 الطلاب الذين غابوا ({absent})"
    )

    if absent_rows:

        st.dataframe(
            [
                {
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"]
                }
                for row in absent_rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.success(
            "🎉 لا يوجد غياب."
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

            return

        if len(new) < 4:

            st.error(
                "❌ كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل."
            )

            return

        if new != confirm:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

            return

        set_setting(
            "teacher_password_hash",
            hash_password(new)
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
        False
    ):

        teacher_login()

        return

    # =====================================================
    # العنوان
    # =====================================================

    st.markdown(
        """
        <div class="big-title">
            👨‍🏫 لوحة تحكم المدرس
        </div>
        """,
        unsafe_allow_html=True
    )

    # =====================================================
    # تسجيل الخروج
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

    # =====================================================
    # رابط المدرس
    # =====================================================

    st.divider()

    st.subheader(
        "🔗 رابط صفحة المدرس"
    )

    st.code(
        teacher_url(),
        language="text"
    )

    st.caption(
        "هذا الرابط يفتح صفحة المدرس وليس صفحة الطالب."
    )


# =========================================================
# تشغيل التطبيق
# =========================================================

def main():

    init_db()

    page = st.query_params.get(
        "page",
        "student"
    )

    # -----------------------------------------------------
    # صفحة المدرس
    # -----------------------------------------------------

    if page == "teacher":

        teacher_dashboard()

    # -----------------------------------------------------
    # صفحة الطالب
    # -----------------------------------------------------

    else:

        student_page()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
