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
# إعدادات المنصة
# =========================================================

DB_FILE = "teacher_system_clean.db"

DEFAULT_TEACHER_PASSWORD = "1234"

GROUPS = [
    "المجموعة 1",
    "المجموعة 2",
    "المجموعة 3",
]

GROUP_CAPACITY = 70

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]


# =========================================================
# إعداد Streamlit
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide"
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
        padding-bottom: 5rem;
    }

    .main-title {
        text-align: center;
        font-size: 46px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .subtitle {
        text-align: center;
        font-size: 20px;
        margin-bottom: 30px;
    }

    .student-card {
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 15px;
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

    conn.execute("PRAGMA foreign_keys = ON")

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
        120000
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
            120000
        )

        return secrets.compare_digest(
            digest.hex(),
            digest_hex
        )

    except Exception:
        return False


# =========================================================
# أدوات SQLite للمigration
# =========================================================

def get_columns(conn, table_name):

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def add_column_if_missing(
    conn,
    table_name,
    column_name,
    column_definition
):

    existing_columns = get_columns(
        conn,
        table_name
    )

    if column_name not in existing_columns:

        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )


# =========================================================
# إنشاء / تحديث قاعدة البيانات
# =========================================================

def init_db():

    conn = db()

    # -----------------------------
    # Settings
    # -----------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (

            key TEXT PRIMARY KEY,

            value TEXT NOT NULL

        )
        """
    )

    # -----------------------------
    # Students
    # -----------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            phone TEXT NOT NULL UNIQUE,

            parent_phone TEXT DEFAULT '',

            grade TEXT NOT NULL,

            group_name TEXT DEFAULT 'المجموعة 1',

            created_at TEXT NOT NULL

        )
        """
    )

    # -----------------------------
    # Lessons
    # -----------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lessons (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            grade TEXT NOT NULL,

            group_name TEXT DEFAULT 'المجموعة 1',

            lesson_name TEXT NOT NULL,

            created_at TEXT NOT NULL,

            ended_at TEXT,

            active INTEGER NOT NULL DEFAULT 1,

            token TEXT NOT NULL UNIQUE

        )
        """
    )

    # -----------------------------
    # Attendance
    # -----------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            lesson_id INTEGER NOT NULL,

            student_id INTEGER NOT NULL,

            marked_at TEXT NOT NULL,

            UNIQUE(
                lesson_id,
                student_id
            )

        )
        """
    )

    # =====================================================
    # Migration
    # =====================================================

    # لو قاعدة البيانات القديمة ناقصها group_name
    add_column_if_missing(
        conn,
        "students",
        "group_name",
        "TEXT DEFAULT 'المجموعة 1'"
    )

    add_column_if_missing(
        conn,
        "lessons",
        "group_name",
        "TEXT DEFAULT 'المجموعة 1'"
    )

    # إصلاح أي سجلات قديمة بدون مجموعة
    conn.execute(
        """
        UPDATE students

        SET group_name = 'المجموعة 1'

        WHERE group_name IS NULL
        OR group_name = ''
        """
    )

    conn.execute(
        """
        UPDATE lessons

        SET group_name = 'المجموعة 1'

        WHERE group_name IS NULL
        OR group_name = ''
        """
    )

    # =====================================================
    # كلمة مرور المدرس
    # =====================================================

    password_row = conn.execute(
        """
        SELECT value

        FROM settings

        WHERE key = 'teacher_password_hash'
        """
    ).fetchone()

    if password_row is None:

        conn.execute(
            """
            INSERT INTO settings(
                key,
                value
            )

            VALUES(
                ?,
                ?
            )
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

    if row:
        return row["value"]

    return None


def set_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT OR REPLACE INTO settings(
            key,
            value
        )

        VALUES(
            ?,
            ?
        )
        """,
        (
            key,
            value
        )
    )

    conn.commit()

    conn.close()


# =========================================================
# روابط المنصة
# =========================================================

