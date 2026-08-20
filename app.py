import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


# =========================================================
# الإعدادات
# =========================================================

DB_FILE = "attendance_platform_v5.db"
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
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1100px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .big-title {
        font-size: 42px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 5px;
    }

    .subtitle {
        text-align: center;
        font-size: 20px;
        margin-bottom: 30px;
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

            UNIQUE(lesson_id, student_id),

            FOREIGN KEY(lesson_id)
                REFERENCES lessons(id)
                ON DELETE CASCADE,

            FOREIGN KEY(student_id)
                REFERENCES students(id)
                ON DELETE CASCADE
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
        ("teacher_password_hash",),
    ).fetchone()

    if row is None:
        cur.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            """,
            (
                "teacher_password_hash",
                hash_password(DEFAULT_TEACHER_PASSWORD),
            ),
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

    return row["value"] if row else None


def set_setting(key, value):
    conn = db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )

    conn.commit()
    conn.close()


# =========================================================
# الروابط
# =========================================================

def make_url(page):
    try:
        current = st.context.url

        parts = urlsplit(current)

        query = dict(parse_qsl(parts.query))

        query["page"] = page

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query),
                parts.fragment,
            )
        )

    except Exception:
        return f"?page={page}"


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
# الحصة الحالية
# =========================================================

def get_active_lesson():
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
# إنهاء أي حصص قديمة
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
        (now(),),
    )

    conn.commit()
    conn.close()


# =========================================================
# إنشاء حصة
# =========================================================

def start_lesson(grade, lesson_name):
    conn = db()

    # مهم:
    # نقفل أي حصة قديمة أولاً
    conn.execute(
        """
        UPDATE lessons
        SET active = 0,
            ended_at = ?
        WHERE active = 1
        """,
        (now(),),
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
        VALUES (?, ?, ?, NULL, 1, ?)
        """,
        (
            grade,
            lesson_name,
            now(),
            token,
        ),
    )

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id


# =========================================================
# إنهاء حصة محددة
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
            lesson_id,
        ),
    )

    conn.commit()
    conn.close()


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
        LIMIT 1
        """,
        (token,),
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
        (student_id,),
    ).fetchone()

    if student is None:
        conn.close()

        return False, "❌ الطالب غير موجود."

    # الطالب لازم يكون في نفس صف الحصة
    if student["grade"] != lesson["grade"]:
        conn.close()

        return (
            False,
            "❌ هذه الحصة ليست للصف الخاص بك.",
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
            student_id,
        ),
    ).fetchone()

    if existing:
        conn.close()

        return (
            True,
            "✅ تم تسجيل حضورك بالفعل في هذه الحصة.",
        )

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
# إحصائيات الحصة
# =========================================================

def get_lesson_stats(lesson_id, grade):
    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM students
        WHERE grade = ?
        """,
        (grade,),
    ).fetchone()["count"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM attendance a
        JOIN students s
            ON s.id = a.student_id
        WHERE a.lesson_id = ?
        AND s.grade = ?
        """,
        (
            lesson_id,
            grade,
        ),
    ).fetchone()["count"]

    conn.close()

    absent = max(total - present, 0)

    return total, present, absent


# =========================================================
# إجمالي المنصة
# =========================================================

def get_platform_stats():
    conn = db()

    total = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM students
        """
    ).fetchone()["count"]

    conn.close()

    return total


# =========================================================
# طلاب الصف
# =========================================================

