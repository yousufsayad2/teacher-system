import streamlit as st
import sqlite3
import secrets
import hashlib
from datetime import datetime
from urllib.parse import urlencode

import qrcode
import cv2
import numpy as np
from PIL import Image


# =========================================================
# إعدادات المنصة
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# قاعدة جديدة لمنع مشاكل قواعد البيانات القديمة
DB_FILE = "attendance_platform_v2.db"

# الصفوف المطلوبة
GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

# 3 مجموعات لكل صف
GROUPS = [
    "مجموعة 1",
    "مجموعة 2",
    "مجموعة 3",
]

# أقصى عدد طلاب في المجموعة
GROUP_CAPACITY = 70

# كود المدرس الافتراضي
# غيره من Streamlit Secrets لو حبيت
DEFAULT_TEACHER_PIN = "1234"


# =========================================================
# أدوات عامة
# =========================================================

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_token():
    return secrets.token_urlsafe(24)


def hash_pin(pin):
    return hashlib.sha256(
        pin.encode("utf-8")
    ).hexdigest()


def get_teacher_pin():
    try:
        return st.secrets.get(
            "TEACHER_PIN",
            DEFAULT_TEACHER_PIN
        )
    except Exception:
        return DEFAULT_TEACHER_PIN


def app_base_url():
    """
    محاولة الحصول على رابط التطبيق الحالي تلقائيًا.
    """
    try:
        url = st.context.url

        if url:
            return url.split("?")[0].split("#")[0]

    except Exception:
        pass

    try:
        url = st.secrets.get(
            "APP_URL",
            ""
        )

        if url:
            return url.rstrip("/")

    except Exception:
        pass

    return ""


def student_url():
    base = app_base_url()

    if base:
        return (
            base
            + "?"
            + urlencode({
                "page": "student"
            })
        )

    return ""


# =========================================================
# DATABASE
# =========================================================

def get_conn():
    """
    فتح اتصال SQLite آمن نسبيًا مع timeout.
    """

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