def base_url():

    try:

        current_url = st.context.url

        parts = urlsplit(
            current_url
        )

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
        return base + "?page=student"

    return "?page=student"


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


# =========================================================
# الحصص
# =========================================================

def get_lesson(lesson_id):

    conn = db()

    row = conn.execute(
        """
        SELECT *

        FROM lessons

        WHERE id = ?
        """,
        (lesson_id,)
    ).fetchone()

    conn.close()

    return row


def get_active_lessons(
    grade=None,
    group_name=None
):

    conn = db()

    query = """
        SELECT *

        FROM lessons

        WHERE active = 1
    """

    params = []

    if grade is not None:

        query += """
            AND grade = ?
        """

        params.append(
            grade
        )

    if group_name is not None:

        query += """
            AND group_name = ?
        """

        params.append(
            group_name
        )

    query += """
        ORDER BY id DESC
    """

    rows = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# عدد طلاب المجموعة
# =========================================================

def group_count(
    grade,
    group_name
):

    conn = db()

    row = conn.execute(
        """
        SELECT COUNT(*) AS c

        FROM students

        WHERE grade = ?

        AND group_name = ?
        """,
        (
            grade,
            group_name
        )
    ).fetchone()

    conn.close()

    return row["c"]


# =========================================================
# تعيين مجموعة تلقائيًا
# =========================================================

