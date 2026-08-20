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
# إعدادات المنصة
# =========================================================

DB_FILE = "attendance_platform_v2.db"

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
    layout="wide"
)


# =========================================================
# CSS
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
        font-size: 24px;
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

    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    return connection


def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =========================================================
# إنشاء قاعدة البيانات
# =========================================================

def init_database():

    conn = db()

    cursor = conn.cursor()

    # -----------------------------------------------------
    # الإعدادات
    # -----------------------------------------------------

    cursor.execute(
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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT,
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # -----------------------------------------------------
    # الحصص
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # قائمة طلاب كل حصة
    #
    # دي أهم إضافة:
    # بنحفظ Snapshot للطلاب لحظة بدء الحصة.
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lesson_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            student_phone TEXT NOT NULL,
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'غائب',
            attendance_time TEXT,
            UNIQUE(lesson_id, student_id)
        )
        """
    )

    # -----------------------------------------------------
    # كلمة مرور المدرس
    # -----------------------------------------------------

    password_row = cursor.execute(
        """
        SELECT value
        FROM settings
        WHERE key = 'teacher_password'
        """
    ).fetchone()

    if password_row is None:

        cursor.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            """,
            (
                "teacher_password",
                hash_password(
                    DEFAULT_TEACHER_PASSWORD
                )
            )
        )

    conn.commit()

    conn.close()


# =========================================================
# تشفير كلمة المرور
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
# الإعدادات
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

    return row["value"] if row else None


def save_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value)
    )

    conn.commit()
    conn.close()


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

    return base_url() + "?page=student"


# =========================================================
# الحصص المفتوحة
# =========================================================

def active_lessons():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return rows


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


# =========================================================
# تسجيل الطالب
# =========================================================

