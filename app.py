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

DB_FILE = "teacher_attendance_v3.db"

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
        font-size: 24px;
        margin-bottom: 35px;
    }

    .student-card {
        padding: 20px;
        border-radius: 15px;
        background: rgba(30, 35, 50, 0.8);
        margin-bottom: 20px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
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


# =========================================================
# تهيئة قاعدة البيانات
# =========================================================

def init_db():

    conn = get_db()
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
            active INTEGER NOT NULL DEFAULT 0,
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
            ),

            FOREIGN KEY (
                lesson_id
            )
            REFERENCES lessons(id),

            FOREIGN KEY (
                student_id
            )
            REFERENCES students(id)
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
# الإعدادات
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


def set_setting(key, value):

    conn = get_db()

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
        (key, value)
    )

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
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


def find_student_by_phone(phone):

    conn = get_db()

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


def get_all_students():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return rows


def get_grade_students(grade):

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        WHERE grade = ?
        ORDER BY name
        """,
        (grade,)
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# الحصص
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


def get_lesson_by_token(token):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
        """,
        (token,)
    ).fetchone()

    conn.close()

    return row


def end_active_lesson():

    conn = get_db()

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


def create_new_lesson(grade, lesson_name):

    # تأمين إضافي:
    # إغلاق أي حصة قديمة قبل إنشاء الجديدة
    end_active_lesson()

    token = secrets.token_urlsafe(32)

    conn = get_db()

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
        VALUES (?, ?, ?, NULL, 1, ?)
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

def get_lesson_stats(lesson):

    grade = lesson["grade"]
    lesson_id = lesson["id"]

    conn = get_db()

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

        INNER JOIN students s
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


# =========================================================
# حضور الطالب
# =========================================================

def mark_attendance(token, student_id):

    conn = get_db()

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

        return False, "❌ الحصة غير موجودة أو انتهت."

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

    # لازم الطالب يكون في نفس صف الحصة
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست للصف الخاص بك."
        )

    # هل حضر بالفعل؟
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
            "✅ تم تسجيل حضورك بالفعل في هذه الحصة."
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
# الرابط الحالي
# =========================================================

def get_app_url():

    try:

        return st.context.url.split("?")[0]

    except Exception:

        return ""


def teacher_page_url():

    base = get_app_url()

    if base:

        return base + "?page=teacher"

    return "?page=teacher"


def student_page_url():

    base = get_app_url()

    if base:

        return base + "?page=student"

    return "?page=student"


# =========================================================
# العنوان
# =========================================================

