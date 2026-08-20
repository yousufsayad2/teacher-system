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

# أقصى عدد في المجموعة
GROUP_CAPACITY = 70

# الصفوف المطلوبة فقط
GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
]


# =========================================================
# إعداد Streamlit
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1100px;
        padding-top: 1.2rem;
        padding-bottom: 5rem;
    }

    .big-title {
        text-align: center;
        font-size: 42px;
        font-weight: 800;
        margin-bottom: 4px;
    }

    .subtitle {
        text-align: center;
        font-size: 20px;
        margin-bottom: 24px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# الوقت
# =========================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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

        salt, digest = stored.split(":", 1)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            120000,
        ).hex()

        return secrets.compare_digest(actual, digest)

    except Exception:

        return False


# =========================================================
# قاعدة البيانات
# =========================================================

def db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def columns(conn, table):

    return {
        row["name"]
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }


def add_column(conn, table, name, definition):

    if name not in columns(conn, table):

        conn.execute(
            f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'
        )


# =========================================================
# إنشاء / إصلاح قاعدة البيانات
# =========================================================

def init_db():

    conn = db()

    try:

        # -----------------------------------------
        # settings
        # -----------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        # -----------------------------------------
        # الطلاب
        # -----------------------------------------

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

        # -----------------------------------------
        # الحصص
        # -----------------------------------------

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

        # -----------------------------------------
        # الطلاب الموجودين في الحصة
        # -----------------------------------------

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                parent_phone TEXT DEFAULT '',
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                UNIQUE(lesson_id, student_id)
            )
            """
        )

        # -----------------------------------------
        # الحضور
        # -----------------------------------------

        conn.execute(
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

        # =================================================
        # إصلاح قواعد البيانات القديمة
        # =================================================

        student_columns = {
            "name": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "parent_phone": "TEXT DEFAULT ''",
            "grade": "TEXT DEFAULT 'الصف الأول الإعدادي'",
            "group_name": "TEXT DEFAULT 'المجموعة 1'",
            "created_at": "TEXT DEFAULT ''",
        }

        lesson_columns = {
            "grade": "TEXT DEFAULT 'الصف الأول الإعدادي'",
            "group_name": "TEXT DEFAULT 'المجموعة 1'",
            "lesson_name": "TEXT DEFAULT 'الحصة'",
            "created_at": "TEXT DEFAULT ''",
            "ended_at": "TEXT",
            "active": "INTEGER DEFAULT 0",
            "token": "TEXT DEFAULT ''",
        }

        lesson_student_columns = {
            "lesson_id": "INTEGER DEFAULT 0",
            "student_id": "INTEGER DEFAULT 0",
            "name": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "parent_phone": "TEXT DEFAULT ''",
            "grade": "TEXT DEFAULT ''",
            "group_name": "TEXT DEFAULT 'المجموعة 1'",
        }

        attendance_columns = {
            "lesson_id": "INTEGER DEFAULT 0",
            "student_id": "INTEGER DEFAULT 0",
            "marked_at": "TEXT DEFAULT ''",
        }

        for name, definition in student_columns.items():
            add_column(
                conn,
                "students",
                name,
                definition,
            )

        for name, definition in lesson_columns.items():
            add_column(
                conn,
                "lessons",
                name,
                definition,
            )

        for name, definition in lesson_student_columns.items():
            add_column(
                conn,
                "lesson_students",
                name,
                definition,
            )

        for name, definition in attendance_columns.items():
            add_column(
                conn,
                "attendance",
                name,
                definition,
            )

        # =================================================
        # إصلاح أسماء المجموعات
        # =================================================

        conn.execute(
            """
            UPDATE students
            SET group_name = 'المجموعة 1'
            WHERE group_name IS NULL
               OR TRIM(group_name) = ''
            """
        )

        conn.execute(
            """
            UPDATE lessons
            SET group_name = 'المجموعة 1'
            WHERE group_name IS NULL
               OR TRIM(group_name) = ''
            """
        )

        # =================================================
        # توزيع الطلاب 70 طالب لكل مجموعة
        # لكل صف بشكل مستقل
        # =================================================

        for grade in GRADES:

            students = conn.execute(
                """
                SELECT id
                FROM students
                WHERE grade = ?
                ORDER BY id
                """,
                (grade,),
            ).fetchall()

            for index, student in enumerate(students):

                group_number = (
                    index // GROUP_CAPACITY
                ) + 1

                group_name = (
                    f"المجموعة {group_number}"
                )

                conn.execute(
                    """
                    UPDATE students
                    SET group_name = ?
                    WHERE id = ?
                    """,
                    (
                        group_name,
                        student["id"],
                    ),
                )

        # =================================================
        # إصلاح roster للحصص القديمة
        # =================================================

        lessons = conn.execute(
            """
            SELECT id, grade, group_name
            FROM lessons
            """
        ).fetchall()

        for lesson in lessons:

            existing_count = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM lesson_students
                WHERE lesson_id = ?
                """,
                (lesson["id"],),
            ).fetchone()["c"]

            if existing_count > 0:
                continue

            students = conn.execute(
                """
                SELECT
                    id,
                    name,
                    phone,
                    parent_phone,
                    grade,
                    group_name
                FROM students
                WHERE grade = ?
                  AND group_name = ?
                ORDER BY id
                """,
                (
                    lesson["grade"],
                    lesson["group_name"]
                    or "المجموعة 1",
                ),
            ).fetchall()

            for student in students:

                conn.execute(
                    """
                    INSERT OR IGNORE INTO lesson_students
                    (
                        lesson_id,
                        student_id,
                        name,
                        phone,
                        parent_phone,
                        grade,
                        group_name
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lesson["id"],
                        student["id"],
                        student["name"],
                        student["phone"],
                        student["parent_phone"] or "",
                        student["grade"],
                        student["group_name"]
                        or "المجموعة 1",
                    ),
                )

        # =================================================
        # كلمة مرور المدرس
        # =================================================

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
                INSERT INTO settings(key, value)
                VALUES ('teacher_password_hash', ?)
                """,
                (
                    hash_password(
                        DEFAULT_TEACHER_PASSWORD
                    ),
                ),
            )

        conn.commit()

    except sqlite3.Error:

        conn.rollback()
        raise

    finally:

        conn.close()


