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

# اسم جديد تمامًا حتى لا يتعارض مع قاعدة البيانات القديمة
DB_FILE = "attendance_platform_v3.db"

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
        text-align: center;
        font-size: 48px;
        font-weight: 900;
        margin-bottom: 5px;
    }

    .main-subtitle {
        text-align: center;
        font-size: 22px;
        margin-bottom: 30px;
    }

    .student-link {
        padding: 18px;
        border-radius: 14px;
        background: #151821;
        border: 1px solid #333746;
        font-size: 16px;
        direction: ltr;
        text-align: left;
        word-break: break-all;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
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
# PASSWORD
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
# INIT DATABASE
# =========================================================

def init_db():

    conn = db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # Settings
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
    # Students
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
    # Lessons
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
    # Attendance
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

            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id),

            FOREIGN KEY (student_id)
                REFERENCES students(id)
        )
        """
    )

    # -----------------------------------------------------
    # Teacher password
    # -----------------------------------------------------

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
# SETTINGS
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
        (key, value),
    )

    conn.commit()
    conn.close()


# =========================================================
# URLS
# =========================================================

def base_app_url():

    try:

        current = st.context.url

        parts = urlsplit(current)

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                "",
                "",
            )
        )

    except Exception:

        return ""


def teacher_url():

    base = base_app_url()

    if base:

        return base + "?page=teacher"

    return "?page=teacher"


def student_url():

    base = base_app_url()

    if base:

        return base + "?page=student"

    return "?page=student"


def personal_student_url(student_id):

    base = base_app_url()

    if base:

        return (
            base
            + "?page=student&student="
            + str(student_id)
        )

    return (
        "?page=student&student="
        + str(student_id)
    )


# =========================================================
# HEADER
# =========================================================

def render_header(title, subtitle):

    st.markdown(
        f"""
        <div class="main-title">
            {title}
        </div>

        <div class="main-subtitle">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# STUDENT FUNCTIONS
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


def get_student_by_phone(phone):

    conn = db()

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


# =========================================================
# ACTIVE LESSON
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
# LESSON STATISTICS
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

    conn.close()

    absent = max(total - present, 0)

    return total, present, absent


# =========================================================
# MARK ATTENDANCE
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
        (token,),
    ).fetchone()

    if lesson is None:

        conn.close()

        return (
            False,
            "❌ كود الحضور غير صالح أو الحصة انتهت.",
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
            "❌ الطالب غير موجود.",
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
            "ℹ️ تم تسجيل حضورك بالفعل في هذه الحصة.",
        )

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
    conn.close()

    return (
        True,
        "🎉 تم تسجيل حضورك بنجاح.",
    )


