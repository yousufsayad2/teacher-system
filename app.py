import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import hashlib
from datetime import datetime


# =========================================================
# CONFIG
# =========================================================

DB_FILE = "attendance_platform.db"

TEACHER_DEFAULT_PASSWORD = "1234"

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
# PAGE
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide"
)


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>

    .main-title {
        text-align: center;
        font-size: 48px;
        font-weight: 900;
        margin-top: 20px;
    }

    .sub-title {
        text-align: center;
        font-size: 23px;
        margin-bottom: 30px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def current_time():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =========================================================
# INITIAL DATABASE
# =========================================================

def init_database():

    conn = get_db()

    cursor = conn.cursor()

    # SETTINGS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # STUDENTS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT,
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL DEFAULT 'المجموعة الأولى',
            created_at TEXT NOT NULL
        )
        """
    )

    # LESSONS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            qr_token TEXT NOT NULL UNIQUE
        )
        """
    )

    # ATTENDANCE
    cursor.execute(
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

    # TEACHER PASSWORD
    row = cursor.execute(
        """
        SELECT value
        FROM settings
        WHERE key = 'teacher_password'
        """
    ).fetchone()

    if row is None:

        cursor.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            """,
            (
                "teacher_password",
                hash_password(
                    TEACHER_DEFAULT_PASSWORD
                )
            )
        )

    conn.commit()
    conn.close()


# =========================================================
# DATABASE MIGRATION
# =========================================================

def migrate_database():

    conn = get_db()

    cursor = conn.cursor()

    # -----------------------------------------------------
    # STUDENTS COLUMNS
    # -----------------------------------------------------

    student_columns = [
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(students)"
        ).fetchall()
    ]

    if "group_name" not in student_columns:

        cursor.execute(
            """
            ALTER TABLE students
            ADD COLUMN group_name TEXT
            DEFAULT 'المجموعة الأولى'
            """
        )

    # -----------------------------------------------------
    # LESSON COLUMNS
    # -----------------------------------------------------

    lesson_columns = [
        row["name"]
        for row in cursor.execute(
            "PRAGMA table_info(lessons)"
        ).fetchall()
    ]

    if "group_name" not in lesson_columns:

        cursor.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN group_name TEXT
            DEFAULT 'المجموعة الأولى'
            """
        )

    if "ended_at" not in lesson_columns:

        cursor.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN ended_at TEXT
            """
        )

    if "qr_token" not in lesson_columns:

        cursor.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN qr_token TEXT
            """
        )

        rows = cursor.execute(
            """
            SELECT id
            FROM lessons
            WHERE qr_token IS NULL
            """
        ).fetchall()

        for row in rows:

            cursor.execute(
                """
                UPDATE lessons
                SET qr_token = ?
                WHERE id = ?
                """,
                (
                    secrets.token_urlsafe(32),
                    row["id"]
                )
            )

    # -----------------------------------------------------
    # FIX EMPTY GROUPS
    # -----------------------------------------------------

    cursor.execute(
        """
        UPDATE students
        SET group_name = 'المجموعة الأولى'
        WHERE group_name IS NULL
        OR TRIM(group_name) = ''
        """
    )

    cursor.execute(
        """
        UPDATE lessons
        SET group_name = 'المجموعة الأولى'
        WHERE group_name IS NULL
        OR TRIM(group_name) = ''
        """
    )

    # -----------------------------------------------------
    # VERY IMPORTANT:
    # CLOSE BROKEN OLD ACTIVE LESSONS
    #
    # We only allow ONE active lesson.
    # -----------------------------------------------------

    active_lessons = cursor.execute(
        """
        SELECT id
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    if len(active_lessons) > 1:

        keep_id = active_lessons[0]["id"]

        for row in active_lessons[1:]:

            cursor.execute(
                """
                UPDATE lessons
                SET
                    active = 0,
                    ended_at = ?
                WHERE id = ?
                """,
                (
                    current_time(),
                    row["id"]
                )
            )

    conn.commit()
    conn.close()


# =========================================================
# PASSWORD
# =========================================================

def hash_password(password):

    salt = secrets.token_bytes(16)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        100000
    )

    return (
        salt.hex()
        + ":"
        + key.hex()
    )


def check_password(password, stored):

    try:

        salt_hex, key_hex = stored.split(":")

        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            100000
        )

        return secrets.compare_digest(
            key.hex(),
            key_hex
        )

    except Exception:

        return False


# =========================================================
# SETTINGS
# =========================================================

def get_setting(key):

    conn = get_db()

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


def save_setting(key, value):

    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (
            key,
            value
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# URLS
# =========================================================

def get_base_url():

    try:

        url = st.context.url

        if "?" in url:
            url = url.split("?")[0]

        return url

    except Exception:

        return ""


def get_student_url():

    return (
        get_base_url()
        + "?page=student"
    )


def get_teacher_url():

    return (
        get_base_url()
        + "?page=teacher"
    )


# =========================================================
# ACTIVE LESSON
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
# GET STUDENT
# =========================================================

def get_student(student_id):

    conn = get_db()

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
# STUDENT REGISTRATION
# =========================================================

def student_registration():

    st.markdown(
        """
        <div class="main-title">
        🎓 منصة الحضور
        </div>

        <div class="sub-title">
        📝 تسجيل الطالب في المنصة
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info(
        """
        👋 التسجيل يتم مرة واحدة فقط.

        بعد التسجيل لن تحتاج إلى كتابة بياناتك مرة أخرى.

        📱 كل حصة يتم تسجيل الحضور فيها عن طريق QR الخاص بالمدرس.
        """
    )

    with st.form("student_register"):

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

        group_name = st.selectbox(
            "👥 المجموعة",
            GROUPS
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

    conn = get_db()

    try:

        cursor = conn.execute(
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
                current_time()
            )
        )

        conn.commit()

        student_id = cursor.lastrowid

        st.session_state.student_id = student_id

        st.query_params["page"] = "student"
        st.query_params["student"] = str(student_id)

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
            (phone,)
        ).fetchone()

        if existing:

            st.session_state.student_id = existing["id"]

            st.query_params["page"] = "student"
            st.query_params["student"] = str(
                existing["id"]
            )

            st.success(
                "✅ الطالب مسجل بالفعل."
            )

            st.rerun()

        else:

            st.error(
                "❌ حدث خطأ أثناء التسجيل."
            )

    finally:

        conn.close()