# =========================================================
# الإعدادات
# =========================================================

def get_setting(key):

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        if row:
            return row["value"]

        return None

    finally:

        conn.close()


def set_setting(key, value):

    conn = db()

    try:

        conn.execute(
            """
            INSERT OR REPLACE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (
                key,
                value,
            ),
        )

        conn.commit()

    finally:

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
                "",
            )
        )

    except Exception:

        return ""


def teacher_url():

    base = base_url()

    if base:
        return f"{base}?page=teacher"

    return "?page=teacher"


def student_url():

    base = base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def student_lesson_url(token):

    base = base_url()

    if base:
        return (
            f"{base}?page=student&lesson={token}"
        )

    return f"?page=student&lesson={token}"


# =========================================================
# بيانات الطلاب
# =========================================================

def get_student(student_id):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()

    finally:

        conn.close()


def find_student(phone):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

    finally:

        conn.close()


# =========================================================
# الحصة الحالية
# =========================================================

def active_lesson():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    finally:

        conn.close()


# =========================================================
# المجموعات
# =========================================================

def groups_for_grade(grade):

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT DISTINCT group_name
            FROM students
            WHERE grade = ?
            ORDER BY group_name
            """,
            (grade,),
        ).fetchall()

        groups = [
            row["group_name"]
            for row in rows
            if row["group_name"]
        ]

        if not groups:
            return ["المجموعة 1"]

        return groups

    finally:

        conn.close()


def group_count(grade, group):

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM students
            WHERE grade = ?
              AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()

        return row["c"]

    finally:

        conn.close()