def register_student():

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

        📷 في كل حصة تستخدم QR الخاص بالمدرس لتسجيل الحضور.
        """
    )

    with st.form("student_registration"):

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

        st.error("❌ اكتب اسم الطالب.")
        return

    if not phone:

        st.error("❌ اكتب رقم الهاتف.")
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

            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                now()
            )
        )

        conn.commit()

        student_id = cursor.lastrowid

        st.session_state.student_id = student_id

        st.query_params["page"] = "student"
        st.query_params["student"] = str(student_id)

        st.success(
            "🎉 تم التسجيل بنجاح."
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
# الحصول على الطالب
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
# QR
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
# تسجيل الحضور
# =========================================================

def mark_attendance(
    student_id,
    token
):

    conn = db()

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
                "❌ الطالب غير موجود."
            )

        if student["grade"] != lesson["grade"]:

            return (
                False,
                "❌ هذه الحصة ليست لصفك."
            )

        if student["group_name"] != lesson["group_name"]:

            return (
                False,
                "❌ هذه الحصة ليست لمجموعتك."
            )

        roster = conn.execute(
            """
            SELECT *
            FROM lesson_students
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson["id"],
                student_id
            )
        ).fetchone()

        if roster is None:

            return (
                False,
                "❌ الطالب لم يكن ضمن طلاب هذه الحصة."
            )

        if roster["status"] == "حاضر":

            return (
                True,
                "✅ تم تسجيل حضورك بالفعل."
            )

        attendance_time = now()

        conn.execute(
            """
            UPDATE lesson_students

            SET
                status = 'حاضر',
                attendance_time = ?

            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                attendance_time,
                lesson["id"],
                student_id
            )
        )

        conn.commit()

        return (
            True,
            "🎉 تم تسجيل حضورك بنجاح."
        )

    except Exception:

        conn.rollback()

        return (
            False,
            "❌ حدث خطأ أثناء تسجيل الحضور."
        )

    finally:

        conn.close()


# =========================================================
# واجهة الطالب
# =========================================================

def student_page():

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    if student_id is None and query_student:

        try:

            student_id = int(
                query_student
            )

            st.session_state.student_id = (
                student_id
            )

        except Exception:

            student_id = None

    # -----------------------------------------------------
    # أول مرة
    # -----------------------------------------------------

    if student_id is None:

        register_student()
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

    # -----------------------------------------------------
    # الصفحة
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # الحصص المناسبة للطالب
    # -----------------------------------------------------

    lessons = [
        lesson
        for lesson in active_lessons()
        if lesson["grade"] == student["grade"]
        and lesson["group_name"] == student["group_name"]
    ]

    if not lessons:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة لصفك ومجموعتك حاليًا.

            عندما يبدأ المدرس الحصة ستظهر هنا.
            """
        )

        return

    lesson = lessons[0]

    # -----------------------------------------------------
    # حالة الطالب
    # -----------------------------------------------------

    conn = db()

    roster = conn.execute(
        """
        SELECT *
        FROM lesson_students
        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student["id"]
        )
    ).fetchone()

    conn.close()

    if roster is None:

        st.warning(
            "⚠️ أنت لم تكن مسجلًا ضمن طلاب هذه الحصة."
        )

        return

    if roster["status"] == "حاضر":

        st.success(
            f"""
            ✅ تم تسجيل حضورك بالفعل.

            🕐 وقت الحضور:
            {roster['attendance_time']}
            """
        )

        return

    # -----------------------------------------------------
    # الحصة
    # -----------------------------------------------------

    st.success(
        f"""
        🟢 الحصة مفتوحة الآن

        📚 {lesson['lesson_name']}

        🎓 {lesson['grade']}

        👥 {lesson['group_name']}
        """
    )

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        "اضغط على الكاميرا وصوّر QR الموجود عند المدرس."
    )

    photo = st.camera_input(
        "📷 فتح الكاميرا",
        key=f"camera_{lesson['id']}"
    )

    if photo is None:
        return

    token = decode_qr(photo)

    if not token:

        st.error(
            "❌ لم يتم قراءة QR."
        )

        return

    success, message = mark_attendance(
        student["id"],
        token
    )

    if success:

        st.success(message)

        st.rerun()

    else:

        st.error(message)


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    st.markdown(
        """
        <div class="main-title">
        👨‍🏫 منصة الحضور
        </div>

        <div class="sub-title">
        🔐 واجهة المدرس
        </div>
        """,
        unsafe_allow_html=True
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

        if stored and check_password(
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
# إنشاء الحصة
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

    group_name = st.selectbox(
        "👥 المجموعة",
        GROUPS,
        key="new_lesson_group"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="new_lesson_name"
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

        conn = db()

        # -------------------------------------------------
        # ممنوع حصة ثانية لنفس الصف والمجموعة
        # -------------------------------------------------

        existing = conn.execute(
            """
            SELECT *
            FROM lessons

            WHERE active = 1
            AND grade = ?
            AND group_name = ?

            LIMIT 1
            """,
            (
                grade,
                group_name
            )
        ).fetchone()

        if existing:

            conn.close()

            st.error(
                f"""
                ❌ توجد حصة مفتوحة بالفعل
                لنفس الصف والمجموعة.

                📚 {existing['lesson_name']}
                """
            )

            return

        # -------------------------------------------------
        # إنشاء QR جديد
        # -------------------------------------------------

        token = secrets.token_urlsafe(
            32
        )

        try:

            cursor = conn.execute(
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
                    now(),
                    token
                )
            )

            lesson_id = cursor.lastrowid

            # -------------------------------------------------
            # Snapshot الطلاب
            # -------------------------------------------------

            students = conn.execute(
                """
                SELECT *
                FROM students

                WHERE grade = ?
                AND group_name = ?

                ORDER BY name
                """,
                (
                    grade,
                    group_name
                )
            ).fetchall()

            for student in students:

                conn.execute(
                    """
                    INSERT INTO lesson_students(
                        lesson_id,
                        student_id,
                        student_name,
                        student_phone,
                        grade,
                        group_name,
                        status,
                        attendance_time
                    )

                    VALUES (?, ?, ?, ?, ?, ?, 'غائب', NULL)
                    """,
                    (
                        lesson_id,
                        student["id"],
                        student["name"],
                        student["phone"],
                        student["grade"],
                        student["group_name"]
                    )
                )

            conn.commit()

            conn.close()

            st.success(
                "🎉 تم إنشاء الحصة وحفظ قائمة طلابها."
            )

            st.rerun()

        except sqlite3.IntegrityError:

            conn.rollback()
            conn.close()

            st.error(
                """
                ❌ حدث تعارض في قاعدة البيانات.

                جرّب مرة أخرى.
                """
            )

        except Exception:

            conn.rollback()
            conn.close()

            st.error(
                "❌ حدث خطأ أثناء إنشاء الحصة."
            )


# =========================================================
# إنهاء الحصة
# =========================================================

def finish_lesson(
    lesson_id
):

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (lesson_id,)
    ).fetchone()

    if lesson is None:

        conn.close()
        return False

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

    return True


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_stats(
    lesson_id
):

    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM lesson_students
        WHERE lesson_id = ?
        """,
        (lesson_id,)
    ).fetchone()[0]

    present = conn.execute(
        """
        SELECT COUNT(*)
        FROM lesson_students

        WHERE lesson_id = ?
        AND status = 'حاضر'
        """,
        (lesson_id,)
    ).fetchone()[0]

    absent = total - present

    conn.close()

    return total, present, absent


