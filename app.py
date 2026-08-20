import streamlit as st
import streamlit.components.v1 as components
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

# قاعدة بيانات جديدة تمامًا لمنع مشاكل النسخة القديمة
DB_FILE = "teacher_system_v3.db"

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
    page_title="Teacher System",
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
        check_same_thread=False,
        timeout=30
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

    # إعدادات النظام
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
            UNIQUE(lesson_id, student_id)
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

    if not stored:
        return False

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
        INSERT OR REPLACE INTO settings(key, value)
        VALUES (?, ?)
        """,
        (key, value)
    )

    conn.commit()
    conn.close()


# =========================================================
# الروابط
# =========================================================

def base_url():

    try:

        current = st.context.url
        parts = urlsplit(current)

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                "",
                ""
            )
        )

    except Exception:

        return ""


def student_url():

    base = base_url()

    if base:
        return base

    return "/"


def teacher_url():

    base = base_url()

    if base:
        return base + "?page=teacher"

    return "?page=teacher"


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


def register_student(
    name,
    phone,
    parent_phone,
    grade
):

    conn = db()

    try:

        cur = conn.execute(
            """
            INSERT INTO students(
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

        conn.close()

        return (
            True,
            new_id,
            "🎉 تم تسجيل الطالب بنجاح."
        )

    except sqlite3.IntegrityError:

        existing = conn.execute(
            """
            SELECT id
            FROM students
            WHERE phone = ?
            """,
            (phone,)
        ).fetchone()

        conn.close()

        if existing:

            return (
                True,
                existing["id"],
                "✅ الطالب مسجل بالفعل."
            )

        return (
            False,
            None,
            "❌ حدث خطأ أثناء التسجيل."
        )


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


def create_lesson(
    grade,
    lesson_name
):

    conn = db()

    # إغلاق أي حصة قديمة
    conn.execute(
        """
        UPDATE lessons
        SET active = 0,
            ended_at = ?
        WHERE active = 1
        """,
        (now(),)
    )

    token = secrets.token_urlsafe(32)

    conn.execute(
        """
        INSERT INTO lessons(
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
            token
        )
    )

    conn.commit()
    conn.close()


def end_lesson(lesson_id):

    conn = db()

    conn.execute(
        """
        UPDATE lessons
        SET active = 0,
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
            "❌ الطالب غير مسجل."
        )

    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست لصفك."
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
            student_id
        )
    ).fetchone()

    if existing:

        conn.close()

        return (
            True,
            "✅ حضورك مسجل بالفعل."
        )

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
# الإحصائيات
# =========================================================

