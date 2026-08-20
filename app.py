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

DB_FILE = "teacher_system_final.db"

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
    page_title="نظام حضور الطلاب",
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
# أدوات قاعدة البيانات
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# =========================================================
# تشفير كلمة المرور
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
            active INTEGER NOT NULL DEFAULT 1,
            token TEXT NOT NULL UNIQUE,
            ended_at TEXT
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
            (key, value)
            VALUES (?, ?)
            """,
            (
                "teacher_password_hash",
                hash_password(
                    DEFAULT_TEACHER_PASSWORD
                )
            )
        )

    # -----------------------------------------------------
    # التأكد من وجود ended_at
    # لو قاعدة البيانات اتعملت من نسخة أقدم
    # -----------------------------------------------------

    columns = cur.execute(
        """
        PRAGMA table_info(lessons)
        """
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "ended_at" not in column_names:

        cur.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN ended_at TEXT
            """
        )

    conn.commit()
    conn.close()


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

    if row:
        return row["value"]

    return None


def set_setting(key, value):

    conn = db()

    conn.execute(
        """
        INSERT INTO settings
        (key, value)

        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
        value = excluded.value
        """,
        (key, value)
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
# إغلاق كل الحصص المفتوحة القديمة
# =========================================================

def close_all_active_lessons():

    conn = db()

    conn.execute(
        """
        UPDATE lessons
        SET active = 0,
            ended_at = ?
        WHERE active = 1
        """,
        (now(),)
    )

    conn.commit()
    conn.close()


# =========================================================
# إنهاء حصة
# =========================================================

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
# إنشاء حصة
# =========================================================

def create_new_lesson(grade, lesson_name):

    # أول حاجة نقفل أي حصة قديمة
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
            token,
            ended_at
        )

        VALUES (?, ?, ?, 1, ?, NULL)
        """,
        (
            grade,
            lesson_name,
            now(),
            token
        )
    )

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id


# =========================================================
# إحصائيات الحصة
# =========================================================

def lesson_stats(lesson_id, grade):

    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM students
        WHERE grade = ?
        """,
        (grade,)
    ).fetchone()["count"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM attendance a

        INNER JOIN students s
        ON s.id = a.student_id

        WHERE a.lesson_id = ?
        AND s.grade = ?
        """,
        (
            lesson_id,
            grade
        )
    ).fetchone()["count"]

    conn.close()

    absent = max(total - present, 0)

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

        return False, "❌ الحصة غير مفتوحة أو QR غير صالح."

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

        return False, "❌ الطالب غير مسجل."

    # -----------------------------------------------------
    # التأكد أن الطالب في نفس الصف
    # -----------------------------------------------------

    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذا الـ QR خاص بصف مختلف."
        )

    # -----------------------------------------------------
    # هل سجل حضور قبل كده؟
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # تسجيل الحضور
    # -----------------------------------------------------

    try:

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

    except sqlite3.IntegrityError:

        conn.close()

        return (
            True,
            "✅ حضورك مسجل بالفعل."
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

        base = st.context.url.split("?")[0]

        return (
            base
            + "?page=teacher"
        )

    except Exception:

        return "?page=teacher"


# =========================================================
# رابط الطالب
# =========================================================

def student_url():

    try:

        base = st.context.url.split("?")[0]

        return base

    except Exception:

        return "الرابط الحالي"


# =========================================================
# Header
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
# صفحة الطالب
# =========================================================

def student_page():

    render_header(
        "🎓 نظام حضور الطلاب",
        "صفحة الطالب"
    )

    # -----------------------------------------------------
    # استرجاع الطالب
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

                st.session_state.student_id = (
                    candidate["id"]
                )

                student_id = candidate["id"]

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
            "student_register_form"
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

            conn = db()

            # -------------------------------------------------
            # لو الطالب مسجل قبل كده
            # -------------------------------------------------

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

                # نستخدم نفس الحساب
                st.session_state.student_id = (
                    existing["id"]
                )

                st.query_params["student"] = (
                    str(existing["id"])
                )

                st.success(
                    "✅ الطالب مسجل بالفعل، تم الدخول للحساب."
                )

                st.rerun()

            # -------------------------------------------------
            # تسجيل جديد
            # -------------------------------------------------

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

                conn.close()

                st.session_state.student_id = (
                    new_id
                )

                st.query_params["student"] = (
                    str(new_id)
                )

                st.success(
                    "🎉 تم تسجيل الطالب بنجاح."
                )

                st.rerun()

            except Exception as e:

                conn.close()

                st.error(
                    f"❌ حدث خطأ أثناء التسجيل: {e}"
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
        f"🎓 الصف: **{student['grade']}**"
    )

    st.write(
        f"📱 الهاتف: **{student['phone']}**"
    )

    st.divider()

    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = active_lesson()

    if lesson is None:

        st.warning(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        st.info(
            "عندما يبدأ المدرس الحصة سيظهر لك زر تسجيل الحضور هنا."
        )

        return

    # -----------------------------------------------------
    # الحصة ليست لصف الطالب
    # -----------------------------------------------------

    if lesson["grade"] != student["grade"]:

        st.warning(
            "⏳ توجد حصة حالياً، لكنها ليست لصفك."
        )

        return

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
        f"**وقت البداية:** {lesson['created_at']}"
    )

    st.divider()

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
            student_id
        )
    ).fetchone()

    conn.close()

    if attendance:

        st.success(
            f"""
            🎉 تم تسجيل حضورك.

            🕐 وقت الحضور:
            {attendance['marked_at']}
            """
        )

        st.info(
            "لا تحتاج إلى مسح QR مرة أخرى."
        )

        return

    # =====================================================
    # زر فتح الكاميرا
    # =====================================================

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        """
        اضغط على الزر لفتح الكاميرا،
        ثم صوّر QR الموجود عند المدرس.
        """
    )

    open_camera = st.button(
        "📷 فتح كاميرا QR",
        use_container_width=True
    )

    if open_camera:

        st.session_state.camera_open = True

    # =====================================================
    # الكاميرا لا تظهر إلا بعد الضغط
    # =====================================================

    if st.session_state.get(
        "camera_open",
        False
    ):

        scan = st.camera_input(
            "📷 صوّر QR الحضور"
        )

        if scan is not None:

            token = decode_qr(
                scan
            )

            if not token:

                st.error(
                    "❌ لم يتم قراءة QR. حاول تصوير الكود بوضوح."
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

                    # قفل الكاميرا بعد التسجيل
                    st.session_state.camera_open = False

                    st.rerun()

                else:

                    st.error(
                        message
                    )


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 صفحة المدرس",
        "دخول آمن للمدرس"
    )

    st.info(
        "🔐 كلمة المرور الافتراضية: 1234"
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

    # -----------------------------------------------------
    # لو في حصة مفتوحة
    # -----------------------------------------------------

    if current is not None:

        st.warning(
            "⚠️ توجد حصة مفتوحة بالفعل."
        )

        st.write(
            f"📚 الحصة: **{current['lesson_name']}**"
        )

        st.write(
            f"🎓 الصف: **{current['grade']}**"
        )

        # زر إغلاق احتياطي
        if st.button(
            "⛔ إغلاق الحصة الحالية وبدء حصة جديدة",
            use_container_width=True
        ):

            end_lesson(
                current["id"]
            )

            st.success(
                "✅ تم إغلاق الحصة القديمة."
            )

            st.rerun()

        return

    # -----------------------------------------------------
    # اختيار الصف
    # -----------------------------------------------------

    grade = st.selectbox(
        "الصف",
        GRADES
    )

    lesson_name = st.text_input(
        "اسم الحصة",
        value=""
    )

    if not lesson_name.strip():

        lesson_name = "الحصة الحالية"

    # -----------------------------------------------------
    # بدء الحصة
    # -----------------------------------------------------

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True
    ):

        try:

            lesson_id = create_new_lesson(
                grade,
                lesson_name.strip()
            )

            st.session_state.current_lesson_id = (
                lesson_id
            )

            st.success(
                "🎉 تم بدء الحصة بنجاح."
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"❌ حدث خطأ: {e}"
            )


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
    # معلومات الحصة
    # -----------------------------------------------------

    st.markdown(
        f"""
        ## 📚 {lesson['lesson_name']}

        🎓 **الصف:** {lesson['grade']}

        🕐 **بدأت:** {lesson['created_at']}
        """
    )

    st.divider()

    # =====================================================
    # الإحصائيات
    # =====================================================

    total, present, absent = lesson_stats(
        lesson["id"],
        lesson["grade"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
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
        caption="الطلاب يصورون هذا الكود",
        width=350
    )

    st.divider()

    # =====================================================
    # تحديث الحضور
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True
    ):

        st.rerun()

    # =====================================================
    # حالة الطلاب
    # =====================================================

    st.subheader(
        "📋 حالة الطلاب"
    )

    conn = db()

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
        ON a.student_id = s.id
        AND a.lesson_id = ?

        WHERE s.grade = ?

        ORDER BY s.name COLLATE NOCASE
        """,
        (
            lesson["id"],
            lesson["grade"]
        )
    ).fetchall()

    conn.close()

    if rows:

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
                    "الهاتف": row["phone"],
                    "الحالة": status,
                    "وقت الحضور": attendance_time
                }
            )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    st.divider()

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

        st.session_state.current_lesson_id = None

        st.success(
            "✅ تم إنهاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
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

    table = []

    for row in rows:

        table.append(
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
        table,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
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
            "لا توجد حصص حتى الآن."
        )

        return

    selected_id = st.selectbox(
        "اختر الحصة",
        options=[
            lesson["id"]
            for lesson in lessons
        ],
        format_func=lambda lesson_id: (
            next(
                (
                    f"{lesson['lesson_name']} - "
                    f"{lesson['grade']} - "
                    f"{lesson['created_at']}"
                    for lesson in lessons
                    if lesson["id"] == lesson_id
                ),
                str(lesson_id)
            )
        )
    )

    selected = next(
        lesson
        for lesson in lessons
        if lesson["id"] == selected_id
    )

    total, present, absent = lesson_stats(
        selected["id"],
        selected["grade"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "إجمالي الطلاب",
        total
    )

    c2.metric(
        "الحاضرون",
        present
    )

    c3.metric(
        "الغائبون",
        absent
    )

    conn = db()

    rows = conn.execute(
        """
        SELECT
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
            selected["id"],
            selected["grade"]
        )
    ).fetchall()

    conn.close()

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time = row["marked_at"]

        else:

            status = "❌ غائب"

            time = "-"

        table.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة": status,
                "وقت الحضور": time
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True
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

        change = st.form_submit_button(
            "🔐 تغيير كلمة المرور",
            use_container_width=True
        )

    if change:

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
                "❌ كلمة المرور الجديدة يجب أن تكون 4 أحرف أو أرقام على الأقل."
            )

        elif new_password != confirm_password:

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

    # -----------------------------------------------------
    # العنوان
    # -----------------------------------------------------

    st.markdown(
        """
        <div class="big-title">
            👨‍🏫 لوحة تحكم المدرس
        </div>
        """,
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # تسجيل خروج
    # -----------------------------------------------------

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    st.divider()

    # =====================================================
    # التبويبات
    # =====================================================

    tabs = st.tabs(
        [
            "📋 التقارير",
            "👨‍🎓 الطلاب",
            "📊 الحصة الحالية",
            "➕ إنشاء حصة",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        reports_page()

    with tabs[1]:

        students_page()

    with tabs[2]:

        current_lesson_page()

    with tabs[3]:

        create_lesson_page()

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
        "هذا الرابط خاص بالمدرس ويتطلب كلمة المرور."
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # إنشاء قاعدة البيانات
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
# تشغيل
# =========================================================

if __name__ == "__main__":
    main()