# =========================================================
# تفاصيل طلاب الحصة
# =========================================================

def lesson_students(
    lesson_id
):

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM lesson_students

        WHERE lesson_id = ?

        ORDER BY student_name
        """,
        (lesson_id,)
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# QR للحصة
# =========================================================

def show_qr(
    token
):

    qr = qrcode.make(
        token
    )

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        width=350
    )


# =========================================================
# الحصة الحالية
# =========================================================

def current_lessons():

    st.subheader(
        "📊 الحصص المفتوحة حاليًا"
    )

    lessons = active_lessons()

    if not lessons:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    for lesson in lessons:

        st.divider()

        st.markdown(
            f"""
            ## 📚 {lesson['lesson_name']}

            🎓 **الصف:** {lesson['grade']}

            👥 **المجموعة:** {lesson['group_name']}

            📅 **التاريخ والوقت:** {lesson['created_at']}
            """
        )

        total, present, absent = lesson_stats(
            lesson["id"]
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "👨‍🎓 الطلاب في الحصة",
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

        st.subheader(
            "📱 QR الحضور"
        )

        show_qr(
            lesson["qr_token"]
        )

        st.caption(
            "الطلاب يصورون هذا الكود من صفحة الطالب."
        )

        st.divider()

        rows = lesson_students(
            lesson["id"]
        )

        if rows:

            table = []

            for row in rows:

                table.append(
                    {
                        "الطالب": row["student_name"],
                        "الهاتف": row["student_phone"],
                        "الحالة": row["status"],
                        "وقت الحضور":
                            row["attendance_time"]
                            or "-"
                    }
                )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True
            )

        if st.button(
            "🔴 إنهاء الحصة وحفظها",
            key=f"finish_{lesson['id']}",
            use_container_width=True
        ):

            finish_lesson(
                lesson["id"]
            )

            st.success(
                """
                ✅ تم إنهاء الحصة.

                📚 تم حفظ الحصة بالكامل:
                الطلاب + الحضور + الغياب + التاريخ + الوقت.
                """
            )

            st.rerun()


# =========================================================
# التقارير
# =========================================================

def reports():

    st.subheader(
        "📋 سجل جميع الحصص"
    )

    conn = db()

    total_platform_students = conn.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    ).fetchone()[0]

    lessons = conn.execute(
        """
        SELECT *
        FROM lessons
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "👨‍🎓 إجمالي طلاب المنصة",
        total_platform_students
    )

    if not lessons:

        st.info(
            "📭 لا توجد حصص محفوظة حتى الآن."
        )

        return

    # -----------------------------------------------------
    # ملخص كل الحصص
    # -----------------------------------------------------

    summary = []

    for lesson in lessons:

        total, present, absent = lesson_stats(
            lesson["id"]
        )

        summary.append(
            {
                "الحصة": lesson["lesson_name"],
                "الصف": lesson["grade"],
                "المجموعة": lesson["group_name"],
                "التاريخ": lesson["created_at"],
                "وقت الانتهاء": lesson["ended_at"] or "-",
                "عدد الطلاب": total,
                "الحضور": present,
                "الغياب": absent,
                "الحالة":
                    "🟢 مفتوحة"
                    if lesson["active"]
                    else "🔴 منتهية"
            }
        )

    st.dataframe(
        summary,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # -----------------------------------------------------
    # اختيار حصة
    # -----------------------------------------------------

    lesson_options = {}

    for lesson in lessons:

        label = (
            f"{lesson['lesson_name']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['created_at']}"
        )

        lesson_options[label] = lesson["id"]

    selected = st.selectbox(
        "📚 اختر حصة لعرض تفاصيلها",
        list(lesson_options.keys())
    )

    lesson_id = lesson_options[selected]

    lesson = get_lesson(
        lesson_id
    )

    total, present, absent = lesson_stats(
        lesson_id
    )

    st.subheader(
        "📖 تفاصيل الحصة"
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
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
        f"📅 **بدأت:** {lesson['created_at']}"
    )

    st.write(
        f"🏁 **انتهت:** {lesson['ended_at'] or 'لم تنتهِ بعد'}"
    )

    rows = lesson_students(
        lesson_id
    )

    st.subheader(
        "👨‍🎓 حالة كل طلاب الحصة"
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب": row["student_name"],
                "الهاتف": row["student_phone"],
                "الحالة": row["status"],
                "وقت الحضور":
                    row["attendance_time"]
                    or "-"
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 جميع الطلاب المسجلين"
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
            "لا يوجد طلاب مسجلون."
        )

        return

    table = []

    for row in rows:

        table.append(
            {
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
# رابط الطالب
# =========================================================

def student_link_page():

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    link = student_url()

    st.success(
        "📱 ابعت الرابط ده للطلاب:"
    )

    st.code(
        link,
        language="text"
    )

    st.info(
        """
        الطالب يفتح الرابط ويسجل بياناته أول مرة فقط.

        بعد ذلك يستخدم نفس الرابط لتسجيل الحضور
        في كل حصة عن طريق QR.
        """
    )


# =========================================================
# إعدادات المدرس
# =========================================================

def settings_page():

    st.subheader(
        "⚙️ إعدادات المدرس"
    )

    with st.form("change_password"):

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

        submit = st.form_submit_button(
            "💾 تغيير كلمة المرور",
            use_container_width=True
        )

    if submit:

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
                "❌ كلمة المرور يجب أن تكون 4 أحرف على الأقل."
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
    # رابط الطالب
    # -----------------------------------------------------

    st.info(
        "📱 رابط الطالب الذي ترسله للطلاب:"
    )

    st.code(
        student_url(),
        language="text"
    )

    st.divider()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصص الحالية",
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "🔗 رابط الطالب",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lessons()

    with tabs[2]:

        reports()

    with tabs[3]:

        students_page()

    with tabs[4]:

        student_link_page()

    with tabs[5]:

        settings_page()


# =========================================================
# MAIN
# =========================================================

def main():

    init_database()

    page = st.query_params.get(
        "page",
        "teacher"
    )

    # -----------------------------------------------------
    # الطالب
    # -----------------------------------------------------

    if page == "student":

        student_page()

    # -----------------------------------------------------
    # المدرس
    # -----------------------------------------------------

    else:

        teacher_dashboard()


# =========================================================
# تشغيل البرنامج
# =========================================================

if __name__ == "__main__":

    main()
