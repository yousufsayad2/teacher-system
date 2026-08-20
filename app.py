import streamlit as st
import sqlite3
import hashlib
import secrets
import qrcode
import io
from datetime import datetime


# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# قاعدة البيانات
# =========================================================

DB_NAME = "teacher_system.db"


def get_db():

    conn = sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


conn = get_db()


# =========================================================
# إنشاء الجداول
# =========================================================

conn.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    student_code TEXT UNIQUE NOT NULL,
    qr_secret TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")


conn.execute("""
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_code TEXT UNIQUE NOT NULL,
    lesson_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
)
""")


conn.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    lesson_id INTEGER NOT NULL,
    scanned_at TEXT NOT NULL,
    UNIQUE(student_id, lesson_id)
)
""")


conn.commit()


# =========================================================
# Functions
# =========================================================

def create_student_code(name):

    clean_name = "".join(
        c for c in name
        if c.isalnum()
    )[:6].upper()

    random_part = secrets.token_hex(3).upper()

    return f"{clean_name}-{random_part}"


def create_lesson_code():

    return secrets.token_urlsafe(12)


def create_qr(data):

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(data)

    qr.make(
        fit=True
    )

    image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG"
    )

    buffer.seek(0)

    return buffer


def get_students():

    return conn.execute(
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()


def get_attendance():

    return conn.execute(
        """
        SELECT
            attendance.id,
            students.name,
            students.student_code,
            lessons.lesson_name,
            attendance.scanned_at
        FROM attendance
        JOIN students
        ON attendance.student_id = students.id
        JOIN lessons
        ON attendance.lesson_id = lessons.id
        ORDER BY attendance.id DESC
        """
    ).fetchall()


# =========================================================
# العنوان
# =========================================================

st.title("🎓 Teacher System")

st.caption(
    "نظام إدارة المدرس والحضور الذكي"
)


# =========================================================
# Sidebar
# =========================================================

with st.sidebar:

    st.header("👨‍🏫 لوحة التحكم")

    page = st.radio(
        "اختر القسم",
        [
            "🏠 الرئيسية",
            "👨‍🎓 الطلاب",
            "📱 QR الحصة",
            "✅ الحضور",
        ]
    )


# =========================================================
# الرئيسية
# =========================================================

if page == "🏠 الرئيسية":

    st.subheader(
        "👋 أهلاً بك في Teacher System"
    )

    students = get_students()

    attendance = get_attendance()

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "👨‍🎓 عدد الطلاب",
            len(students)
        )

    with col2:

        st.metric(
            "✅ سجلات الحضور",
            len(attendance)
        )

    with col3:

        active_lessons = conn.execute(
            """
            SELECT COUNT(*)
            FROM lessons
            WHERE active = 1
            """
        ).fetchone()[0]

        st.metric(
            "📚 الحصص النشطة",
            active_lessons
        )

    st.divider()

    st.info(
        """
        النظام الحالي يحتوي على إدارة الطلاب
        وإنشاء QR للحصة وتسجيل الحضور.

        الخطوة القادمة ستكون ربط QR بالكاميرا
        بحيث الطالب يعمل Scan ويتم تسجيل حضوره.
        """
    )


# =========================================================
# الطلاب
# =========================================================

elif page == "👨‍🎓 الطلاب":

    st.subheader(
        "👨‍🎓 إدارة الطلاب"
    )

    with st.form(
        "add_student",
        clear_on_submit=True
    ):

        name = st.text_input(
            "اسم الطالب"
        )

        phone = st.text_input(
            "رقم ولي الأمر / الهاتف"
        )

        submitted = st.form_submit_button(
            "➕ إضافة الطالب",
            use_container_width=True
        )

        if submitted:

            if not name.strip():

                st.error(
                    "❌ اكتب اسم الطالب."
                )

            else:

                student_code = create_student_code(
                    name
                )

                qr_secret = secrets.token_hex(
                    16
                )

                try:

                    conn.execute(
                        """
                        INSERT INTO students
                        (
                            name,
                            phone,
                            student_code,
                            qr_secret,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            name.strip(),
                            phone.strip(),
                            student_code,
                            qr_secret,
                            datetime.now().isoformat()
                        )
                    )

                    conn.commit()

                    st.success(
                        f"✅ تم إضافة {name}"
                    )

                except sqlite3.IntegrityError:

                    st.error(
                        "❌ حصل تعارض في كود الطالب، جرّب مرة أخرى."
                    )

    st.divider()

    students = get_students()

    if not students:

        st.info(
            "لسه مفيش طلاب."
        )

    else:

        for student in students:

            with st.container(
                border=True
            ):

                col1, col2 = st.columns(
                    [3, 1]
                )

                with col1:

                    st.markdown(
                        f"### 👨‍🎓 {student['name']}"
                    )

                    st.write(
                        f"🆔 كود الطالب: `{student['student_code']}`"
                    )

                    if student["phone"]:

                        st.write(
                            f"📞 الهاتف: {student['phone']}"
                        )

                with col2:

                    qr_data = (
                        "STUDENT:"
                        + student["student_code"]
                        + "|SECRET:"
                        + student["qr_secret"]
                    )

                    qr_image = create_qr(
                        qr_data
                    )

                    st.image(
                        qr_image,
                        caption="QR الطالب"
                    )