def assign_group(conn, grade):

    rows = conn.execute(
        """
        SELECT
            group_name,
            COUNT(*) AS c
        FROM students
        WHERE grade = ?
        GROUP BY group_name
        ORDER BY group_name
        """,
        (grade,),
    ).fetchall()

    for row in rows:

        if (row["c"] or 0) < GROUP_CAPACITY:

            return (
                row["group_name"]
                or "المجموعة 1"
            )

    return f"المجموعة {len(rows) + 1}"


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_stats(lesson_id):

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["c"]

        present = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM attendance
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["c"]

        absent = max(
            total - present,
            0,
        )

        return (
            total,
            present,
            absent,
        )

    finally:

        conn.close()


# =========================================================
# تفاصيل الحضور
# =========================================================

def lesson_rows(lesson_id):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT
                ls.student_id AS id,
                ls.name,
                ls.phone,
                ls.parent_phone,
                ls.grade,
                ls.group_name,
                a.marked_at

            FROM lesson_students ls

            LEFT JOIN attendance a
                ON a.lesson_id = ls.lesson_id
               AND a.student_id = ls.student_id

            WHERE ls.lesson_id = ?

            ORDER BY ls.name
            """,
            (lesson_id,),
        ).fetchall()

    finally:

        conn.close()


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
            """,
            (token,),
        ).fetchone()

        if not lesson:

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

        if not student:

            return (
                False,
                "❌ الطالب غير مسجل.",
            )

        # التأكد من الصف والمجموعة
        if (
            student["grade"]
            != lesson["grade"]
            or student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذا QR خاص بصف أو مجموعة مختلفة.",
            )

        # التأكد أن الطالب ضمن كشف الحصة
        roster = conn.execute(
            """
            SELECT 1
            FROM lesson_students
            WHERE lesson_id = ?
              AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if not roster:

            return (
                False,
                "❌ الطالب ليس ضمن طلاب هذه الحصة.",
            )

        # منع تسجيل الحضور مرتين
        existing = conn.execute(
            """
            SELECT 1
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
                "✅ حضورك مسجل بالفعل.",
            )

        # تسجيل الحضور
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

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except sqlite3.Error:

        conn.rollback()

        return (
            False,
            "❌ تعذر حفظ الحضور. حاول مرة أخرى.",
        )

    finally:

        conn.close()


# =========================================================
# قراءة QR
# =========================================================

def decode_qr(uploaded):

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

        value, _, _ = detector.detectAndDecode(
            image
        )

        if value:
            return value.strip()

        return None

    except Exception:

        return None


# =========================================================
# Header
# =========================================================