def page_header(title, subtitle):

    st.markdown(
        f"""
        <div class="main-title">
            {title}
        </div>

        <div class="sub-title">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# تسجيل الطالب أول مرة
# =========================================================

def student_registration():

    page_header(
        "🎓 منصة الحضور",
        "تسجيل الطالب"
    )

    st.info(
        """
        👨‍🎓 سجل بياناتك مرة واحدة فقط.

        بعد التسجيل لن تحتاج إلى تسجيل بياناتك مرة أخرى.
        في كل حصة ستقوم فقط بمسح QR الخاص بالمدرس.
        """
    )

    with st.form("student_register"):

        name = st.text_input(
            "👤 اسم الطالب"
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "📞 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب في المنصة",
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

        # لو الطالب مسجل بالفعل
        existing = find_student_by_phone(
            phone
        )

        if existing:

            st.session_state.student_id = existing["id"]

            st.query_params["page"] = "student"
            st.query_params["student"] = str(
                existing["id"]
            )

            st.success(
                "✅ الطالب مسجل بالفعل، تم فتح حسابه."
            )

            st.rerun()

        conn = get_db()

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

            student_id = cur.lastrowid

        except sqlite3.IntegrityError:

            conn.close()

            st.error(
                "❌ رقم الهاتف مسجل بالفعل."
            )

            return

        conn.close()

        st.session_state.student_id = student_id

        st.query_params["page"] = "student"
        st.query_params["student"] = str(
            student_id
        )

        st.success(
            "🎉 تم تسجيلك في المنصة بنجاح."
        )

        st.rerun()


# =========================================================
# استرجاع الطالب المسجل
# =========================================================

def student_login():

    st.subheader(
        "🔐 أنت مسجل بالفعل؟"
    )

    st.write(
        "اكتب رقم هاتفك لفتح حسابك."
    )

    with st.form("student_login_form"):

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        login = st.form_submit_button(
            "دخول",
            use_container_width=True
        )

    if login:

        phone = phone.strip()

        student = find_student_by_phone(
            phone
        )

        if student:

            st.session_state.student_id = student["id"]

            st.query_params["page"] = "student"
            st.query_params["student"] = str(
                student["id"]
            )

            st.success(
                "✅ تم فتح حسابك."
            )

            st.rerun()

        else:

            st.error(
                "❌ لا يوجد طالب بهذا الرقم."
            )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    # ---------------------------------------------
    # معرفة الطالب
    # ---------------------------------------------

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

    # ---------------------------------------------
    # لو مش مسجل
    # ---------------------------------------------

    if student_id is None:

        student_registration()

        st.divider()

        student_login()

        return

    # ---------------------------------------------
    # بيانات الطالب
    # ---------------------------------------------

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

    page_header(
        "🎓 منصة الحضور",
        "واجهة الطالب"
    )

    st.success(
        f"👨‍🎓 أهلاً يا {student['name']}"
    )

    st.write(
        f"🎓 **الصف:** {student['grade']}"
    )

    st.write(
        f"🆔 **رقم الطالب:** {student['id']}"
    )

    st.divider()

    # ---------------------------------------------
    # الحصة الحالية
    # ---------------------------------------------

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        st.write(
            "عندما يبدأ المدرس الحصة ستظهر هنا إمكانية تسجيل الحضور."
        )

        return

    # ---------------------------------------------
    # التأكد من الصف
    # ---------------------------------------------

    if lesson["grade"] != student["grade"]:

        st.warning(
            f"""
            ⏳ توجد حصة حالياً للصف:
            {lesson['grade']}

            أنت في:
            {student['grade']}
            """
        )

        return

    # ---------------------------------------------
    # الحصة
    # ---------------------------------------------

    st.success(
        f"📚 الحصة الحالية: {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 الصف: {lesson['grade']}"
    )

    st.write(
        f"🕐 بدأت: {lesson['created_at']}"
    )

    st.divider()

    # ---------------------------------------------
    # فحص هل حضر بالفعل
    # ---------------------------------------------

    conn = get_db()

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
            "لا تحتاج إلى مسح QR مرة أخرى."
        )

        return

    # ---------------------------------------------
    # زر فتح الكاميرا
    # ---------------------------------------------

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        "اضغط الزر أولاً، وبعدها ستظهر الكاميرا لمسح QR."
    )

    if "open_camera" not in st.session_state:

        st.session_state.open_camera = False

    if not st.session_state.open_camera:

        if st.button(
            "📷 فتح الكاميرا وتسجيل الحضور",
            use_container_width=True
        ):

            st.session_state.open_camera = True

            st.rerun()

    else:

        st.warning(
            "📷 وجّه الكاميرا إلى QR الموجود عند المدرس."
        )

        scan = st.camera_input(
            "امسح QR الحضور"
        )

        if scan is not None:

            token = decode_qr(
                scan
            )

            if not token:

                st.error(
                    "❌ لم يتم التعرف على QR. حاول مرة أخرى."
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

                    st.session_state.open_camera = False

                    st.rerun()

                else:

                    st.error(
                        message
                    )

        if st.button(
            "❌ إغلاق الكاميرا",
            use_container_width=True
        ):

            st.session_state.open_camera = False

            st.rerun()


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    page_header(
        "👨‍🏫 منصة الحضور",
        "واجهة المدرس"
    )

    st.info(
        "🔐 هذه الصفحة خاصة بالمدرس فقط."
    )

    password = st.text_input(
        "🔑 كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "🔓 دخول المدرس",
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

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.header(
        "➕ إنشاء حصة جديدة"
    )

    current = get_active_lesson()

    # ---------------------------------------------
    # لو توجد حصة مفتوحة
    # ---------------------------------------------

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

        if st.button(
            "🔴 إنهاء الحصة الحالية وبدء حصة جديدة",
            use_container_width=True
        ):

            end_active_lesson()

            st.success(
                "✅ تم إنهاء الحصة القديمة."
            )

            st.rerun()

        st.info(
            "يمكنك أيضاً الانتقال إلى تبويب «الحصة الحالية» وإنهائها."
        )

        return

    # ---------------------------------------------
    # إنشاء حصة
    # ---------------------------------------------

    grade = st.selectbox(
        "🎓 اختر الصف",
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

        create_new_lesson(
            grade,
            lesson_name
        )

        st.success(
            "🎉 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصة الحالية
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

    # ---------------------------------------------
    # الإحصائيات
    # ---------------------------------------------

    total, present, absent = get_lesson_stats(
        lesson
    )

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 الصف: **{lesson['grade']}**"
    )

    st.write(
        f"🕐 بدأت: **{lesson['created_at']}**"
    )

    st.divider()

    # ---------------------------------------------
    # أرقام الحضور
    # ---------------------------------------------

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "👨‍🎓 إجمالي طلاب الصف",
            total
        )

    with c2:

        st.metric(
            "✅ الحاضرون الآن",
            present
        )

    with c3:

        st.metric(
            "❌ الغائبون حتى الآن",
            absent
        )

    st.divider()

    # ---------------------------------------------
    # QR
    # ---------------------------------------------

    st.subheader(
        "📱 QR الحضور"
    )

    qr_image = qrcode.make(
        lesson["token"]
    )

    buffer = io.BytesIO()

    qr_image.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        caption="الطلاب يمسحون هذا الكود",
        width=350
    )

    st.divider()

    # ---------------------------------------------
    # تحديث
    # ---------------------------------------------

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True
    ):

        st.rerun()

    st.divider()

    # ---------------------------------------------
    # قائمة الطلاب
    # ---------------------------------------------

    st.subheader(
        "📋 حالة طلاب الصف"
    )

    students = get_grade_students(
        lesson["grade"]
    )

    conn = get_db()

    attendance_rows = conn.execute(
        """
        SELECT
            student_id,
            marked_at
        FROM attendance
        WHERE lesson_id = ?
        """,
        (lesson["id"],)
    ).fetchall()

    conn.close()

    attendance_map = {
        row["student_id"]: row["marked_at"]
        for row in attendance_rows
    }

    table = []

    for student in students:

        if student["id"] in attendance_map:

            status = "✅ حاضر"

            marked_at = attendance_map[
                student["id"]
            ]

        else:

            status = "❌ غائب"

            marked_at = "-"

        table.append(
            {
                "الطالب": student["name"],
                "الهاتف": student["phone"],
                "الحالة": status,
                "وقت الحضور": marked_at
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

    st.divider()

    # ---------------------------------------------
    # إنهاء الحصة
    # ---------------------------------------------

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True
    ):

        end_active_lesson()

        st.success(
            "✅ تم إنهاء الحصة."
        )

        st.rerun()


# =========================================================
# الطلاب
# =========================================================

def students_page():

    st.header(
        "👨‍🎓 الطلاب المسجلون"
    )

    students = get_all_students()

    # إجمالي المنصة
    st.metric(
        "👨‍🎓 إجمالي الطلاب في المنصة",
        len(students)
    )

    if not students:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )

        return

    table = []

    for student in students:

        table.append(
            {
                "ID": student["id"],
                "الاسم": student["name"],
                "هاتف الطالب": student["phone"],
                "هاتف ولي الأمر": student["parent_phone"],
                "الصف": student["grade"],
                "تاريخ التسجيل": student["created_at"]
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

    st.header(
        "📋 التقارير"
    )

    conn = get_db()

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
        "اختر حصة",
        [
            lesson["id"]
            for lesson in lessons
        ]
    )

    selected = None

    for lesson in lessons:

        if lesson["id"] == selected_id:

            selected = lesson

            break

    if selected is None:
        return

    total, present, absent = get_lesson_stats(
        selected
    )

    st.subheader(
        f"📚 {selected['lesson_name']}"
    )

    st.write(
        f"🎓 الصف: {selected['grade']}"
    )

    st.write(
        f"🕐 البداية: {selected['created_at']}"
    )

    st.write(
        f"🔴 النهاية: {selected['ended_at'] or 'الحصة ما زالت مفتوحة'}"
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

    students = get_grade_students(
        selected["grade"]
    )

    conn = get_db()

    attendance = conn.execute(
        """
        SELECT
            student_id,
            marked_at
        FROM attendance
        WHERE lesson_id = ?
        """,
        (selected["id"],)
    ).fetchall()

    conn.close()

    attendance_map = {
        row["student_id"]: row["marked_at"]
        for row in attendance
    }

    table = []

    for student in students:

        if student["id"] in attendance_map:

            table.append(
                {
                    "الطالب": student["name"],
                    "الحالة": "✅ حاضر",
                    "وقت الحضور": attendance_map[
                        student["id"]
                    ]
                }
            )

        else:

            table.append(
                {
                    "الطالب": student["name"],
                    "الحالة": "❌ غائب",
                    "وقت الحضور": "-"
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

    st.header(
        "⚙️ إعدادات المدرس"
    )

    st.write(
        "🔐 تغيير كلمة مرور المدرس"
    )

    with st.form("password_form"):

        old_password = st.text_input(
            "كلمة المرور الحالية",
            type="password"
        )

        new_password = st.text_input(
            "كلمة المرور الجديدة",
            type="password"
        )

        confirm_password = st.text_input(
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
            old_password,
            stored
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

            return

        if len(new_password) < 4:

            st.error(
                "❌ كلمة المرور يجب أن تكون 4 أحرف أو أرقام على الأقل."
            )

            return

        if new_password != confirm_password:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

            return

        set_setting(
            "teacher_password_hash",
            hash_password(new_password)
        )

        st.success(
            "✅ تم تغيير كلمة المرور بنجاح."
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

    page_header(
        "👨‍🏫 لوحة تحكم المدرس",
        "إدارة الحصص والحضور"
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

    # ---------------------------------------------
    # رابط المدرس
    # ---------------------------------------------

    st.divider()

    st.subheader(
        "🔗 رابط صفحة المدرس"
    )

    st.code(
        teacher_page_url(),
        language="text"
    )

    st.caption(
        "هذا الرابط خاص بالمدرس فقط."
    )

    # ---------------------------------------------
    # رابط الطالب
    # ---------------------------------------------

    st.subheader(
        "🔗 رابط صفحة الطالب"
    )

    st.code(
        student_page_url(),
        language="text"
    )

    st.caption(
        "هذا الرابط خاص بالطلاب."
    )


# =========================================================
# الصفحة الرئيسية
# =========================================================

def main():

    # تهيئة قاعدة البيانات
    init_db()

    # الصفحة المطلوبة
    page = st.query_params.get(
        "page",
        "student"
    )

    # ---------------------------------------------
    # المدرس
    # ---------------------------------------------

    if page == "teacher":

        teacher_dashboard()

    # ---------------------------------------------
    # الطالب
    # ---------------------------------------------

    else:

        student_page()


# =========================================================
# تشغيل
# =========================================================

if __name__ == "__main__":

    main()