# =========================================================
# QR DECODER
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

    except Exception:

        return None

    return None


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    render_header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    # -----------------------------------------------------
    # Get student ID
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
    # FIRST REGISTRATION
    # -----------------------------------------------------

    if student_id is None:

        st.info(
            """
            👋 أول مرة فقط:

            اكتب بياناتك وسجل في المنصة.

            بعد التسجيل لن تحتاج لإعادة التسجيل.
            """
        )

        with st.form(
            "student_registration"
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
                GRADES,
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

            # -------------------------------------------------
            # Check existing student
            # -------------------------------------------------

            existing = get_student_by_phone(
                phone
            )

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
                    "✅ الطالب مسجل بالفعل."
                )

                st.rerun()

            # -------------------------------------------------
            # New student
            # -------------------------------------------------

            conn = db()

            try:

                cursor = conn.execute(
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

                new_id = cursor.lastrowid

                st.session_state.student_id = (
                    new_id
                )

                st.query_params["page"] = (
                    "student"
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
    # Student data
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

        return

    st.success(
        f"🎓 أهلاً يا {student['name']}"
    )

    st.write(
        f"**الصف:** {student['grade']}"
    )

    st.write(
        f"**رقم الطالب:** {student['id']}"
    )

    # -----------------------------------------------------
    # Personal link
    # -----------------------------------------------------

    st.info(
        """
        🔗 احتفظ بالرابط الخاص بك.

        هذا الرابط يفتح حسابك مباشرة بعد التسجيل.
        """
    )

    st.code(
        personal_student_url(
            student["id"]
        ),
        language="text",
    )

    # -----------------------------------------------------
    # Active lesson
    # -----------------------------------------------------

    lesson = active_lesson()

    if lesson is None:

        st.warning(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.warning(
            "⏳ توجد حصة حالياً، لكنها ليست لصفك."
        )

        return

    # -----------------------------------------------------
    # Current lesson
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Attendance button
    # -----------------------------------------------------

    already_present = False

    conn = db()

    check = conn.execute(
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

    conn.close()

    if check:

        already_present = True

    if already_present:

        st.success(
            "✅ أنت مسجل حضور في هذه الحصة بالفعل."
        )

        return

    st.markdown(
        "### 📷 تسجيل الحضور"
    )

    st.write(
        "اضغط الزر أولاً، وبعدها ستظهر لك الكاميرا."
    )

    # -----------------------------------------------------
    # Camera is NOT opened automatically
    # -----------------------------------------------------

    scan_mode = st.session_state.get(
        "scan_mode",
        False,
    )

    if not scan_mode:

        if st.button(
            "📷 مسح QR وتسجيل الحضور",
            use_container_width=True,
        ):

            st.session_state.scan_mode = True

            st.rerun()

        return

    # -----------------------------------------------------
    # Camera
    # -----------------------------------------------------

    st.info(
        "📷 وجّه الكاميرا إلى QR الموجود عند المدرس."
    )

    scan = st.camera_input(
        "📷 تصوير QR",
        key="attendance_camera",
    )

    if scan is None:

        if st.button(
            "❌ إلغاء المسح",
            use_container_width=True,
        ):

            st.session_state.scan_mode = False

            st.rerun()

        return

    token = decode_qr(scan)

    if not token:

        st.error(
            "❌ لم أستطع قراءة QR. حاول تصويره بوضوح."
        )

        return

    ok, message = mark_attendance(
        token,
        student_id,
    )

    if ok:

        st.session_state.scan_mode = False

        st.success(message)

        st.balloons()

        st.rerun()

    else:

        st.error(message)


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 لوحة المدرس",
        "إدارة الحصص والحضور",
    )

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

            st.session_state.teacher_logged_in = (
                True
            )

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# TEACHER STUDENT LINK
# =========================================================

def teacher_student_link():

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.write(
        """
        ابعت الرابط ده للطلاب.

        الطالب يفتحه ويسجل بياناته أول مرة.
        """
    )

    link = student_url()

    st.code(
        link,
        language="text",
    )

    st.success(
        "📱 هذا هو الرابط الذي ترسله للطلاب."
    )


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    current = active_lesson()

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
            "يجب إنهاء الحصة الحالية أولاً."
        )

        return

    # -----------------------------------------------------
    # Get grades with students
    # -----------------------------------------------------

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
        if row["grade"] in GRADES
    ]

    if not available_grades:

        available_grades = GRADES

    grade = st.selectbox(
        "🎓 الصف",
        available_grades,
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        # Double check
        current = active_lesson()

        if current is not None:

            st.error(
                "❌ توجد حصة مفتوحة بالفعل."
            )

            return

        lesson_name = lesson_name.strip()

        if not lesson_name:

            lesson_name = "الحصة الحالية"

        token = secrets.token_urlsafe(
            32
        )

        conn = db()

        conn.execute(
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

        conn.commit()
        conn.close()

        st.success(
            "🎉 تم بدء الحصة بنجاح."
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

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    total, present, absent = lesson_statistics(
        lesson["id"],
        lesson["grade"],
    )

    # -----------------------------------------------------
    # Lesson information
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
    # Statistics
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 طلاب الصف",
        total,
    )

    c2.metric(
        "✅ الحاضرون الآن",
        present,
    )

    c3.metric(
        "❌ الغائبون الآن",
        absent,
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
        caption="الطلاب يمسحون هذا الكود لتسجيل الحضور",
        width=350,
    )

    st.divider()

    # -----------------------------------------------------
    # Attendance table
    # -----------------------------------------------------

    st.subheader(
        "📋 حالة طلاب الصف"
    )

    conn = db()

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,

            a.marked_at

        FROM students s

        LEFT JOIN attendance a

            ON a.student_id = s.id

            AND a.lesson_id = ?

        WHERE s.grade = ?

        ORDER BY s.name
        """,
        (
            lesson["id"],
            lesson["grade"],
        ),
    ).fetchall()

    conn.close()

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

    if table:

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
    # Refresh
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True,
    ):

        st.rerun()

    # -----------------------------------------------------
    # End lesson
    # -----------------------------------------------------

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True,
    ):

        conn = db()

        conn.execute(
            """
            UPDATE lessons

            SET
                active = 0,
                ended_at = ?

            WHERE id = ?

            AND active = 1
            """,
            (
                now(),
                lesson["id"],
            ),
        )

        conn.commit()
        conn.close()

        st.success(
            "✅ تم إنهاء الحصة وتثبيت الحضور والغياب."
        )

        st.rerun()


# =========================================================
# ALL STUDENTS
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
    )

    conn = db()

    total_platform = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM students
        """
    ).fetchone()["c"]

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
        "👨‍🎓 إجمالي طلاب المنصة",
        total_platform,
    )

    if rows:

        data = []

        for row in rows:

            data.append(
                {
                    "ID": row["id"],
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"],
                    "هاتف ولي الأمر": row[
                        "parent_phone"
                    ],
                    "الصف": row["grade"],
                    "تاريخ التسجيل": row[
                        "created_at"
                    ],
                }
            )

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.subheader(
        "📋 التقارير"
    )

    conn = db()

    total_platform = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM students
        """
    ).fetchone()["c"]

    total_lessons = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM lessons
        """
    ).fetchone()["c"]

    conn.close()

    c1, c2 = st.columns(2)

    c1.metric(
        "👨‍🎓 طلاب المنصة",
        total_platform,
    )

    c2.metric(
        "📚 إجمالي الحصص",
        total_lessons,
    )

    st.divider()

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
            f"{status} | {lesson['lesson_name']} | {lesson['grade']}"
        ):

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "طلاب الصف",
                total,
            )

            c2.metric(
                "حضر",
                present,
            )

            c3.metric(
                "غاب",
                absent,
            )

            st.write(
                f"بدأت: {lesson['created_at']}"
            )

            if lesson["ended_at"]:

                st.write(
                    f"انتهت: {lesson['ended_at']}"
                )