def header(title, subtitle):

    st.markdown(
        f"""
        <div class="big-title">{title}</div>
        <div class="subtitle">{subtitle}</div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "واجهة الطالب",
    )

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    # محاولة استرجاع الطالب
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

    # =====================================================
    # التسجيل لأول مرة
    # =====================================================

    if student_id is None:

        st.info(
            "👋 أول مرة فقط: سجّل بياناتك. "
            "بعد التسجيل لن تحتاج لإعادة التسجيل."
        )

        with st.form("student_register"):

            name = st.text_input(
                "👨‍🎓 اسم الطالب"
            )

            phone = st.text_input(
                "📱 رقم هاتف الطالب"
            )

            parent = st.text_input(
                "👪 رقم هاتف ولي الأمر"
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
            parent = parent.strip()

            if not name or not phone:

                st.error(
                    "❌ اكتب اسم الطالب ورقم الهاتف."
                )

                return

            conn = db()

            try:

                old = conn.execute(
                    """
                    SELECT *
                    FROM students
                    WHERE phone = ?
                    """,
                    (phone,),
                ).fetchone()

                # الطالب مسجل من قبل
                if old:

                    if old["grade"] != grade:

                        st.error(
                            "❌ رقم الهاتف مسجل لطالب "
                            "في صف مختلف."
                        )

                        return

                    student_id = old["id"]

                    st.session_state.student_id = (
                        student_id
                    )

                    st.query_params["student"] = (
                        str(student_id)
                    )

                    st.success(
                        "✅ الطالب مسجل بالفعل."
                    )

                    st.rerun()

                # تحديد المجموعة تلقائياً
                group = assign_group(
                    conn,
                    grade,
                )

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
                        parent,
                        grade,
                        group,
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
                    f"🎉 تم التسجيل. "
                    f"أنت في {group}."
                )

                st.rerun()

            except sqlite3.IntegrityError:

                conn.rollback()

                st.error(
                    "❌ رقم الهاتف مسجل بالفعل."
                )

            except sqlite3.Error:

                conn.rollback()

                st.error(
                    "❌ حدث خطأ في قاعدة البيانات."
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

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

        return

    st.success(
        f"👨‍🎓 أهلاً {student['name']}"
    )

    st.write(
        f"🎓 {student['grade']} "
        f"— 👥 {student['group_name']}"
    )

    # =====================================================
    # الحصة
    # =====================================================

    token = st.query_params.get(
        "lesson"
    )

    lesson = None

    if token:

        conn = db()

        try:

            lesson = conn.execute(
                """
                SELECT *
                FROM lessons
                WHERE token = ?
                  AND active = 1
                """,
                (token,),
            ).fetchone()

        finally:

            conn.close()

    if lesson is None:

        lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    # التأكد من المجموعة
    if (
        lesson["grade"]
        != student["grade"]
        or lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            "⚠️ لا توجد حصة مفتوحة لمجموعتك حالياً."
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

    try:

        already = conn.execute(
            """
            SELECT 1
            FROM attendance
            WHERE lesson_id = ?
              AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

    finally:

        conn.close()

    if already:

        st.success(
            "✅ تم تسجيل حضورك في هذه الحصة."
        )

        return

    # =====================================================
    # الكاميرا
    # =====================================================

    st.info(
        "📷 امسح QR الموجود عند المدرس للحضور. "
        "كل حصة تحتاج مسح QR جديد."
    )

    scan = st.camera_input(
        "📷 تصوير QR الحضور",
        key=f"camera_{lesson['id']}",
    )

    if scan is not None:

        decoded = decode_qr(
            scan
        )

        if not decoded:

            st.error(
                "❌ لم أستطع قراءة QR. "
                "قرّب الكاميرا من الكود."
            )

            return

        ok, message = mark_attendance(
            decoded,
            student_id,
        )

        if ok:

            st.success(message)

        else:

            st.error(message)

        st.rerun()


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    header(
        "👨‍🏫 منصة الحضور",
        "دخول المدرس",
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password",
    )

    if st.button(
        "👨‍🏫 دخول",
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

    st.caption(
        "كلمة المرور الافتراضية: 1234"
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
        key="lesson_grade",
    )

    groups = groups_for_grade(
        grade
    )

    group = st.selectbox(
        "👥 المجموعة",
        groups,
        key="lesson_group",
    )

    count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 عدد طلاب المجموعة: "
        f"{count}/{GROUP_CAPACITY}"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if count == 0:

            st.error(
                "❌ لا يوجد طلاب في هذه المجموعة."
            )

            return

        token = secrets.token_urlsafe(
            24
        )

        created = now()

        conn = db()

        try:

            # إنهاء أي حصة قديمة مفتوحة
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
                (created,),
            )

            # إنشاء الحصة
            cur = conn.execute(
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
                    group,
                    lesson_name.strip()
                    or "الحصة",
                    created,
                    token,
                ),
            )

            lesson_id = cur.lastrowid

            # حفظ كشف الطلاب وقت بداية الحصة
            students = conn.execute(
                """
                SELECT
                    id,
                    name,
                    phone,
                    parent_phone,
                    grade,
                    group_name
                FROM students
                WHERE grade = ?
                  AND group_name = ?
                ORDER BY id
                """,
                (
                    grade,
                    group,
                ),
            ).fetchall()

            for student in students:

                conn.execute(
                    """
                    INSERT OR IGNORE INTO lesson_students(
                        lesson_id,
                        student_id,
                        name,
                        phone,
                        parent_phone,
                        grade,
                        group_name
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lesson_id,
                        student["id"],
                        student["name"],
                        student["phone"],
                        student["parent_phone"]
                        or "",
                        student["grade"],
                        student["group_name"],
                    ),
                )

            conn.commit()

        except sqlite3.Error as error:

            conn.rollback()

            st.error(
                f"❌ لم يتم إنشاء الحصة: {error}"
            )

            return

        finally:

            conn.close()

        st.success(
            "🟢 تم بدء الحصة وحفظ قائمة الطلاب."
        )

        st.rerun()


# =========================================================
# الحصة الحالية
# =========================================================

def current_lesson():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = active_lesson()

    if not lesson:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    total, present, absent = lesson_stats(
        lesson["id"]
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 طلاب المجموعة",
        total,
    )

    c2.metric(
        "📝 سجل حضور",
        present,
    )

    c3.metric(
        "❌ غائب",
        absent,
    )

    c4.metric(
        "🟢 موجود الآن",
        present,
    )

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

    # =====================================================
    # رابط الطالب للحصة
    # =====================================================

    link = student_lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الطالب لهذه الحصة"
    )

    st.code(
        link,
        language="text",
    )

    st.caption(
        "📱 ابعت الرابط للطلاب. "
        "الطالب المسجل يدخل الرابط ثم يمسح QR المدرس."
    )

    # =====================================================
    # QR
    # =====================================================

    qr = qrcode.make(
        link
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG",
    )

    st.image(
        buffer.getvalue(),
        caption="📷 QR الحضور",
        width=320,
    )

    # =====================================================
    # جدول الطلاب
    # =====================================================

    rows = lesson_rows(
        lesson["id"]
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة":
                    "✅ حضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    if table:

        st.subheader(
            "👨‍🎓 حالة طلاب المجموعة"
        )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    # =====================================================
    # تحديث / إنهاء
    # =====================================================

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "🔄 تحديث الحضور",
            use_container_width=True,
        ):

            st.rerun()

    with col2:

        if st.button(
            "⛔ إنهاء الحصة وحفظها",
            use_container_width=True,
        ):

            conn = db()

            try:

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
                        lesson["id"],
                    ),
                )

                conn.commit()

                st.success(
                    "✅ تم حفظ الحصة بالحضور "
                    "والغياب والتاريخ والوقت."
                )

            except sqlite3.Error:

                conn.rollback()

                st.error(
                    "❌ تعذر حفظ الحصة."
                )

            finally:

                conn.close()

            st.rerun()


# =========================================================
# تقرير حصة
# =========================================================

def lesson_report():

    st.subheader(
        "📋 تقارير الحصص السابقة"
    )

    conn = db()

    try:

        lessons = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 0
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()

    if not lessons:

        st.info(
            "لا توجد حصص محفوظة."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

        options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys()),
    )

    lesson_id = options[
        selected
    ]

    conn = db()

    try:

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE id = ?
            """,
            (lesson_id,),
        ).fetchone()

    finally:

        conn.close()

    total, present, absent = lesson_stats(
        lesson_id
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "إجمالي",
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
        f"🎓 {lesson['grade']}"
    )

    st.write(
        f"👥 {lesson['group_name']}"
    )

    st.write(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 البداية: {lesson['created_at']}"
    )

    st.write(
        f"🕐 النهاية: {lesson['ended_at'] or '-'}"
    )

    rows = lesson_rows(
        lesson_id
    )

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة":
                    "✅ حضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# إحصائيات كل الصفوف والمجموعات