# =========================================================
# QR الحصة
# =========================================================

elif page == "📱 QR الحصة":

    st.subheader(
        "📱 إنشاء QR للحصة"
    )

    st.write(
        "كل مرة تعمل حصة جديدة يتم إنشاء QR جديد."
    )

    lesson_name = st.text_input(
        "اسم الحصة",
        placeholder="مثال: رياضيات - الحصة 1"
    )

    if st.button(
        "🚀 بدء حصة جديدة",
        use_container_width=True
    ):

        if not lesson_name.strip():

            st.error(
                "❌ اكتب اسم الحصة."
            )

        else:

            lesson_code = create_lesson_code()

            conn.execute(
                """
                UPDATE lessons
                SET active = 0
                WHERE active = 1
                """
            )

            conn.execute(
                """
                INSERT INTO lessons
                (
                    lesson_code,
                    lesson_name,
                    created_at,
                    active
                )
                VALUES (?, ?, ?, 1)
                """,
                (
                    lesson_code,
                    lesson_name.strip(),
                    datetime.now().isoformat()
                )
            )

            conn.commit()

            st.session_state.current_lesson = lesson_code

            st.success(
                "✅ تم بدء الحصة."
            )

    # عرض الحصة الحالية

    if "current_lesson" in st.session_state:

        lesson_code = st.session_state.current_lesson

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE lesson_code = ?
            """,
            (lesson_code,)
        ).fetchone()

        if lesson:

            st.divider()

            st.markdown(
                f"### 📚 {lesson['lesson_name']}"
            )

            st.caption(
                "QR الحصة الحالية"
            )

            qr_data = (
                "LESSON:"
                + lesson["lesson_code"]
            )

            qr_image = create_qr(
                qr_data
            )

            col1, col2, col3 = st.columns(
                [1, 2, 1]
            )

            with col2:

                st.image(
                    qr_image,
                    width=350
                )

            st.code(
                lesson["lesson_code"]
            )

            st.warning(
                "⚠️ في النسخة القادمة سنجعل QR الحصة يتغير تلقائيًا أثناء الحصة."
            )


# =========================================================
# الحضور
# =========================================================

elif page == "✅ الحضور":

    st.subheader(
        "✅ سجل الحضور"
    )

    attendance = get_attendance()

    if not attendance:

        st.info(
            "لا يوجد حضور مسجل حتى الآن."
        )

    else:

        for record in attendance:

            with st.container(
                border=True
            ):

                st.write(
                    f"👨‍🎓 **{record['name']}**"
                )

                st.write(
                    f"🆔 {record['student_code']}"
                )

                st.write(
                    f"📚 الحصة: {record['lesson_name']}"
                )

                st.write(
                    f"🕐 الوقت: {record['scanned_at']}"
                )


# =========================================================
# Footer
# =========================================================

st.divider()

st.caption(
    "🎓 Teacher System — Developed by يوسف"
                    )
