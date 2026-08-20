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
# إعدادات
# =========================================================

DB_FILE = "teacher_system_v2.db"
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
        check_same_thread=False
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
        password.encode(),
        salt,
        120000
    )

    return (
        salt.hex()
        + ":"
        + digest.hex()
    )


def verify_password(password, stored):

    try:

        salt_hex, digest_hex = stored.split(":")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
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
        INSERT INTO settings(key, value)
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


# =========================================================
# إحصائيات الحضور
# =========================================================

def lesson_stats(lesson_id, grade):

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

    absent = total - present

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

        return (
            False,
            "❌ الكود غير صالح أو الحصة انتهت."
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

    # التأكد أن الطالب في نفس الصف
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ الطالب ليس في صف هذه الحصة."
        )

    # هل سجل قبل كده؟
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
            "✅ تم تسجيل حضورك بالفعل."
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

def decode_qr(uploaded):

    if uploaded is None:
        return None

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

    return None


# =========================================================
# رابط المدرس
# =========================================================

def teacher_url():

    try:

        return (
            st.context.url
            + "?page=teacher"
        )

    except Exception:

        return "?page=teacher"


# =========================================================
# عنوان الصفحة
# =========================================================

def render_header(title, subtitle):

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

    st.info(
        """
        📝 سجل الطالب أول مرة فقط.

        📷 بعد كده في كل حصة:
        افتح صفحة الطالب وامسح QR الخاص بالمدرس.
        """
    )

    # -----------------------------------------------------
    # معرفة الطالب
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

        except ValueError:

            pass

    # -----------------------------------------------------
    # التسجيل لأول مرة
    # -----------------------------------------------------

    if student_id is None:

        st.subheader(
            "📝 تسجيل الطالب لأول مرة"
        )

        with st.form("register_form"):

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

            if not name or not phone:

                st.error(
                    "❌ اكتب اسم الطالب ورقم هاتفه."
                )

                return

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
                        now()
                    )
                )

                conn.commit()

                new_id = cur.lastrowid

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

            except sqlite3.IntegrityError:

                existing = conn.execute(
                    """
                    SELECT id
                    FROM students
                    WHERE phone = ?
                    """,
                    (phone,)
                ).fetchone()

                if existing:

                    st.session_state.student_id = (
                        existing["id"]
                    )

                    st.query_params["student"] = (
                        str(existing["id"])
                    )

                    st.success(
                        "تم العثور على تسجيل الطالب."
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ حدث خطأ أثناء التسجيل."
                    )

            finally:

                conn.close()

        return

    # -----------------------------------------------------
    # بيانات الطالب
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

    st.success(
        f"""
        👨‍🎓 أهلاً {student["name"]}

        الصف: {student["grade"]}
        """
    )

    st.caption(
        f"رقم الطالب: {student['id']}"
    )

    # -----------------------------------------------------
    # الحصة
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث الحصة",
        use_container_width=True
    ):

        st.rerun()

    lesson = active_lesson()

    if lesson is None:

        st.warning(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.warning(
            "⚠️ الحصة الحالية ليست لصفك."
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 وقت البداية: {lesson['created_at']}"
    )

    st.markdown(
        "### 📷 امسح QR الحضور"
    )

    st.write(
        """
        وجّه الكاميرا إلى QR الموجود عند المدرس
        ثم التقط الصورة.
        """
    )

    # -----------------------------------------------------
    # الكاميرا
    # -----------------------------------------------------

    scan_key = st.session_state.get(
        "scan_key",
        0
    )

    scan = st.camera_input(
        "📷 مسح QR الحضور",
        key=f"scan_{scan_key}",
        resolution="720p"
    )

    if scan is not None:

        token = decode_qr(scan)

        if not token:

            st.error(
                "❌ لم يتم العثور على QR واضح."
            )

        else:

            ok, message = mark_attendance(
                token,
                student_id
            )

            if ok:

                st.success(message)

                st.session_state["scan_key"] = (
                    scan_key + 1
                )

                st.rerun()

            else:

                st.error(message)

    st.divider()

    st.info(
        """
        💡 بعد التسجيل أول مرة،
        بياناتك محفوظة في النظام.
        """
    )


# =========================================================
# تسجيل دخول المدرس
# =========================================================

def teacher_login():

    render_header(
        "👨‍🏫 Teacher System",
        "صفحة المدرس"
    )

    st.info(
        "🔐 صفحة المدرس منفصلة ومحمية بكلمة مرور."
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

        if stored and verify_password(
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

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

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

        lesson_name = (
            lesson_name.strip()
            or "الحصة الحالية"
        )

        token = secrets.token_urlsafe(
            24
        )

        conn = db()

        # إغلاق أي حصة قديمة
        conn.execute(
            """
            UPDATE lessons
            SET active = 0
            WHERE active = 1
            """
        )

        # إنشاء الحصة
        conn.execute(
            """
            INSERT INTO lessons
            (
                grade,
                lesson_name,
                created_at,
                active,
                token
            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                grade,
                lesson_name,
                now(),
                1,
                token
            )
        )

        conn.commit()
        conn.close()

        st.success(
            "🟢 بدأت الحصة."
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

    if lesson is None:

        st.warning(
            "لا توجد حصة مفتوحة حالياً."
        )

        return

    total, present, absent = lesson_stats(
        lesson["id"],
        lesson["grade"]
    )

    # -----------------------------------------------------
    # الأرقام
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # حالة العدد
    # -----------------------------------------------------

    if total > 0 and present == total:

        st.success(
            "🎉 العدد اكتمل — كل الطلاب حضروا."
        )

    elif total > 0:

        st.warning(
            f"⚠️ يوجد {absent} طالب غائب حتى الآن."
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذا الصف."
        )

    # -----------------------------------------------------
    # معلومات الحصة
    # -----------------------------------------------------

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**بدأت:** {lesson['created_at']}"
    )

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
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        caption="الطلاب يمسحون هذا الكود",
        width=320
    )

    # -----------------------------------------------------
    # تحديث
    # -----------------------------------------------------

    if st.button(
        "🔄 تحديث أعداد الحضور",
        use_container_width=True
    ):

        st.rerun()

    # -----------------------------------------------------
    # إنهاء الحصة
    # -----------------------------------------------------

    if st.button(
        "⛔ إنهاء الحصة",
        use_container_width=True
    ):

        conn = db()

        conn.execute(
            """
            UPDATE lessons
            SET active = 0
            WHERE id = ?
            """,
            (lesson["id"],)
        )

        conn.commit()
        conn.close()

        st.success(
            "✅ تم إنهاء الحصة."
        )

        st.rerun()

    # -----------------------------------------------------
    # الحاضرون
    # -----------------------------------------------------

    conn = db()

    rows = conn.execute(
        """
        SELECT
            s.name,
            s.phone,
            a.marked_at

        FROM attendance a

        JOIN students s
        ON s.id = a.student_id

        WHERE a.lesson_id = ?

        ORDER BY a.marked_at
        """,
        (lesson["id"],)
    ).fetchall()

    conn.close()

    st.subheader(
        "🟢 الطلاب الحاضرون"
    )

    if rows:

        st.dataframe(
            [
                {
                    "الطالب": row["name"],
                    "الهاتف": row["phone"],
                    "وقت الحضور": row["marked_at"]
                }
                for row in rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لم يسجل أي طالب حضور حتى الآن."
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
            created_at

        FROM students

        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    st.metric(
        "إجمالي الطلاب المسجلين",
        len(rows)
    )

    if rows:

        st.dataframe(
            [
                {
                    "ID": row["id"],
                    "الاسم": row["name"],
                    "هاتف الطالب": row["phone"],
                    "هاتف ولي الأمر": row["parent_phone"],
                    "الصف": row["grade"],
                    "تاريخ التسجيل": row["created_at"]
                }
                for row in rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب حتى الآن."
        )


# =========================================================
# إعدادات المدرس
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
                "❌ كلمة المرور الجديدة يجب أن تكون 4 أحرف/أرقام على الأقل."
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
                "✅ تم تغيير كلمة مرور المدرس."
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
            "👨‍🎓 الطلاب",
            "⚙️ الإعدادات"
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lesson()

    with tabs[2]:

        students_page()

    with tabs[3]:

        settings_page()

    # -----------------------------------------------------
    # رابط المدرس
    # -----------------------------------------------------

    st.divider()

    st.write(
        "🔗 رابط صفحة المدرس:"
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