def get_grade_students(grade):
    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        WHERE grade = ?
        ORDER BY name
        """,
        (grade,),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# حالة الطلاب في الحصة
# =========================================================

def get_lesson_students(lesson_id, grade):
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
            grade,
        ),
    ).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def make_qr(token):
    qr = qrcode.make(token)

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


def decode_qr(uploaded):
    if uploaded is None:
        return None

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

        value, points, _ = detector.detectAndDecode(
            image
        )

        if value:
            return value.strip()

    except Exception:
        return None

    return None


# =========================================================
# العنوان
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
        unsafe_allow_html=True,
    )


# =========================================================
# صفحة تسجيل الطالب
# =========================================================

def student_register():
    render_header(
        "🎓 منصة الحضور",
        "تسجيل الطالب لأول مرة",
    )

    st.info(
        """
        📝 التسجيل هنا يتم مرة واحدة فقط.

        بعد التسجيل لن تحتاج لكتابة بياناتك مرة أخرى،
        وستستخدم QR لتسجيل الحضور في كل حصة.
        """
    )

    with st.form("student_register_form"):
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
            GRADES,
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submit:
        return

    name = name.strip()
    phone = phone.strip()
    parent_phone = parent_phone.strip()

    if not name or not phone:
        st.error(
            "❌ لازم تكتب اسم الطالب ورقم الهاتف."
        )
        return

    existing = get_student_by_phone(phone)

    if existing:
        st.session_state.student_id = existing["id"]

        st.query_params["page"] = "student"
        st.query_params["student"] = str(existing["id"])

        st.success(
            "✅ الطالب مسجل بالفعل، تم فتح حسابه."
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
                now(),
            ),
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
    st.query_params["student"] = str(student_id)

    st.success(
        "🎉 تم تسجيل الطالب بنجاح."
    )

    st.rerun()


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():
    render_header(
        "🎓 منصة الحضور",
        "واجهة الطالب",
    )

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
                student_id = candidate["id"]

                st.session_state.student_id = (
                    candidate["id"]
                )

        except Exception:
            pass

    # لو مش مسجل
    if student_id is None:
        student_register()
        return

    student = get_student(student_id)

    if student is None:
        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

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

    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = get_active_lesson()

    if lesson is None:
        st.info(
            """
            ⏳ لا توجد حصة مفتوحة حالياً.

            عندما يبدأ المدرس الحصة سيظهر هنا
            زر تسجيل الحضور بالـ QR.
            """
        )

        return

    # الحصة ليست لنفس الصف
    if lesson["grade"] != student["grade"]:
        st.warning(
            f"""
            ⏳ توجد حصة حالياً لطلاب
            **{lesson['grade']}**.

            ليست هناك حصة مفتوحة لصفك الآن.
            """
        )

        return

    # =====================================================
    # الحصة
    # =====================================================

    st.success(
        f"🟢 توجد حصة مفتوحة الآن: {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    st.divider()

    # =====================================================
    # هل الطالب حضر بالفعل؟
    # =====================================================

    conn = db()

    attendance = conn.execute(
        """
        SELECT marked_at
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student["id"],
        ),
    ).fetchone()

    conn.close()

    if attendance:
        st.success(
            f"""
            ✅ أنت مسجل حضور في هذه الحصة.

            🕐 وقت الحضور:
            {attendance['marked_at']}
            """
        )

        st.info(
            "لا تحتاج لمسح QR مرة أخرى."
        )

        return

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.write(
        """
        اضغط على الكاميرا بالأسفل فقط عندما تكون
        مستعدًا لمسح QR الموجود عند المدرس.
        """
    )

    scan_key = st.session_state.get(
        "scan_key",
        0,
    )

    # الكاميرا لا تعمل تلقائياً.
    # الطالب يضغط عليها بنفسه.
    picture = st.camera_input(
        "📷 افتح الكاميرا لمسح QR",
        key=f"student_camera_{scan_key}",
    )

    if picture is None:
        st.caption(
            "💡 اضغط على زر الكاميرا لفتحها."
        )
        return

    token = decode_qr(picture)

    if not token:
        st.error(
            "❌ لم يتم قراءة QR. حاول تصوير الكود بوضوح."
        )
        return

    ok, message = mark_attendance(
        token,
        student["id"],
    )

    if ok:
        st.success(message)

        # إعادة ضبط الكاميرا بعد النجاح
        st.session_state["scan_key"] = (
            scan_key + 1
        )

        st.rerun()

    else:
        st.error(message)