def lesson_stats(
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

    absent = max(
        total - present,
        0
    )

    return total, present, absent


def get_lesson_students(
    lesson_id,
    grade
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
            grade
        )
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
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
        pass

    return None


# =========================================================
# صوت حضور جديد عند المدرس
# =========================================================

def attendance_sound():

    components.html(
        """
        <script>
        try {
            const AudioContext =
                window.AudioContext ||
                window.webkitAudioContext;

            if (AudioContext) {

                const ctx = new AudioContext();

                const oscillator =
                    ctx.createOscillator();

                const gain =
                    ctx.createGain();

                oscillator.type = "sine";
                oscillator.frequency.value = 880;

                gain.gain.setValueAtTime(
                    0.0001,
                    ctx.currentTime
                );

                gain.gain.exponentialRampToValueAtTime(
                    0.25,
                    ctx.currentTime + 0.03
                );

                gain.gain.exponentialRampToValueAtTime(
                    0.0001,
                    ctx.currentTime + 0.4
                );

                oscillator.connect(gain);
                gain.connect(ctx.destination);

                oscillator.start();

                oscillator.stop(
                    ctx.currentTime + 0.4
                );
            }
        }
        catch(e) {}
        </script>
        """,
        height=0
    )


# =========================================================
# العنوان
# =========================================================

def render_header(
    title,
    subtitle
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
        unsafe_allow_html=True
    )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    render_header(
        "🎓 نظام الحضور الذكي",
        "صفحة الطالب"
    )

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    # استرجاع الطالب
    if student_id is None and query_student:

        try:

            student = get_student(
                int(query_student)
            )

            if student:

                st.session_state.student_id = (
                    student["id"]
                )

                student_id = student["id"]

        except Exception:
            pass

    # =====================================================
    # تسجيل الطالب أول مرة
    # =====================================================

    if student_id is None:

        st.info(
            """
            📝 سجل بياناتك أول مرة فقط.

            بعد التسجيل لن تحتاج إلى التسجيل مرة أخرى.
            """
        )

        st.subheader(
            "📝 تسجيل الطالب"
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

            ok, new_id, message = register_student(
                name,
                phone,
                parent_phone,
                grade
            )

            if ok:

                st.session_state.student_id = new_id

                st.query_params["student"] = str(
                    new_id
                )

                st.success(message)

                st.rerun()

            else:

                st.error(message)

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

        return

    st.success(
        f"""
        👨‍🎓 أهلاً بك يا {student['name']}

        الصف: {student['grade']}
        """
    )

    st.caption(
        f"رقم الطالب: {student['id']}"
    )

    # =====================================================
    # الحصة
    # =====================================================

    lesson = active_lesson()

    if lesson is None:

        st.warning(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.warning(
            f"""
            ⚠️ توجد حصة حالياً للصف:
            {lesson['grade']}

            وأنت مسجل في:
            {student['grade']}
            """
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 بدأت الحصة: {lesson['created_at']}"
    )

    # =====================================================
    # هل حضر بالفعل؟
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
            "حضورك محفوظ بالفعل."
        )

        return

    # =====================================================
    # فتح الكاميرا يدويًا
    # =====================================================

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        """
        اضغط على الزر أولًا.
        الكاميرا لن تفتح تلقائيًا.
        """
    )

    if not st.session_state.get(
        "scanner_open",
        False
    ):

        if st.button(
            "📷 بدء مسح QR",
            use_container_width=True
        ):

            st.session_state.scanner_open = True

            st.rerun()

        return

    # =====================================================
    # الكاميرا
    # =====================================================

    st.info(
        "📷 وجّه الكاميرا إلى QR الموجود عند المدرس."
    )

    scan = st.camera_input(
        "مسح QR الحضور",
        key="attendance_camera"
    )

    if scan is not None:

        token = decode_qr(scan)

        if not token:

            st.error(
                "❌ لم أستطع قراءة QR. حاول مرة أخرى."
            )

        else:

            ok, message = mark_attendance(
                token,
                student_id
            )

            if ok:

                st.session_state.scanner_open = False

                st.success(message)

                st.rerun()

            else:

                st.error(message)

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

    render_header(
        "👨‍🏫 Teacher System",
        "دخول المدرس"
    )

    st.info(
        "🔐 هذه الصفحة خاصة بالمدرس."
    )

    password = st.text_input(
        "كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "🔑 دخول المدرس",
        use_container_width=True
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if verify_password(
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
            ⚠️ توجد حصة مفتوحة بالفعل:

            {current['lesson_name']}

            الصف:
            {current['grade']}
            """
        )

        st.info(
            "أنهِي الحصة الحالية أولًا."
        )

        return

    conn = db()

    rows = conn.execute(
        """
        SELECT DISTINCT grade
        FROM students
        ORDER BY grade
        """
    ).fetchall()

    conn.close()

    available_grades = [
        row["grade"]
        for row in rows
    ]

    if not available_grades:
        available_grades = GRADES

    grade = st.selectbox(
        "الصف",
        available_grades
    )

    lesson_name = st.text_input(
        "اسم الحصة",
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

        st.session_state.last_present_count = 0

        st.success(
            "🟢 بدأت الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصة الحالية
# =========================================================

@st.fragment(run_every="3s")
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

    total, present, absent = lesson_stats(
        lesson["id"],
        lesson["grade"]
    )

    # صوت عند حضور طالب جديد
    old_count = st.session_state.get(
        "last_present_count",
        present
    )

    if present > old_count:

        attendance_sound()

    st.session_state.last_present_count = present

    # =====================================================
    # الأرقام
    # =====================================================

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

    if total > 0 and present == total:

        st.success(
            "🎉 كل الطلاب المسجلين حضروا."
        )

    elif present > 0:

        st.warning(
            f"⚠️ باقي {absent} طالب لم يسجلوا الحضور."
        )

    else:

        st.info(
            "لم يسجل أي طالب الحضور حتى الآن."
        )

    st.write(
        f"**📚 الصف:** {lesson['grade']}"
    )

    st.write(
        f"**📖 الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**🕐 بدأت:** {lesson['created_at']}"
    )

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
    # كل طلاب الصف
    # =====================================================

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"]
    )

    st.subheader(
        "👨‍🎓 حالة الطلاب"
    )

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حضر"
            attendance_time = row["marked_at"]

        else:

            status = "❌ غائب"
            attendance_time = "-"

        table.append(
            {
                "الطالب": row["name"],
                "رقم الهاتف": row["phone"],
                "الحالة": status,
                "وقت الحضور": attendance_time
            }
        )

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    if st.button(
        "⛔ إنهاء الحصة",
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
        WHERE active = 0
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    if not lessons:

        st.info(
            "لا توجد حصص منتهية حتى الآن."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
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

    conn.close()

    total, present, absent = lesson_stats(
        lesson["id"],
        lesson["grade"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 المسجلون",
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

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"]
    )

    present_list = []
    absent_list = []

    for row in rows:

        if row["marked_at"]:

            present_list.append(
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "وقت الحضور": row["marked_at"]
                }
            )

        else:

            absent_list.append(
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "ولي الأمر": row["parent_phone"]
                }
            )

    st.subheader(
        "✅ الطلاب الحاضرون"
    )

    if present_list:

        st.dataframe(
            present_list,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب حضروا."
        )

    st.subheader(
        "❌ الطلاب الغائبون"
    )

    if absent_list:

        st.dataframe(
            absent_list,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.success(
            "🎉 جميع الطلاب حضروا."
        )


# =========================================================
# جميع الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 جميع الطلاب"
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
# الإعدادات
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    st.write(
        "🔐 تغيير كلمة مرور المدرس"
    )

    with st.form(
        "change_password"
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

        elif len(new) < 4:

            st.error(
                "❌ كلمة المرور الجديدة قصيرة جدًا."
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
        """
        <div class="big-title">
            👨‍🏫 لوحة تحكم المدرس
        </div>
        """,
        unsafe_allow_html=True
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
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "⚙️ الإعدادات"
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

    st.divider()

    st.subheader(
        "🔗 روابط النظام"
    )

    st.write(
        "👨‍🎓 رابط الطالب:"
    )

    st.code(
        student_url(),
        language="text"
    )

    st.write(
        "👨‍🏫 رابط المدرس:"
    )

    st.code(
        teacher_url(),
        language="text"
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

    if page == "teacher":

        teacher_dashboard()

    else:

        student_page()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