def assign_group(grade):

    for group in GROUPS:

        count = group_count(
            grade,
            group
        )

        if count < GROUP_CAPACITY:

            return group

    return None


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_stats(lesson_id):

    conn = db()

    lesson = conn.execute(
        """
        SELECT grade, group_name

        FROM lessons

        WHERE id = ?
        """,
        (lesson_id,)
    ).fetchone()

    if lesson is None:

        conn.close()

        return 0, 0, 0

    total = conn.execute(
        """
        SELECT COUNT(*) AS c

        FROM students

        WHERE grade = ?

        AND group_name = ?
        """,
        (
            lesson["grade"],
            lesson["group_name"]
        )
    ).fetchone()["c"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS c

        FROM attendance

        WHERE lesson_id = ?
        """,
        (lesson_id,)
    ).fetchone()["c"]

    conn.close()

    absent = max(
        total - present,
        0
    )

    return (
        total,
        present,
        absent
    )


# =========================================================
# طلاب الحصة
# =========================================================

def lesson_students(lesson_id):

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

        JOIN lessons l

            ON l.id = ?

            AND l.grade = s.grade

            AND l.group_name = s.group_name

        LEFT JOIN attendance a

            ON a.lesson_id = l.id

            AND a.student_id = s.id

        ORDER BY

            CASE

                WHEN a.marked_at IS NULL

                THEN 1

                ELSE 0

            END,

            a.marked_at,

            s.name
        """,
        (lesson_id,)
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# تسجيل الحضور
# =========================================================

def mark_attendance(
    token,
    student_id
):

    conn = db()

    # -----------------------------
    # الحصة
    # -----------------------------

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

    # -----------------------------
    # الطالب
    # -----------------------------

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

    # -----------------------------
    # التأكد من الصف والمجموعة
    # -----------------------------

    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست لمجموعة الطالب."
        )

    # -----------------------------
    # هل سجل قبل كده؟
    # -----------------------------

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

    # -----------------------------
    # تسجيل الحضور
    # -----------------------------

    conn.execute(
        """
        INSERT INTO attendance(
            lesson_id,
            student_id,
            marked_at
        )

        VALUES(
            ?,
            ?,
            ?
        )
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

        pass

    return None


# =========================================================
# Header
# =========================================================

def render_header(
    title,
    subtitle=""
):

    st.markdown(
        f"""
        <div class="main-title">
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

    render_header(
        "🎓 منصة الحضور",
        "واجهة الطالب"
    )

    student_id = (
        st.session_state
        .get("student_id")
    )

    query_student = (
        st.query_params
        .get("student")
    )

    # --------------------------------
    # استرجاع الطالب من الرابط
    # --------------------------------

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

    # =====================================================
    # التسجيل لأول مرة
    # =====================================================

    if student_id is None:

        st.info(
            """
            📝 التسجيل في المنصة يتم مرة واحدة فقط.

            بعد التسجيل لن تحتاج لإدخال بياناتك كل حصة.

            في كل حصة فقط صوّر QR الموجود عند المدرس.
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

            # -----------------------------
            # تعيين المجموعة
            # -----------------------------

            group = assign_group(
                grade
            )

            if group is None:

                st.error(
                    "❌ المجموعات الثلاث ممتلئة لهذا الصف. الحد الأقصى 210 طالب."
                )

                return

            conn = db()

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

                    VALUES(
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        name,
                        phone,
                        parent_phone,
                        grade,
                        group,
                        now()
                    )
                )

                conn.commit()

                new_id = cursor.lastrowid

                conn.close()

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
                    f"🎉 تم تسجيلك بنجاح في {group}."
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

                conn.close()

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

                else:

                    st.error(
                        "❌ حدث خطأ أثناء التسجيل."
                    )

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
        f"**الصف:** {student['grade']}"
    )

    st.write(
        f"**المجموعة:** {student['group_name']}"
    )

    # =====================================================
    # الحصة
    # =====================================================

    active_lessons = get_active_lessons(
        student["grade"],
        student["group_name"]
    )

    if not active_lessons:

        st.info(
            "⏳ لا توجد حصة مفتوحة لمجموعتك حالياً."
        )

        return

    lesson = active_lessons[0]

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🗓️ بدأت الحصة: {lesson['created_at']}"
    )

    st.info(
        "📷 صوّر QR الموجود عند المدرس لتسجيل حضورك."
    )

    # =====================================================
    # الكاميرا
    # =====================================================

    scan = st.camera_input(
        "📷 مسح QR الحضور",
        key=f"attendance_camera_{lesson['id']}"
    )

    if scan is not None:

        token = decode_qr(
            scan
        )

        if not token:

            st.error(
                "❌ لم يتم قراءة QR بوضوح. حاول مرة أخرى."
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

            else:

                st.error(
                    message
                )


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 منصة الحضور",
        "دخول المدرس"
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "👨‍🏫 دخول المدرس",
        use_container_width=True
    ):

        stored = get_setting(
            "teacher_password_hash"
        )

        if (
            stored
            and
            verify_password(
                password,
                stored
            )
        ):

            st.session_state.teacher_logged_in = (
                True
            )

            st.query_params["page"] = (
                "teacher"
            )

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.caption(
        "كلمة المرور الافتراضية أول مرة: 1234"
    )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="new_lesson_grade"
    )

    group = st.selectbox(
        "👥 المجموعة",
        GROUPS,
        key="new_lesson_group"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية"
    )

    students_number = group_count(
        grade,
        group
    )

    st.info(
        f"👨‍🎓 عدد الطلاب في المجموعة: {students_number}/{GROUP_CAPACITY}"
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True
    ):

        if students_number == 0:

            st.warning(
                "⚠️ لا يوجد طلاب مسجلون في هذه المجموعة."
            )

            return

        conn = db()

        # --------------------------------
        # إنهاء أي حصة قديمة لنفس المجموعة
        # --------------------------------

        conn.execute(
            """
            UPDATE lessons

            SET

                active = 0,

                ended_at =
                    COALESCE(
                        ended_at,
                        ?
                    )

            WHERE active = 1

            AND grade = ?

            AND group_name = ?
            """,
            (
                now(),
                grade,
                group
            )
        )

        token = secrets.token_urlsafe(
            32
        )

        lesson_name = (
            lesson_name.strip()
            or
            "الحصة الحالية"
        )

        conn.execute(
            """
            INSERT INTO lessons(

                grade,

                group_name,

                lesson_name,

                created_at,

                active,

                token

            )

            VALUES(
                ?,
                ?,
                ?,
                ?,
                1,
                ?
            )
            """,
            (
                grade,
                group,
                lesson_name,
                now(),
                token
            )
        )

        conn.commit()

        conn.close()

        st.success(
            "🟢 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصص الحالية
# =========================================================

def current_lessons_page():

    st.subheader(
        "📊 الحصص المفتوحة حالياً"
    )

    active_lessons = get_active_lessons()

    if not active_lessons:

        st.info(
            "⏳ لا توجد حصص مفتوحة حالياً."
        )

        return

    options = {}

    for lesson in active_lessons:

        label = (
            f"#{lesson['id']} — "
            f"{lesson['grade']} — "
            f"{lesson['group_name']} — "
            f"{lesson['lesson_name']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys())
    )

    lesson_id = options[selected]

    lesson = get_lesson(
        lesson_id
    )

    total, present, absent = lesson_stats(
        lesson_id
    )

    # =====================================================
    # الإحصائيات
    # =====================================================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👥 إجمالي المسجلين",
        total
    )

    c2.metric(
        "📷 سجلوا حضور",
        present
    )

    c3.metric(
        "❌ الغائبون",
        absent
    )

    c4.metric(
        "🟢 الحاضرون الآن",
        present
    )

    st.divider()

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"**الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**تاريخ ووقت البداية:** {lesson['created_at']}"
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
        width=350,
        caption="📷 الطلاب يمسحون هذا الكود"
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
    # جدول الطلاب
    # =====================================================

    st.subheader(
        "👨‍🎓 حالة طلاب المجموعة"
    )

    rows = lesson_students(
        lesson_id
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
            "لا يوجد طلاب."
        )

    st.divider()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    if st.button(
        "⛔ إنهاء الحصة وحفظها",
        use_container_width=True
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
                lesson_id
            )
        )

        conn.commit()

        conn.close()

        st.success(
            "✅ تم إنهاء الحصة وحفظ الحضور والغياب والتاريخ والوقت."
        )

        st.rerun()


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 الحصص المحفوظة"
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
            "لا توجد حصص محفوظة حتى الآن."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} — "
            f"{lesson['grade']} — "
            f"{lesson['group_name']} — "
            f"{lesson['lesson_name']} — "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys())
    )

    lesson_id = options[selected]

    lesson = get_lesson(
        lesson_id
    )

    total, present, absent = lesson_stats(
        lesson_id
    )

    percentage = 0

    if total > 0:

        percentage = (
            present
            /
            total
            *
            100
        )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👥 المسجلون",
        total
    )

    c2.metric(
        "✅ الحضور",
        present
    )

    c3.metric(
        "❌ الغياب",
        absent
    )

    c4.metric(
        "📊 نسبة الحضور",
        f"{percentage:.1f}%"
    )

    st.divider()

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"**الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**بدأت:** {lesson['created_at']}"
    )

    st.write(
        f"**انتهت:** {lesson['ended_at'] or '-'}"
    )

    rows = lesson_students(
        lesson_id
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب": row["name"],

                "رقم الهاتف": row["phone"],

                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else
                    "❌ غائب",

                "وقت الحضور":
                    row["marked_at"]
                    or
                    "-"
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# جميع الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 جميع الطلاب المسجلين"
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

            group_name,

            created_at

        FROM students

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
        len(rows)
    )

    table = []

    for row in rows:

        table.append(
            {
                "ID": row["id"],

                "الاسم": row["name"],

                "هاتف الطالب": row["phone"],

                "هاتف ولي الأمر":
                    row["parent_phone"],

                "الصف": row["grade"],

                "المجموعة":
                    row["group_name"],

                "تاريخ التسجيل":
                    row["created_at"]
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
            "لا يوجد طلاب مسجلون."
        )


# =========================================================
# المجموعات
# =========================================================

def groups_page():

    st.subheader(
        "👥 مجموعات الطلاب"
    )

    st.info(
        "كل صف يحتوي على 3 مجموعات، وكل مجموعة حدها الأقصى 70 طالب."
    )

    for grade in GRADES:

        st.markdown(
            f"### 🎓 {grade}"
        )

        c1, c2, c3 = st.columns(3)

        for column, group in zip(
            [c1, c2, c3],
            GROUPS
        ):

            count = group_count(
                grade,
                group
            )

            column.metric(
                group,
                f"{count}/{GROUP_CAPACITY}"
            )


# =========================================================
# ملخص الحضور
# =========================================================

def attendance_summary():

    st.subheader(
        "📈 ملخص الحضور حسب الصف والمجموعة"
    )

    conn = db()

    rows = conn.execute(
        """
        SELECT

            l.grade,

            l.group_name,

            COUNT(
                DISTINCT l.id
            ) AS lessons_count,

            COUNT(a.id)
            AS attendance_count

        FROM lessons l

        LEFT JOIN attendance a

            ON a.lesson_id = l.id

        WHERE l.active = 0

        GROUP BY

            l.grade,

            l.group_name

        ORDER BY

            l.grade,

            l.group_name
        """
    ).fetchall()

    conn.close()

    table = []

    for row in rows:

        table.append(
            {
                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "عدد الحصص المحفوظة":
                    row["lessons_count"],

                "إجمالي تسجيلات الحضور":
                    row["attendance_count"]
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
            "لا توجد بيانات حضور محفوظة."
        )


# =========================================================
# إعدادات المدرس
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    with st.form(
        "change_password"
    ):

        old_password = st.text_input(
            "كلمة المرور الحالية",
            type="password"
        )

        new_password = st.text_input(
            "كلمة المرور الجديدة",
            type="password"
        )

        confirm_password = st.text_input(
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
            old_password,
            stored
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

        elif len(new_password) < 4:

            st.error(
                "❌ كلمة المرور الجديدة قصيرة."
            )

        elif (
            new_password
            !=
            confirm_password
        ):

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

        else:

            set_setting(
                "teacher_password_hash",
                hash_password(
                    new_password
                )
            )

            st.success(
                "✅ تم تغيير كلمة المرور."
            )

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text"
    )

    st.success(
        "📱 ابعت الرابط ده للطلاب. الطالب يسجل بياناته مرة واحدة، وبعدها يستخدم نفس الصفحة لمسح QR كل حصة."
    )


# =========================================================
# لوحة تحكم المدرس
# =========================================================

def teacher_page():

    if not st.session_state.get(
        "teacher_logged_in",
        False
    ):

        teacher_login()

        return

    render_header(
        "👨‍🏫 لوحة تحكم المدرس",
        "إدارة الحصص والحضور"
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = (
            False
        )

        st.rerun()

    # =====================================================
    # رابط الطالب في أعلى الصفحة
    # =====================================================

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text"
    )

    st.info(
        "👨‍🎓 ابعت الرابط ده للطلاب. الطالب هيفتحه ويسجل بياناته أول مرة فقط."
    )

    st.divider()

    # =====================================================
    # Tabs
    # =====================================================

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصص الحالية",
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "👥 المجموعات",
            "📈 ملخص الحضور",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lessons_page()

    with tabs[2]:

        reports_page()

    with tabs[3]:

        students_page()

    with tabs[4]:

        groups_page()

    with tabs[5]:

        attendance_summary()

    with tabs[6]:

        settings_page()


# =========================================================
# تشغيل المنصة
# =========================================================

def main():

    # مهم جدًا:
    # تحديث قاعدة البيانات قبل أي صفحة
    init_db()

    # =====================================================
    # الافتراضي = المدرس
    # =====================================================

    page = st.query_params.get(
        "page",
        "teacher"
    )

    if page == "student":

        student_page()

    else:

        teacher_page()


# =========================================================
# Start
# =========================================================

if __name__ == "__main__":

    main()