# =========================================================
# QR DECODER
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
# MARK ATTENDANCE
# =========================================================

def mark_student_attendance(
    student_id,
    token
):

    conn = get_db()

    try:

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE qr_token = ?
            AND active = 1
            """,
            (token,)
        ).fetchone()

        if lesson is None:

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

            return (
                False,
                "❌ الطالب غير مسجل."
            )

        if student["grade"] != lesson["grade"]:

            return (
                False,
                "❌ هذه الحصة ليست لصفك."
            )

        if (
            student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذه الحصة ليست لمجموعتك."
            )

        old = conn.execute(
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

        if old:

            return (
                True,
                "✅ أنت سجلت حضورك بالفعل."
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
                current_time()
            )
        )

        conn.commit()

        return (
            True,
            "🎉 تم تسجيل حضورك بنجاح."
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            "❌ حدث خطأ أثناء تسجيل الحضور."
        )

    finally:

        conn.close()


# =========================================================
# STUDENT ATTENDANCE PAGE
# =========================================================

def student_attendance(student):

    st.markdown(
        """
        <div class="main-title">
        🎓 منصة الحضور
        </div>

        <div class="sub-title">
        👨‍🎓 واجهة الطالب
        </div>
        """,
        unsafe_allow_html=True
    )

    st.success(
        f"👋 أهلاً يا {student['name']}"
    )

    st.write(
        f"🎓 **الصف:** {student['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {student['group_name']}"
    )

    st.divider()

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة حاليًا.

            عندما يبدأ المدرس الحصة،
            ستظهر إمكانية تسجيل الحضور هنا.
            """
        )

        return

    # -----------------------------------------------------
    # CHECK CLASS
    # -----------------------------------------------------

    if (
        lesson["grade"] != student["grade"]
        or
        lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            f"""
            ⏳ توجد حصة مفتوحة حاليًا،
            لكنها ليست لصفك أو مجموعتك.

            📚 الحصة: {lesson['lesson_name']}

            🎓 الصف: {lesson['grade']}

            👥 المجموعة: {lesson['group_name']}
            """
        )

        return

    # -----------------------------------------------------
    # ALREADY ATTENDED
    # -----------------------------------------------------

    conn = get_db()

    attendance = conn.execute(
        """
        SELECT marked_at
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

    st.success(
        f"""
        🟢 الحصة مفتوحة الآن

        📚 {lesson['lesson_name']}

        🎓 {lesson['grade']}

        👥 {lesson['group_name']}
        """
    )

    if attendance:

        st.success(
            f"""
            ✅ تم تسجيل حضورك بالفعل.

            🕐 وقت الحضور:
            {attendance['marked_at']}
            """
        )

        return

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        "اضغط على الكاميرا بنفسك وصوّر QR الموجود عند المدرس."
    )

    # -----------------------------------------------------
    # CAMERA IS NOT OPEN AUTOMATICALLY
    # -----------------------------------------------------

    photo = st.camera_input(
        "📷 افتح الكاميرا لتصوير QR",
        key="student_qr_camera"
    )

    if photo is None:
        return

    token = decode_qr(photo)

    if not token:

        st.error(
            "❌ لم يتم قراءة QR. حاول مرة أخرى."
        )

        return

    success, message = mark_student_attendance(
        student["id"],
        token
    )

    if success:

        st.success(message)

        st.rerun()

    else:

        st.error(message)


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    student_id = st.session_state.get(
        "student_id"
    )

    query_id = st.query_params.get(
        "student"
    )

    # -----------------------------------------------------
    # GET ID FROM URL
    # -----------------------------------------------------

    if (
        student_id is None
        and query_id
    ):

        try:

            student_id = int(query_id)

            st.session_state.student_id = student_id

        except Exception:

            student_id = None

    # -----------------------------------------------------
    # REGISTER
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
            None
        )

        st.query_params.clear()

        st.query_params["page"] = "student"

        st.rerun()

        return

    student_attendance(
        student
    )


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    st.markdown(
        """
        <div class="main-title">
        👨‍🏫 لوحة المدرس
        </div>

        <div class="sub-title">
        🔐 إدارة الحصص والحضور
        </div>
        """,
        unsafe_allow_html=True
    )

    st.info(
        "هذه الصفحة خاصة بالمدرس."
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
            "teacher_password"
        )

        if (
            stored
            and check_password(
                password,
                stored
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
# CREATE LESSON
# =========================================================

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    active = get_active_lesson()

    if active:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة بالفعل.

            📚 الحصة: {active['lesson_name']}

            🎓 الصف: {active['grade']}

            👥 المجموعة: {active['group_name']}

            🕐 بدأت: {active['created_at']}
            """
        )

        if st.button(
            "🔴 إنهاء الحصة الحالية",
            use_container_width=True
        ):

            finish_lesson(
                active["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="create_grade"
    )

    group_name = st.selectbox(
        "👥 المجموعة",
        GROUPS,
        key="create_group"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="create_lesson_name"
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True
    ):

        if not lesson_name.strip():

            st.error(
                "❌ اكتب اسم الحصة."
            )

            return

        # -------------------------------------------------
        # DOUBLE CHECK
        # -------------------------------------------------

        check = get_active_lesson()

        if check:

            st.error(
                "❌ توجد حصة مفتوحة بالفعل."
            )

            return

        conn = get_db()

        token = secrets.token_urlsafe(
            32
        )

        conn.execute(
            """
            INSERT INTO lessons(
                lesson_name,
                grade,
                group_name,
                created_at,
                ended_at,
                active,
                qr_token
            )

            VALUES (?, ?, ?, ?, NULL, 1, ?)
            """,
            (
                lesson_name.strip(),
                grade,
                group_name,
                current_time(),
                token
            )
        )

        conn.commit()
        conn.close()

        st.success(
            "🎉 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# FINISH LESSON
# =========================================================

def finish_lesson(
    lesson_id
):

    conn = get_db()

    conn.execute(
        """
        UPDATE lessons
        SET
            active = 0,
            ended_at = ?
        WHERE id = ?
        """,
        (
            current_time(),
            lesson_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# LESSON STUDENTS
# =========================================================

def get_lesson_students(
    lesson
):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.parent_phone,
            a.marked_at

        FROM students s

        LEFT JOIN attendance a

        ON
            s.id = a.student_id
            AND a.lesson_id = ?

        WHERE
            s.grade = ?
            AND s.group_name = ?

        ORDER BY s.name
        """,
        (
            lesson["id"],
            lesson["grade"],
            lesson["group_name"]
        )
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# LESSON STATISTICS
# =========================================================

def get_lesson_statistics(
    lesson
):

    students = get_lesson_students(
        lesson
    )

    total = len(students)

    present = len(
        [
            x for x in students
            if x["marked_at"]
        ]
    )

    absent = total - present

    return total, present, absent


# =========================================================
# CURRENT LESSON
# =========================================================

def current_lesson():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    st.markdown(
        f"""
        ## 📚 {lesson["lesson_name"]}

        🎓 **الصف:** {lesson["grade"]}

        👥 **المجموعة:** {lesson["group_name"]}

        🕐 **بدأت:** {lesson["created_at"]}
        """
    )

    total, present, absent = (
        get_lesson_statistics(
            lesson
        )
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

    # -----------------------------------------------------
    # QR
    # -----------------------------------------------------

    st.subheader(
        "📱 QR الحضور"
    )

    qr = qrcode.make(
        lesson["qr_token"]
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        width=350,
        caption="📱 الطلاب يصورون هذا الكود"
    )

    st.divider()

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True
    ):

        st.rerun()

    # -----------------------------------------------------
    # STUDENTS
    # -----------------------------------------------------

    st.subheader(
        "📋 حالة طلاب الحصة"
    )

    rows = get_lesson_students(
        lesson
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
            "لا يوجد طلاب في هذه المجموعة."
        )

    st.divider()

    # -----------------------------------------------------
    # FINISH
    # -----------------------------------------------------

    if st.button(
        "🔴 إنهاء الحصة وحفظ النتائج",
        use_container_width=True
    ):

        finish_lesson(
            lesson["id"]
        )

        st.success(
            "✅ تم إنهاء الحصة وحفظ نتائجها."
        )

        st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports():

    st.subheader(
        "📋 التقارير وسجل الحصص"
    )

    conn = get_db()

    lessons = conn.execute(
        """
        SELECT *
        FROM lessons
        ORDER BY id DESC
        """
    ).fetchall()

    platform_students = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

    conn.close()

    st.metric(
        "👨‍🎓 إجمالي طلاب المنصة",
        platform_students
    )

    if not lessons:

        st.info(
            "📭 لا توجد حصص محفوظة."
        )

        return

    summary = []

    for lesson in lessons:

        total, present, absent = (
            get_lesson_statistics(
                lesson
            )
        )

        summary.append(
            {
                "الحصة": lesson["lesson_name"],
                "الصف": lesson["grade"],
                "المجموعة": lesson["group_name"],
                "التاريخ والوقت": lesson["created_at"],
                "وقت الانتهاء": lesson["ended_at"] or "-",
                "الطلاب المسجلون": total,
                "الحضور": present,
                "الغياب": absent,
                "الحالة": (
                    "🟢 مفتوحة"
                    if lesson["active"]
                    else "🔴 منتهية"
                )
            }
        )

    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

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
        "📚 اختر حصة",
        list(options.keys())
    )

    lesson_id = options[selected]

    conn = get_db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (lesson_id,)
    ).fetchone()

    conn.close()

    total, present, absent = (
        get_lesson_statistics(
            lesson
        )
    )

    st.subheader(
        "📖 تفاصيل الحصة"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 المسجلون",
        total
    )

    c2.metric(
        "📱 سجلوا حضور",
        present
    )

    c3.metric(
        "✅ الحضور",
        present
    )

    c4.metric(
        "❌ الغياب",
        absent
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
        f"📅 **التاريخ:** {lesson['created_at']}"
    )

    st.write(
        f"⏰ **الانتهاء:** {lesson['ended_at'] or '-'}"
    )

    rows = get_lesson_students(
        lesson
    )

    st.subheader(
        "✅ الحاضرون"
    )

    present_rows = [
        row for row in rows
        if row["marked_at"]
    ]

    if present_rows:

        st.dataframe(
            [
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
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

    st.subheader(
        "❌ الغائبون"
    )

    absent_rows = [
        row for row in rows
        if not row["marked_at"]
    ]

    if absent_rows:

        st.dataframe(
            [
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "الحالة": "❌ غائب"
                }
                for row in absent_rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.success(
            "🎉 كل الطلاب حضروا."
        )


# =========================================================
# STUDENTS
# =========================================================

def students():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون في المنصة"
    )

    conn = get_db()

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

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
        total
    )

    if not rows:

        st.info(
            "لا يوجد طلاب حتى الآن."
        )

        return

    table = []

    for row in rows:

        table.append(
            {
                "ID": row["id"],
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "تاريخ التسجيل": row["created_at"]
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# STUDENT LINK
# =========================================================

def student_link():

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    link = get_student_url()

    st.success(
        "📱 ابعت الرابط ده للطلاب."
    )

    st.code(
        link,
        language="text"
    )

    st.markdown(
        """
        ### طريقة الطالب

        1. يفتح الرابط.

        2. يسجل بياناته أول مرة فقط.

        3. بعد التسجيل تظل بياناته محفوظة.

        4. عند بدء المدرس للحصة تظهر له الحصة المناسبة.

        5. يضغط على الكاميرا.

        6. يصور QR الموجود عند المدرس.

        7. يظهر الحضور عند المدرس فورًا.
        """
    )


# =========================================================
# SETTINGS
# =========================================================

def teacher_settings():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    st.write(
        "🔐 تغيير كلمة المرور"
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
            "💾 حفظ",
            use_container_width=True
        )

    if save:

        stored = get_setting(
            "teacher_password"
        )

        if not check_password(
            old,
            stored
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

            return

        if len(new) < 4:

            st.error(
                "❌ كلمة المرور قصيرة جدًا."
            )

            return

        if new != confirm:

            st.error(
                "❌ كلمتا المرور غير متطابقتين."
            )

            return

        save_setting(
            "teacher_password",
            hash_password(new)
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
        False
    ):

        teacher_login()

        return

    st.markdown(
        """
        <div class="main-title">
        👨‍🏫 لوحة تحكم المدرس
        </div>

        <div class="sub-title">
        إدارة الحصص والحضور
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    # -----------------------------------------------------
    # STUDENT LINK ALWAYS VISIBLE
    # -----------------------------------------------------

    st.info(
        "📱 رابط الطالب الذي ترسله للطلاب:"
    )

    st.code(
        get_student_url(),
        language="text"
    )

    st.divider()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "🔗 رابط الطالب",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lesson()

    with tabs[2]:

        reports()

    with tabs[3]:

        students()

    with tabs[4]:

        student_link()

    with tabs[5]:

        teacher_settings()


# =========================================================
# MAIN
# =========================================================

def main():

    init_database()

    migrate_database()

    page = st.query_params.get(
        "page",
        "teacher"
    )

    # =====================================================
    # DEFAULT = TEACHER
    # =====================================================

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