# =========================================================
# تسجيل دخول المدرس
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
    st.header(
        "➕ إنشاء حصة جديدة"
    )

    current = get_active_lesson()

    if current:
        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حالياً.

            📚 الحصة: {current['lesson_name']}

            🎓 الصف: {current['grade']}
            """
        )

        if st.button(
            "🔴 إنهاء الحصة الحالية وبدء حصة جديدة",
            use_container_width=True,
        ):
            end_lesson(current["id"])

            st.success(
                "✅ تم إنهاء الحصة القديمة."
            )

            st.rerun()

        st.info(
            "أو اذهب إلى تبويب «الحصة الحالية» لإدارتها."
        )

        return

    st.success(
        "🟢 لا توجد حصة مفتوحة. يمكنك إنشاء حصة جديدة."
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):
        lesson_name = lesson_name.strip()

        if not lesson_name:
            lesson_name = "الحصة الحالية"

        start_lesson(
            grade,
            lesson_name,
        )

        st.success(
            "🎉 تم بدء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# الحصة الحالية للمدرس
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

    # معلومات
    st.success(
        "🟢 الحصة مفتوحة حالياً"
    )

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

    # =====================================================
    # الإحصائيات
    # =====================================================

    total, present, absent = get_lesson_stats(
        lesson["id"],
        lesson["grade"],
    )

    platform_total = get_platform_stats()

    st.subheader(
        "📊 إحصائيات الحصة"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 طلاب الصف",
        total,
    )

    c2.metric(
        "✅ الحاضرون",
        present,
    )

    c3.metric(
        "❌ الغائبون",
        absent,
    )

    c4.metric(
        "👥 إجمالي المنصة",
        platform_total,
    )

    st.divider()

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📱 QR الحضور"
    )

    st.write(
        "الطلاب يمسحون هذا الكود لتسجيل حضورهم."
    )

    qr_image = make_qr(
        lesson["token"]
    )

    st.image(
        qr_image,
        width=350,
        caption="QR الخاص بهذه الحصة",
    )

    st.divider()

    # =====================================================
    # حالة الطلاب
    # =====================================================

    st.subheader(
        "📋 حالة طلاب الصف"
    )

    rows = get_lesson_students(
        lesson["id"],
        lesson["grade"],
    )

    if rows:
        table = []

        for row in rows:
            if row["marked_at"]:
                status = "✅ حاضر"
                attendance_time = row["marked_at"]
            else:
                status = "❌ غائب"
                attendance_time = "-"

            table.append(
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "الصف": row["grade"],
                    "الحالة": status,
                    "وقت الحضور": attendance_time,
                }
            )

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

    # =====================================================
    # تحديث
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True,
    ):
        st.rerun()

    # =====================================================
    # إنهاء الحصة
    # =====================================================

    if st.button(
        "🔴 إنهاء الحصة",
        use_container_width=True,
    ):
        end_lesson(
            lesson["id"]
        )

        st.success(
            "✅ تم إنهاء الحصة نهائياً."
        )

        st.rerun()


# =========================================================
# الطلاب
# =========================================================

def students_page():
    st.header(
        "👨‍🎓 الطلاب المسجلون"
    )

    platform_total = get_platform_stats()

    st.metric(
        "👥 إجمالي طلاب المنصة",
        platform_total,
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
                "الطالب": row["name"],
                "هاتف الطالب": row["phone"],
                "هاتف ولي الأمر": row["parent_phone"],
                "الصف": row["grade"],
                "تاريخ التسجيل": row["created_at"],
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# التقارير
# =========================================================

def reports_page():
    st.header(
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
            "لا توجد حصص سابقة."
        )
        return

    for lesson in lessons:
        total, present, absent = get_lesson_stats(
            lesson["id"],
            lesson["grade"],
        )

        status = (
            "🟢 مفتوحة"
            if lesson["active"]
            else "🔴 منتهية"
        )

        with st.expander(
            f"{status} | {lesson['lesson_name']} | {lesson['grade']} | {lesson['created_at']}"
        ):
            c1, c2, c3 = st.columns(3)

            c1.metric(
                "إجمالي الطلاب",
                total,
            )

            c2.metric(
                "الحضور",
                present,
            )

            c3.metric(
                "الغياب",
                absent,
            )

            rows = get_lesson_students(
                lesson["id"],
                lesson["grade"],
            )

            table = []

            for row in rows:
                if row["marked_at"]:
                    status_text = "✅ حاضر"
                    time_text = row["marked_at"]
                else:
                    status_text = "❌ غائب"
                    time_text = "-"

                table.append(
                    {
                        "الطالب": row["name"],
                        "الهاتف": row["phone"],
                        "الحالة": status_text,
                        "وقت الحضور": time_text,
                    }
                )

            if table:
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                )


# =========================================================
# إعدادات المدرس
# =========================================================

def settings_page():
    st.header(
        "⚙️ إعدادات المدرس"
    )

    st.subheader(
        "🔐 تغيير كلمة المرور"
    )

    with st.form("change_password"):
        old = st.text_input(
            "كلمة المرور الحالية",
            type="password",
        )

        new = st.text_input(
            "كلمة المرور الجديدة",
            type="password",
        )

        confirm = st.text_input(
            "تأكيد كلمة المرور الجديدة",
            type="password",
        )

        save = st.form_submit_button(
            "حفظ كلمة المرور",
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
                "❌ كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل."
            )

        elif new != confirm:
            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

        else:
            set_setting(
                "teacher_password_hash",
                hash_password(new),
            )

            st.success(
                "✅ تم تغيير كلمة المرور."
            )

    st.divider()

    st.subheader(
        "🔗 روابط المنصة"
    )

    st.write(
        "👨‍🎓 رابط الطالب:"
    )

    st.code(
        make_url("student"),
        language="text",
    )

    st.write(
        "👨‍🏫 رابط المدرس:"
    )

    st.code(
        make_url("teacher"),
        language="text",
    )


# =========================================================
# لوحة المدرس
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

    if st.button(
        "🚪 تسجيل خروج",
    ):
        st.session_state.teacher_logged_in = False
        st.rerun()

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
# التطبيق
# =========================================================

def main():
    init_db()

    page = st.query_params.get(
        "page",
        "student",
    )

    # ---------------------------------------------
    # الطالب
    # ---------------------------------------------

    if page == "student":
        student_page()
        return

    # ---------------------------------------------
    # المدرس
    # ---------------------------------------------

    if page == "teacher":
        teacher_dashboard()
        return

    # ---------------------------------------------
    # أي رابط غلط
    # ---------------------------------------------

    st.query_params["page"] = "student"

    st.rerun()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