def init_db():
    """
    إنشاء كل الجداول المطلوبة.
    """

    conn = get_conn()

    try:

        try:
            conn.execute(
                "PRAGMA journal_mode=WAL"
            )
        except sqlite3.Error:
            pass

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                parent_phone TEXT NOT NULL,
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_name TEXT NOT NULL,
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS lesson_students (
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,

                PRIMARY KEY (
                    lesson_id,
                    student_id
                ),

                FOREIGN KEY (
                    lesson_id
                )
                REFERENCES lessons(id)
                ON DELETE CASCADE,

                FOREIGN KEY (
                    student_id
                )
                REFERENCES students(id)
                ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attendance (
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                attended_at TEXT NOT NULL,

                status TEXT NOT NULL
                    DEFAULT 'present',

                PRIMARY KEY (
                    lesson_id,
                    student_id
                ),

                FOREIGN KEY (
                    lesson_id
                )
                REFERENCES lessons(id)
                ON DELETE CASCADE,

                FOREIGN KEY (
                    student_id
                )
                REFERENCES students(id)
                ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS
            idx_students_grade_group
            ON students(grade, group_name);

            CREATE INDEX IF NOT EXISTS
            idx_lessons_grade_group
            ON lessons(grade, group_name);

            CREATE INDEX IF NOT EXISTS
            idx_attendance_lesson
            ON attendance(lesson_id);
            """
        )

        # ترقية قاعدة بيانات قديمة لو كان جدول attendance
        # موجودًا بدون status
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(attendance)"
            ).fetchall()
        }

        if "status" not in columns:

            conn.execute(
                """
                ALTER TABLE attendance
                ADD COLUMN status TEXT
                NOT NULL DEFAULT 'present'
                """
            )

        conn.commit()

    finally:
        conn.close()


def write_db(sql, params=()):
    """
    تنفيذ عمليات الكتابة مع إعادة المحاولة.
    """

    last_error = None

    for _ in range(5):

        conn = None

        try:

            conn = get_conn()

            conn.execute(
                "BEGIN IMMEDIATE"
            )

            cur = conn.execute(
                sql,
                params
            )

            conn.commit()

            return cur.lastrowid

        except sqlite3.OperationalError as e:

            last_error = e

            if conn:

                try:
                    conn.rollback()
                except Exception:
                    pass

        finally:

            if conn:
                conn.close()

    raise last_error


def fetch_one(sql, params=()):

    conn = get_conn()

    try:

        return conn.execute(
            sql,
            params
        ).fetchone()

    finally:
        conn.close()


def fetch_all(sql, params=()):

    conn = get_conn()

    try:

        return conn.execute(
            sql,
            params
        ).fetchall()

    finally:
        conn.close()


def fetch_value(sql, params=()):

    row = fetch_one(
        sql,
        params
    )

    if row:
        return row[0]

    return 0


# =========================================================
# جلسة الطالب
# =========================================================

def clear_student_session():

    keys = [
        "student_id",
        "student_name",
        "student_grade",
        "student_group",
    ]

    for key in keys:
        st.session_state.pop(
            key,
            None
        )


def save_student_query(student_id):

    try:

        st.query_params["page"] = "student"

        st.query_params["student_id"] = str(
            student_id
        )

    except Exception:
        pass


def load_student_session(student_id):

    row = fetch_one(
        """
        SELECT
            id,
            name,
            grade,
            group_name
        FROM students
        WHERE id = ?
        """,
        (student_id,),
    )

    if not row:
        return False

    st.session_state.student_id = row["id"]
    st.session_state.student_name = row["name"]
    st.session_state.student_grade = row["grade"]
    st.session_state.student_group = row["group_name"]

    return True


def load_student_from_phone(phone):

    phone = phone.strip()

    row = fetch_one(
        """
        SELECT *
        FROM students
        WHERE phone = ?
        """,
        (phone,),
    )

    if not row:
        return (
            False,
            "لا يوجد طالب مسجل بهذا الرقم."
        )

    load_student_session(
        row["id"]
    )

    save_student_query(
        row["id"]
    )

    return (
        True,
        f"أهلاً يا {row['name']}"
    )


# =========================================================
# الطلاب
# =========================================================

def student_count(
    grade,
    group_name
):

    return int(
        fetch_value(
            """
            SELECT COUNT(*)
            FROM students
            WHERE grade = ?
              AND group_name = ?
            """,
            (
                grade,
                group_name,
            ),
        )
    )


def find_student(phone):

    return fetch_one(
        """
        SELECT *
        FROM students
        WHERE phone = ?
        """,
        (phone.strip(),),
    )


def register_student(
    name,
    phone,
    parent_phone,
    grade,
    group_name
):

    name = name.strip()
    phone = phone.strip()
    parent_phone = parent_phone.strip()

    if not name:
        return False, "اكتب اسم الطالب."

    if not phone:
        return False, "اكتب رقم الطالب."

    if not parent_phone:
        return False, "اكتب رقم ولي الأمر."

    if len(phone) < 8:
        return False, "رقم الهاتف غير صحيح."

    existing = find_student(phone)

    if existing:

        load_student_session(
            existing["id"]
        )

        save_student_query(
            existing["id"]
        )

        return (
            True,
            f"الطالب مسجل بالفعل باسم {existing['name']}."
        )

    count = student_count(
        grade,
        group_name
    )

    if count >= GROUP_CAPACITY:

        return (
            False,
            f"{group_name} وصلت للحد الأقصى "
            f"وهو {GROUP_CAPACITY} طالب."
        )

    try:

        student_id = write_db(
            """
            INSERT INTO students
            (
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
                now_str(),
            ),
        )

        load_student_session(
            student_id
        )

        save_student_query(
            student_id
        )

        return (
            True,
            "تم تسجيل الطالب بنجاح."
        )

    except sqlite3.IntegrityError:

        return (
            False,
            "رقم الهاتف مسجل بالفعل."
        )


# =========================================================
# الحصص
# =========================================================

def active_lesson_for_student(
    grade,
    group_name
):

    return fetch_one(
        """
        SELECT *
        FROM lessons
        WHERE grade = ?
          AND group_name = ?
          AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            grade,
            group_name,
        ),
    )


def get_active_lessons():

    return fetch_all(
        """
        SELECT *
        FROM lessons
        WHERE status = 'active'
        ORDER BY id DESC
        """
    )


def get_active_lesson(
    lesson_id
):

    return fetch_one(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
          AND status = 'active'
        """,
        (lesson_id,),
    )


def create_lesson(
    lesson_name,
    grade,
    group_name,
    scheduled_at
):

    # منع حصتين مفتوحتين لنفس المجموعة
    active = active_lesson_for_student(
        grade,
        group_name
    )

    if active:

        return (
            False,
            "هناك حصة مفتوحة بالفعل "
            f"لهذه المجموعة: {active['lesson_name']}"
        )

    students = fetch_all(
        """
        SELECT id
        FROM students
        WHERE grade = ?
          AND group_name = ?
        ORDER BY id
        """,
        (
            grade,
            group_name,
        ),
    )

    if not students:

        return (
            False,
            "لا يوجد طلاب مسجلون في هذه المجموعة."
        )

    token = make_token()

    conn = None

    try:

        conn = get_conn()

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        cur = conn.execute(
            """
            INSERT INTO lessons
            (
                lesson_name,
                grade,
                group_name,
                scheduled_at,
                started_at,
                token,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                lesson_name.strip()
                or "حصة جديدة",

                grade,
                group_name,
                scheduled_at,
                now_str(),
                token,
            ),
        )

        lesson_id = cur.lastrowid

        # حفظ الطلاب الموجودين في المجموعة
        # لحظة بدء الحصة
        conn.executemany(
            """
            INSERT INTO lesson_students
            (
                lesson_id,
                student_id
            )
            VALUES (?, ?)
            """,
            [
                (
                    lesson_id,
                    row["id"]
                )
                for row in students
            ],
        )

        conn.commit()

        return (
            True,
            lesson_id
        )

    except Exception as e:

        if conn:

            try:
                conn.rollback()
            except Exception:
                pass

        return (
            False,
            str(e)
        )

    finally:

        if conn:
            conn.close()


def lesson_stats(lesson_id):

    total = int(
        fetch_value(
            """
            SELECT COUNT(*)
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        )
    )

    present = int(
        fetch_value(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE lesson_id = ?
              AND status = 'present'
            """,
            (lesson_id,),
        )
    )

    absent = max(
        total - present,
        0
    )

    return (
        total,
        present,
        absent
    )


def lesson_students_status(
    lesson_id
):

    return fetch_all(
        """
        SELECT
            s.id,
            s.name,
            s.phone,
            s.grade,
            s.group_name,

            CASE
                WHEN a.status = 'present'
                    THEN 'حاضر'

                WHEN a.status = 'absent'
                    THEN 'غائب'

                ELSE 'غائب'
            END AS status,

            a.attended_at

        FROM lesson_students ls

        JOIN students s
            ON s.id = ls.student_id

        LEFT JOIN attendance a
            ON a.lesson_id = ls.lesson_id
            AND a.student_id = ls.student_id

        WHERE ls.lesson_id = ?

        ORDER BY s.name
        """,
        (lesson_id,),
    )


def mark_attendance_by_token(
    student_id,
    token
):

    lesson = fetch_one(
        """
        SELECT *
        FROM lessons
        WHERE token = ?
          AND status = 'active'
        """,
        (token,),
    )

    if not lesson:

        return (
            False,
            "QR غير صالح أو الحصة انتهت."
        )

    enrolled = fetch_one(
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
    )

    if not enrolled:

        return (
            False,
            "الطالب غير مسجل في مجموعة هذه الحصة."
        )

    already = fetch_one(
        """
        SELECT *
        FROM attendance
        WHERE lesson_id = ?
          AND student_id = ?
        """,
        (
            lesson["id"],
            student_id,
        ),
    )

    if already:

        if already["status"] == "present":

            return (
                True,
                "الحضور مسجل بالفعل لهذه الحصة."
            )

    try:

        write_db(
            """
            INSERT INTO attendance
            (
                lesson_id,
                student_id,
                attended_at,
                status
            )
            VALUES (?, ?, ?, 'present')
            """,
            (
                lesson["id"],
                student_id,
                now_str(),
            ),
        )

        return (
            True,
            f"تم تسجيل حضورك في {lesson['lesson_name']}."
        )

    except sqlite3.IntegrityError:

        return (
            True,
            "الحضور مسجل بالفعل."
        )

    except sqlite3.Error:

        return (
            False,
            "حدث خطأ أثناء تسجيل الحضور."
        )


def finish_lesson(
    lesson_id
):

    lesson = get_active_lesson(
        lesson_id
    )

    if not lesson:

        return (
            False,
            "الحصة غير موجودة أو منتهية بالفعل."
        )

    conn = None

    try:

        conn = get_conn()

        conn.execute(
            "BEGIN IMMEDIATE"
        )

        # أي طالب لم يسجل حضورًا
        # يتحول إلى غائب عند إنهاء الحصة
        conn.execute(
            """
            INSERT OR IGNORE INTO attendance
            (
                lesson_id,
                student_id,
                attended_at,
                status
            )

            SELECT
                ls.lesson_id,
                ls.student_id,
                ?,
                'absent'

            FROM lesson_students ls

            LEFT JOIN attendance a
                ON a.lesson_id = ls.lesson_id
                AND a.student_id = ls.student_id

            WHERE ls.lesson_id = ?
              AND a.student_id IS NULL
            """,
            (
                now_str(),
                lesson_id,
            ),
        )

        conn.execute(
            """
            UPDATE lessons
            SET
                status = 'ended',
                ended_at = ?
            WHERE id = ?
            """,
            (
                now_str(),
                lesson_id,
            ),
        )

        conn.commit()

        return (
            True,
            "تم إنهاء الحصة وحفظ الحضور والغياب."
        )

    except Exception as e:

        if conn:

            try:
                conn.rollback()
            except Exception:
                pass

        return (
            False,
            str(e)
        )

    finally:

        if conn:
            conn.close()


# =========================================================
# التقارير
# =========================================================

def lesson_history(
    grade=None,
    group_name=None
):

    sql = """
        SELECT
            l.id,
            l.lesson_name,
            l.grade,
            l.group_name,
            l.scheduled_at,
            l.started_at,
            l.ended_at,
            l.status,

            COUNT(
                DISTINCT ls.student_id
            ) AS total_students,

            SUM(
                CASE
                    WHEN a.status = 'present'
                    THEN 1
                    ELSE 0
                END
            ) AS present_students,

            SUM(
                CASE
                    WHEN a.status = 'absent'
                    THEN 1
                    ELSE 0
                END
            ) AS absent_students

        FROM lessons l

        LEFT JOIN lesson_students ls
            ON ls.lesson_id = l.id

        LEFT JOIN attendance a
            ON a.lesson_id = l.id
            AND a.student_id = ls.student_id
    """

    conditions = []
    params = []

    if grade:

        conditions.append(
            "l.grade = ?"
        )

        params.append(
            grade
        )

    if group_name:

        conditions.append(
            "l.group_name = ?"
        )

        params.append(
            group_name
        )

    if conditions:

        sql += (
            " WHERE "
            + " AND ".join(
                conditions
            )
        )

    sql += """
        GROUP BY l.id
        ORDER BY l.id DESC
    """

    return fetch_all(
        sql,
        params
    )


# =========================================================
# QR
# =========================================================

def make_qr(text):

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )

    qr.add_data(text)

    qr.make(
        fit=True
    )

    return qr.make_image(
        fill_color="black",
        back_color="white",
    ).convert("RGB")


def decode_qr(uploaded_file):

    if uploaded_file is None:
        return None

    try:

        image = Image.open(
            uploaded_file
        ).convert("RGB")

        frame = np.array(
            image
        )

        frame = cv2.cvtColor(
            frame,
            cv2.COLOR_RGB2BGR
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(
            frame
        )

        if data:

            return data.strip()

    except Exception:
        return None

    return None


# =========================================================
# HEADER
# =========================================================

def page_header(
    title,
    subtitle
):

    st.markdown(
        f"""
        <div style="
            text-align:center;
            padding:10px 0 25px 0
        ">

            <h1 style="
                font-size:48px;
                margin-bottom:5px
            ">
                🎓 {title}
            </h1>

            <h3>
                {subtitle}
            </h3>

        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# واجهة الطالب
# =========================================================

def student_page():

    page_header(
        "منصة الحضور",
        "👨‍🎓 واجهة الطالب"
    )

    # محاولة استعادة الطالب من الرابط
    if "student_id" not in st.session_state:

        try:

            saved_id = st.query_params.get(
                "student_id"
            )

            if saved_id:

                load_student_session(
                    int(saved_id)
                )

        except Exception:
            pass

    # =====================================================
    # أول دخول للطالب
    # =====================================================

    if "student_id" not in st.session_state:

        st.info(
            "👋 أول مرة فقط: سجل بياناتك. "
            "بعد التسجيل لن تحتاج إلى تسجيل البيانات مرة أخرى. "
            "في كل حصة ستستخدم QR الخاص بالحصة."
        )

        reg_tab, login_tab = st.tabs(
            [
                "📝 تسجيل أول مرة",
                "🔐 دخول طالب مسجل",
            ]
        )

        # -------------------------------
        # التسجيل
        # -------------------------------

        with reg_tab:

            with st.form(
                "student_register"
            ):

                name = st.text_input(
                    "👨‍🎓 اسم الطالب"
                )

                phone = st.text_input(
                    "📱 رقم هاتف الطالب"
                )

                parent_phone = st.text_input(
                    "👪 رقم هاتف ولي الأمر"
                )

                grade = st.selectbox(
                    "🎓 الصف",
                    GRADES
                )

                group_name = st.selectbox(
                    "👥 المجموعة",
                    GROUPS
                )

                submitted = st.form_submit_button(
                    "✅ تسجيل الطالب",
                    use_container_width=True
                )

            if submitted:

                ok, msg = register_student(
                    name,
                    phone,
                    parent_phone,
                    grade,
                    group_name
                )

                if ok:

                    st.success(
                        msg
                    )

                    st.rerun()

                else:

                    st.error(
                        msg
                    )

        # -------------------------------
        # دخول الطالب المسجل
        # -------------------------------

        with login_tab:

            with st.form(
                "student_login"
            ):

                login_phone = st.text_input(
                    "📱 رقم الهاتف المسجل"
                )

                login_btn = st.form_submit_button(
                    "🔐 دخول",
                    use_container_width=True
                )

            if login_btn:

                ok, msg = load_student_from_phone(
                    login_phone
                )

                if ok:

                    st.success(
                        msg
                    )

                    st.rerun()

                else:

                    st.error(
                        msg
                    )

        st.stop()

    # =====================================================
    # بيانات الطالب
    # =====================================================

    student = fetch_one(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (
            st.session_state.student_id,
        ),
    )

    if not student:

        clear_student_session()

        st.rerun()

    st.success(
        f"👨‍🎓 أهلاً يا {student['name']}"
    )

    st.write(
        f"**🎓 الصف:** {student['grade']}"
    )

    st.write(
        f"**👥 المجموعة:** {student['group_name']}"
    )

    st.write(
        f"**🆔 رقم الطالب:** {student['id']}"
    )

    if st.button(
        "🚪 تسجيل الخروج من هذا الجهاز"
    ):

        clear_student_session()

        try:

            st.query_params.clear()

            st.query_params["page"] = "student"

        except Exception:
            pass

        st.rerun()

    st.divider()

    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = active_lesson_for_student(
        student["grade"],
        student["group_name"]
    )

    if not lesson:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        st.write(
            "عندما يبدأ المدرس الحصة "
            "سيظهر هنا تسجيل الحضور."
        )

        st.stop()

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"**🎓 الصف:** {lesson['grade']}"
    )

    st.write(
        f"**👥 المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"**⏰ بدأت:** {lesson['started_at']}"
    )

    # هل حضر بالفعل؟
    attended = fetch_one(
        """
        SELECT *
        FROM attendance
        WHERE lesson_id = ?
          AND student_id = ?
          AND status = 'present'
        """,
        (
            lesson["id"],
            student["id"],
        ),
    )

    if attended:

        st.success(
            "✅ تم تسجيل حضورك في هذه الحصة."
        )

        st.info(
            "لا تحتاج إلى تصوير QR مرة أخرى."
        )

        st.stop()

    # =====================================================
    # الكاميرا
    # =====================================================

    st.warning(
        "📷 اضغط على زر الكاميرا فقط عندما تكون مستعدًا "
        "لتصوير QR الخاص بالمدرس."
    )

    # الكاميرا لا تفتح تلقائيًا.
    camera_photo = st.camera_input(
        "📷 تصوير QR وتسجيل الحضور",
        key=f"camera_{lesson['id']}"
    )

    if camera_photo is not None:

        with st.spinner(
            "🔎 جاري قراءة QR..."
        ):

            decoded = decode_qr(
                camera_photo
            )

        if not decoded:

            st.error(
                "❌ لم أستطع قراءة QR. "
                "قرب الكاميرا من الكود وحاول مرة أخرى."
            )

        elif not decoded.startswith(
            "ATTEND:"
        ):

            st.error(
                "❌ هذا QR ليس خاصًا بمنصة الحضور."
            )

        else:

            parts = decoded.split(
                ":",
                2
            )

            if len(parts) != 3:

                st.error(
                    "❌ QR غير صالح."
                )

            else:

                token = parts[2]

                ok, msg = mark_attendance_by_token(
                    student["id"],
                    token
                )

                if ok:

                    st.success(
                        "🎉 " + msg
                    )

                    st.rerun()

                else:

                    st.error(
                        msg
                    )


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    page_header(
        "منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس"
    )

    st.info(
        "هذه الصفحة خاصة بالمدرس."
    )

    if st.session_state.get(
        "teacher_logged_in"
    ):

        return True

    with st.form(
        "teacher_login"
    ):

        pin = st.text_input(
            "🔐 كود المدرس",
            type="password"
        )

        login = st.form_submit_button(
            "دخول المدرس",
            use_container_width=True
        )

    if login:

        if hash_pin(pin) == hash_pin(
            get_teacher_pin()
        ):

            st.session_state.teacher_logged_in = True

            st.rerun()

        else:

            st.error(
                "❌ كود المدرس غير صحيح."
            )

    return False


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    if not teacher_login():

        st.stop()

    st.success(
        "👨‍🏫 تم الدخول إلى لوحة المدرس."
    )

    if st.button(
        "🚪 تسجيل خروج المدرس"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    # =====================================================
    # رابط الطالب
    # =====================================================

    st.divider()

    st.header(
        "🔗 رابط تسجيل الطلاب"
    )

    url = student_url()

    if url:

        st.text_input(
            "📱 ابعت الرابط ده للطلاب",
            value=url
        )

        st.link_button(
            "📱 فتح صفحة الطالب",
            url,
            use_container_width=True
        )

        st.success(
            "الطالب يدخل من الرابط ده ويسجل بياناته أول مرة."
        )

    else:

        st.warning(
            "لم أستطع تحديد رابط التطبيق تلقائيًا."
        )

        st.info(
            "لو الرابط لم يظهر، ضع APP_URL في Streamlit Secrets."
        )

    st.divider()

    # =====================================================
    # التبويبات
    # =====================================================

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "📋 التقارير",
        ]
    )

    # =====================================================
    # إنشاء حصة
    # =====================================================

    with tabs[0]:

        st.header(
            "➕ إنشاء حصة جديدة"
        )

        active = get_active_lessons()

        if active:

            st.warning(
                f"يوجد حاليًا {len(active)} حصة مفتوحة."
            )

        with st.form(
            "create_lesson_form"
        ):

            lesson_name = st.text_input(
                "📚 اسم الحصة",
                value="الحصة الحالية"
            )

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

            scheduled_date = st.date_input(
                "📅 تاريخ الحصة",
                value=datetime.now().date()
            )

            scheduled_time = st.time_input(
                "⏰ وقت الحصة",
                value=datetime.now().time().replace(
                    second=0,
                    microsecond=0
                )
            )

            current_count = student_count(
                grade,
                group_name
            )

            st.info(
                f"👨‍🎓 عدد الطلاب المسجلين: "
                f"{current_count} / {GROUP_CAPACITY}"
            )

            create = st.form_submit_button(
                "🟢 بدء الحصة",
                use_container_width=True
            )

        if create:

            scheduled_at = (
                scheduled_date.strftime(
                    "%Y-%m-%d"
                )
                + " "
                + scheduled_time.strftime(
                    "%H:%M:%S"
                )
            )

            ok, result = create_lesson(
                lesson_name,
                grade,
                group_name,
                scheduled_at
            )

            if ok:

                st.success(
                    "✅ بدأت الحصة وتم حفظ قائمة الطلاب."
                )

                st.session_state.selected_lesson_id = result

                st.rerun()

            else:

                st.error(
                    "❌ " + str(result)
                )

    # =====================================================
    # الحصة الحالية
    # =====================================================

    with tabs[1]:

        st.header(
            "📊 الحصة الحالية"
        )

        active_lessons = get_active_lessons()

        if not active_lessons:

            st.info(
                "لا توجد حصص مفتوحة حاليًا."
            )

        else:

            options = {
                f"{row['lesson_name']} — "
                f"{row['grade']} — "
                f"{row['group_name']}":
                row["id"]

                for row in active_lessons
            }

            labels = list(
                options.keys()
            )

            default_index = 0

            if "selected_lesson_id" in st.session_state:

                for i, label in enumerate(
                    labels
                ):

                    if options[label] == st.session_state.selected_lesson_id:

                        default_index = i

                        break

            selected_label = st.selectbox(
                "اختر الحصة",
                labels,
                index=default_index
            )

            lesson_id = options[
                selected_label
            ]

            st.session_state.selected_lesson_id = lesson_id

            lesson = get_active_lesson(
                lesson_id
            )

            if lesson:

                total, present, absent = lesson_stats(
                    lesson_id
                )

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "👨‍🎓 المسجلين",
                    total
                )

                c2.metric(
                    "✅ الحاضرون الآن",
                    present
                )

                c3.metric(
                    "❌ الغائبون الآن",
                    absent
                )

                c4.metric(
                    "👥 المجموعة",
                    lesson["group_name"]
                )

                st.write(
                    f"**📚 الحصة:** {lesson['lesson_name']}"
                )

                st.write(
                    f"**🎓 الصف:** {lesson['grade']}"
                )

                st.write(
                    f"**📅 الموعد:** {lesson['scheduled_at']}"
                )

                st.write(
                    f"**⏰ بدأت:** {lesson['started_at']}"
                )

                # =================================================
                # QR
                # =================================================

                qr_text = (
                    f"ATTEND:"
                    f"{lesson['id']}:"
                    f"{lesson['token']}"
                )

                qr_image = make_qr(
                    qr_text
                )

                st.subheader(
                    "📷 QR تسجيل الحضور"
                )

                st.image(
                    qr_image,
                    caption="الطلاب يصورون هذا الكود من صفحة الطالب",
                    width=350
                )

                st.caption(
                    "كل حصة لها QR مختلف."
                )

                if st.button(
                    "🔄 تحديث الحضور",
                    use_container_width=True,
                    key=f"refresh_{lesson_id}"
                ):

                    st.rerun()

                # =================================================
                # جدول الطلاب
                # =================================================

                st.subheader(
                    "📋 حالة طلاب الحصة"
                )

                rows = lesson_students_status(
                    lesson_id
                )

                display_rows = []

                for row in rows:

                    display_rows.append(
                        {
                            "الطالب": row["name"],
                            "الهاتف": row["phone"],
                            "الحالة":
                                "✅ حاضر"
                                if row["status"] == "حاضر"
                                else "❌ غائب",
                            "وقت الحضور":
                                row["attended_at"]
                                if row["attended_at"]
                                else "-",
                        }
                    )

                st.dataframe(
                    display_rows,
                    use_container_width=True,
                    hide_index=True
                )

                st.warning(
                    "عند إنهاء الحصة سيتم تثبيت كل طالب "
                    "لم يسجل حضورًا كغائب، وحفظ الحصة بالكامل."
                )

                if st.button(
                    "🔴 إنهاء الحصة وحفظ الحضور والغياب",
                    use_container_width=True,
                    key=f"finish_{lesson_id}"
                ):

                    ok, msg = finish_lesson(
                        lesson_id
                    )

                    if ok:

                        st.success(
                            msg
                        )

                        st.session_state.pop(
                            "selected_lesson_id",
                            None
                        )

                        st.rerun()

                    else:

                        st.error(
                            msg
                        )

    # =====================================================
    # الطلاب
    # =====================================================

    with tabs[2]:

        st.header(
            "👨‍🎓 الطلاب المسجلون"
        )

        total_students = int(
            fetch_value(
                "SELECT COUNT(*) FROM students"
            )
        )

        st.metric(
            "👨‍🎓 إجمالي طلاب المنصة",
            total_students
        )

        for grade in GRADES:

            with st.expander(
                f"🎓 {grade}"
            ):

                grade_total = int(
                    fetch_value(
                        """
                        SELECT COUNT(*)
                        FROM students
                        WHERE grade = ?
                        """,
                        (grade,)
                    )
                )

                st.write(
                    f"**إجمالي الصف:** {grade_total}"
                )

                cols = st.columns(3)

                for i, group_name in enumerate(
                    GROUPS
                ):

                    count = student_count(
                        grade,
                        group_name
                    )

                    cols[i].metric(
                        group_name,
                        f"{count}/{GROUP_CAPACITY}"
                    )

                rows = fetch_all(
                    """
                    SELECT
                        name AS "الطالب",
                        phone AS "الهاتف",
                        parent_phone AS "ولي الأمر",
                        group_name AS "المجموعة",
                        created_at AS "تاريخ التسجيل"

                    FROM students

                    WHERE grade = ?

                    ORDER BY
                        group_name,
                        name
                    """,
                    (grade,)
                )

                if rows:

                    st.dataframe(
                        [
                            dict(row)
                            for row in rows
                        ],
                        use_container_width=True,
                        hide_index=True
                    )

                else:

                    st.info(
                        "لا يوجد طلاب في هذا الصف."
                    )

    # =====================================================
    # التقارير
    # =====================================================

    with tabs[3]:

        st.header(
            "📋 تقارير الحصص المحفوظة"
        )

        f1, f2 = st.columns(2)

        filter_grade = f1.selectbox(
            "🎓 الصف",
            ["كل الصفوف"] + GRADES,
            key="report_grade"
        )

        filter_group = f2.selectbox(
            "👥 المجموعة",
            ["كل المجموعات"] + GROUPS,
            key="report_group"
        )

        grade_value = (
            None
            if filter_grade == "كل الصفوف"
            else filter_grade
        )

        group_value = (
            None
            if filter_group == "كل المجموعات"
            else filter_group
        )

        history = lesson_history(
            grade=grade_value,
            group_name=group_value
        )

        if not history:

            st.info(
                "لا توجد حصص محفوظة حتى الآن."
            )

        else:

            report_rows = []

            for row in history:

                total = row["total_students"] or 0
                present = row["present_students"] or 0
                absent = row["absent_students"] or 0

                report_rows.append(
                    {
                        "الحصة":
                            row["lesson_name"],

                        "الصف":
                            row["grade"],

                        "المجموعة":
                            row["group_name"],

                        "الموعد":
                            row["scheduled_at"],

                        "بدأت":
                            row["started_at"],

                        "انتهت":
                            row["ended_at"] or "-",

                        "إجمالي الطلاب":
                            total,

                        "حضر":
                            present,

                        "غاب":
                            absent,

                        "الحالة":
                            "مغلقة"
                            if row["status"] == "ended"
                            else "مفتوحة",
                    }
                )

            st.dataframe(
                report_rows,
                use_container_width=True,
                hide_index=True
            )

            st.divider()

            st.subheader(
                "📊 عدد الحصص حسب الصف والمجموعة"
            )

            summary = fetch_all(
                """
                SELECT
                    grade,
                    group_name,
                    COUNT(*) AS lessons_count

                FROM lessons

                GROUP BY
                    grade,
                    group_name

                ORDER BY
                    grade,
                    group_name
                """
            )

            if summary:

                st.dataframe(
                    [
                        dict(row)
                        for row in summary
                    ],
                    use_container_width=True,
                    hide_index=True
                )

            st.caption(
                "كل حصة محفوظة بالتاريخ والوقت والصف "
                "والمجموعة وعدد الحضور والغياب."
            )


# =========================================================
# تشغيل التطبيق
# =========================================================

def main():

    # إنشاء قاعدة البيانات والجداول
    # قبل تشغيل أي صفحة
    init_db()

    # التطبيق يفتح على المدرس افتراضيًا
    try:

        page = st.query_params.get(
            "page",
            "teacher"
        )

    except Exception:

        page = "teacher"

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


if __name__ == "__main__":

    main()