# =========================================================

def overall_reports():

    st.subheader(
        "📊 إحصائيات الصفوف والمجموعات"
    )

    conn = db()

    try:

        placeholders = ",".join(
            "?"
            for _ in GRADES
        )

        groups = conn.execute(
            f"""
            SELECT
                grade,
                group_name,
                COUNT(*) AS total
            FROM students
            WHERE grade IN ({placeholders})
            GROUP BY grade, group_name
            ORDER BY grade, group_name
            """,
            tuple(GRADES),
        ).fetchall()

        lessons = conn.execute(
            f"""
            SELECT
                id,
                grade,
                group_name,
                lesson_name,
                created_at,
                ended_at
            FROM lessons
            WHERE grade IN ({placeholders})
            ORDER BY id DESC
            """,
            tuple(GRADES),
        ).fetchall()

    finally:

        conn.close()

    st.caption(
        "كل مجموعة تصل إلى 70 طالباً، "
        "وكل حصة تُحفظ مستقلة بتاريخها ووقتها."
    )

    if groups:

        group_data = []

        for row in groups:

            group_data.append(
                {
                    "الصف": row["grade"],
                    "المجموعة": row["group_name"],
                    "عدد الطلاب": row["total"],
                    "السعة": GROUP_CAPACITY,
                    "المتبقي":
                        max(
                            GROUP_CAPACITY
                            - row["total"],
                            0,
                        ),
                }
            )

        st.dataframe(
            group_data,
            use_container_width=True,
            hide_index=True,
        )

    # =====================================================
    # كل الحصص
    # =====================================================

    st.subheader(
        "📚 ملخص كل الحصص"
    )

    summary = []

    for lesson in lessons:

        total, present, absent = lesson_stats(
            lesson["id"]
        )

        summary.append(
            {
                "رقم": lesson["id"],
                "الصف": lesson["grade"],
                "المجموعة":
                    lesson["group_name"],
                "الحصة":
                    lesson["lesson_name"],
                "التاريخ والوقت":
                    lesson["created_at"],
                "وقت الانتهاء":
                    lesson["ended_at"]
                    or "-",
                "إجمالي الطلاب":
                    total,
                "حضر":
                    present,
                "غاب":
                    absent,
            }
        )

    if summary:

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا توجد حصص محفوظة."
        )


