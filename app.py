import streamlit as st
import sqlite3
import secrets
import qrcode
import io
import cv2
import numpy as np
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
# وظائف مساعدة
# =========================================================

def create_student_code(name):

    clean_name = "".join(
        c for c in name
        if c.isalnum()
    )[:6].upper()

    random_part = secrets.token_hex(3).upper()

    return f"{clean_name}-{random_part}"


def create_lesson_code():

    return secrets.token_urlsafe(16)


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


def get_active_lesson():

    return conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


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
# قراءة QR بالكاميرا
# =========================================================

def scan_qr(image_file):

    try:

        image_bytes = image_file.getvalue()

        image_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(
            image
        )

        if data:

            return data.strip()

        return ""

    except Exception:

        return ""


# =========================================================
# التحقق من QR الطالب
# =========================================================

def verify_student_qr(qr_data, lesson):

    if not qr_data:
        return None, "❌ لم يتم العثور على QR."

    if not lesson:
        return None, "❌ لا توجد حصة نشطة حاليًا."

    try:

        parts = {}

        for item in qr_data.split("|"):

            if ":" in item:

                key, value = item.split(
                    ":",
                    1
                )

                parts[key] = value

        student_code = parts.get(
            "STUDENT"
        )

        lesson_code = parts.get(
            "LESSON"
        )

        student_secret = parts.get(
            "SECRET"
        )

        if not student_code:
            return None, "❌ QR غير صالح."

        if not lesson_code:
            return None, "❌ QR الحصة غير موجود."

        if not student_secret:
            return None, "❌ QR الطالب غير صالح."

        if lesson_code != lesson["lesson_code"]:

            return None, (
                "⚠️ QR الطالب خاص بحصة أخرى."
            )

        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE student_code = ?
            """,
            (student_code,)
        ).fetchone()

        if not student:

            return None, "❌ الطالب غير موجود."

        if student["qr_secret"] != student_secret:

            return None, "❌ QR غير صالح."

        return student, ""

    except Exception:

        return None, "❌ تعذر قراءة QR."


# =========================================================
# العنوان
# =========================================================

st.title("🎓 Teacher System")

st.caption(
    "نظام إدارة المدرس والحضور الذكي"
)


# =========================================================
# القائمة
# =========================================================

with st.sidebar:

    st.header("👨‍🏫 لوحة المدرس")

    page = st.radio(
        "اختر القسم",
        [
            "🏠 الرئيسية",
            "👨‍🎓 الطلاب",
            "📚 الحصة الحالية",
            "📷 مسح QR",
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

    active_lesson = get_active_lesson()

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

        st.metric(
            "📚 الحصة النشطة",
            1 if active_lesson else 0
        )

    st.divider()

    if active_lesson:

        st.success(
            f"🟢 الحصة الحالية: {active_lesson['lesson_name']}"
        )

    else:

        st.info(
            "🔴 لا توجد حصة نشطة. اذهب إلى «الحصة الحالية» وابدأ حصة."
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
            "رقم ولي الأمر"
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
                    20
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
                        f"✅ تم إضافة الطالب: {name}"
                    )

                except sqlite3.IntegrityError:

                    st.error(
                        "❌ حصل تعارض، حاول مرة أخرى."
                    )

    st.divider()

    students = get_students()

    active_lesson = get_active_lesson()

    if not students:

        st.info(
            "لا يوجد طلاب حتى الآن."
        )

    else:

        for student in students:

            with st.container(
                border=True
            ):

                st.markdown(
                    f"### 👨‍🎓 {student['name']}"
                )

                st.write(
                    f"🆔 كود الطالب: `{student['student_code']}`"
                )

                if student["phone"]:

                    st.write(
                        f"📞 ولي الأمر: {student['phone']}"
                    )

                # QR يتغير حسب الحصة الحالية

                if active_lesson:

                    qr_data = (
                        "STUDENT:"
                        + student["student_code"]
                        + "|LESSON:"
                        + active_lesson["lesson_code"]
                        + "|SECRET:"
                        + student["qr_secret"]
                    )

                    qr_image = create_qr(
                        qr_data
                    )

                    st.image(
                        qr_image,
                        width=220,
                        caption=(
                            "QR الطالب للحصة الحالية"
                        )
                    )

                else:

                    st.warning(
                        "ابدأ حصة أولًا لإنشاء QR خاص بها."
                    )


# =========================================================
# الحصة الحالية
# =========================================================

elif page == "📚 الحصة الحالية":

    st.subheader(
        "📚 إدارة الحصة"
    )

    active_lesson = get_active_lesson()

    if active_lesson:

        st.success(
            f"🟢 الحصة الحالية: {active_lesson['lesson_name']}"
        )

        st.write(
            f"بدأت: {active_lesson['created_at']}"
        )

        if st.button(
            "🔴 إنهاء الحصة",
            use_container_width=True
        ):

            conn.execute(
                """
                UPDATE lessons
                SET active = 0
                WHERE id = ?
                """,
                (active_lesson["id"],)
            )

            conn.commit()

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

    else:

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

                conn.execute(
                    """
                    UPDATE lessons
                    SET active = 0
                    WHERE active = 1
                    """
                )

                lesson_code = create_lesson_code()

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

                st.success(
                    "✅ تم بدء الحصة."
                )

                st.rerun()


# =========================================================
# مسح QR
# =========================================================

elif page == "📷 مسح QR":

    st.subheader(
        "📷 تسجيل حضور الطالب"
    )

    active_lesson = get_active_lesson()

    if not active_lesson:

        st.error(
            "❌ لازم تبدأ حصة أولًا."
        )

    else:

        st.success(
            f"🟢 الحصة: {active_lesson['lesson_name']}"
        )

        st.write(
            "وجّه كاميرا الهاتف إلى QR الطالب."
        )

        camera_image = st.camera_input(
            "📷 تصوير QR الطالب"
        )

        if camera_image:

            qr_data = scan_qr(
                camera_image
            )

            if not qr_data:

                st.error(
                    "❌ مش قادر أقرأ QR. قرّب الكاميرا وحاول تاني."
                )

            else:

                student, error = verify_student_qr(
                    qr_data,
                    active_lesson
                )

                if error:

                    st.error(
                        error
                    )

                else:

                    existing = conn.execute(
                        """
                        SELECT *
                        FROM attendance
                        WHERE student_id = ?
                        AND lesson_id = ?
                        """,
                        (
                            student["id"],
                            active_lesson["id"]
                        )
                    ).fetchone()

                    if existing:

                        st.warning(
                            f"⚠️ {student['name']} مسجل حضوره بالفعل."
                        )

                    else:

                        now = datetime.now().isoformat()

                        conn.execute(
                            """
                            INSERT INTO attendance
                            (
                                student_id,
                                lesson_id,
                                scanned_at
                            )
                            VALUES (?, ?, ?)
                            """,
                            (
                                student["id"],
                                active_lesson["id"],
                                now
                            )
                        )

                        conn.commit()

                        st.success(
                            f"✅ تم تسجيل حضور {student['name']} بنجاح!"
                        )

                        st.balloons()


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

                st.markdown(
                    f"### 👨‍🎓 {record['name']}"
                )

                st.write(
                    f"🆔 {record['student_code']}"
                )

                st.write(
                    f"📚 {record['lesson_name']}"
                )

                st.write(
                    f"🕐 {record['scanned_at']}"
                )


# =========================================================
# Footer
# =========================================================

st.divider()

st.caption(
    "🎓 Teacher System — Developed by يوسف"
        )