# =========================================================
# SETTINGS
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    st.write(
        "🔐 تغيير كلمة المرور"
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

        submit = st.form_submit_button(
            "🔐 تغيير كلمة المرور",
            use_container_width=True,
        )

    if submit:

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

        elif len(new) < 4:

            st.error(
                "❌ كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل."
            )

        elif new != confirm:

            st.error(
                "❌ كلمتا المرور غير متطابقتين."
            )

        else:

            set_setting(
                "teacher_password_hash",
                hash_password(new),
            )

            st.success(
                "✅ تم تغيير كلمة المرور."
            )


# =========================================================
# TEACHER DASHBOARD
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
    # Logout
    # -----------------------------------------------------

    if st.button(
        "🚪 تسجيل خروج",
        use_container_width=True,
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    # -----------------------------------------------------
    # Student link
    # -----------------------------------------------------

    teacher_student_link()

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

        students_page()

    with tabs[3]:

        reports_page()

    with tabs[4]:

        settings_page()


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    # -----------------------------------------------------
    # IMPORTANT:
    # Default page is TEACHER
    # -----------------------------------------------------

    page = st.query_params.get(
        "page",
        "teacher",
    )

    # -----------------------------------------------------
    # Student page only when explicitly requested
    # -----------------------------------------------------

    if page == "student":

        student_page()

    # -----------------------------------------------------
    # Everything else = teacher
    # -----------------------------------------------------

    else:

        teacher_dashboard()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