# =========================================================
# صفحة الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 جميع الطلاب"
    )

    conn = db()

    try:

        placeholders = ",".join(
            "?"
            for _ in GRADES
        )

        rows = conn.execute(
            f"""
            SELECT
                id,
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                created_at
            FROM students
            WHERE grade IN ({placeholders})
            ORDER BY grade, group_name, id
            """,
            tuple(GRADES),
        ).fetchall()

    finally:

        conn.close()

    st.metric(
        "إجمالي الطلاب في المنصة",
        len(rows),
    )

    if rows:

        data = []

        for row in rows:

            data.append(
                {
                    "ID": row["id"],
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"],
                    "ولي الأمر":
                        row["parent_phone"],
                    "الصف": row["grade"],
                    "المجموعة":
                        row["group_name"],
                    "تاريخ التسجيل":
                        row["created_at"],
                }
            )

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون."
        )


# =========================================================
# إعدادات المدرس
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

        elif len(new) < 4:

            st.error(
                "❌ كلمة المرور الجديدة قصيرة."
            )

        elif new != confirm:

            st.error(
                "❌ التأكيد غير مطابق."
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
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher_logged_in"
    ):

        teacher_login()

        return

    header(
        "👨‍🏫 منصة الحضور",
        "لوحة تحكم المدرس",
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = (
            False
        )

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "📋 التقارير",
            "📊 إحصائيات الصفوف",
            "👨‍🎓 الطلاب",
            "⚙️ الإعدادات",
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lesson()

    with tabs[2]:

        lesson_report()

    with tabs[3]:

        overall_reports()

    with tabs[4]:

        students_page()

    with tabs[5]:

        settings_page()

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text",
    )

    st.caption(
        "المنصة تفتح للمدرس افتراضياً. "
        "المدرس يرسل هذا الرابط للطلاب لأول تسجيل فقط."
    )


# =========================================================
# تشغيل المنصة
# =========================================================

def main():

    try:

        init_db()

    except sqlite3.Error as error:

        st.error(
            "❌ تعذر تجهيز قاعدة البيانات."
        )

        st.code(
            str(error)
        )

        st.stop()

    # مهم جداً:
    # المنصة تفتح على المدرس افتراضياً

    page = st.query_params.get(
        "page",
        "teacher",
    )

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
