import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
from datetime import datetime

# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

DB_NAME = "teacher_system_v2.db"

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
    "الصف الثالث الثانوي"
]

DEFAULT_PASSWORD = "123456"


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # الطلاب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            phone TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # الحصص
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            active INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # إعدادات المدرس
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
    """)

    cur.execute("""
        INSERT OR IGNORE INTO settings(setting_key, setting_value)
        VALUES ('teacher_password', ?)
    """, (DEFAULT_PASSWORD,))

    conn.commit()
    conn.close()


init_db()


# =========================================================
# وظائف قاعدة البيانات
# =========================================================

def get_teacher_password():
    conn = get_db()
    row = conn.execute("""
        SELECT setting_value
        FROM settings
        WHERE setting_key = 'teacher_password'
    """).fetchone()
    conn.close()

    if row:
        return row["setting_value"]

    return DEFAULT_PASSWORD


def change_teacher_password(new_password):
    conn = get_db()

    conn.execute("""
        INSERT INTO settings(setting_key, setting_value)
        VALUES ('teacher_password', ?)
        ON CONFLICT(setting_key)
        DO UPDATE SET setting_value=excluded.setting_value
    """, (new_password,))

    conn.commit()
    conn.close()


def add_student(name, grade, phone, parent_phone):
    conn = get_db()

    existing = conn.execute("""
        SELECT id
        FROM students
        WHERE phone = ?
    """, (phone,)).fetchone()

    if existing:
        conn.close()
        return False, "رقم الهاتف مسجل بالفعل."

    conn.execute("""
        INSERT INTO students
        (name, grade, phone, parent_phone, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        name,
        grade,
        phone,
        parent_phone,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return True, "تم تسجيل الطالب بنجاح."


def create_lesson(name, grade):
    conn = get_db()

    token = secrets.token_urlsafe(20)

    cur = conn.execute("""
        INSERT INTO lessons
        (lesson_name, grade, token, active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (
        name,
        grade,
        token,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    lesson_id = cur.lastrowid

    conn.execute("""
        UPDATE lessons
        SET active = 0
        WHERE id != ?
    """, (lesson_id,))

    conn.commit()
    conn.close()

    return lesson_id, token


def get_active_lesson():
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return row


def get_lesson_by_token(token):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token = ?
        LIMIT 1
    """, (token,)).fetchone()

    conn.close()

    return row


def mark_attendance(token, student_id):
    lesson = get_lesson_by_token(token)

    if not lesson:
        return False, "كود الحصة غير صحيح."

    if lesson["active"] != 1:
        return False, "الحصة غير نشطة حاليًا."

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO attendance
            (lesson_id, student_id, attended_at)
            VALUES (?, ?, ?)
        """, (
            lesson["id"],
            student_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        return True, "تم تسجيل الحضور بنجاح."

    except sqlite3.IntegrityError:
        conn.close()
        return False, "الطالب سجل حضوره بالفعل في هذه الحصة."


def get_lesson_attendance(lesson_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT
            students.id,
            students.name,
            students.grade,
            students.phone,
            students.parent_phone,
            attendance.attended_at
        FROM attendance
        INNER JOIN students
        ON students.id = attendance.student_id
        WHERE attendance.lesson_id = ?
        ORDER BY attendance.id DESC
    """, (lesson_id,)).fetchall()

    conn.close()

    return rows


def get_students_by_grade(grade):
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM students
        WHERE grade = ?
        ORDER BY name
    """, (grade,)).fetchall()

    conn.close()

    return rows


def get_all_students():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def make_qr(token):
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


def scan_qr_from_image(uploaded_file):
    if uploaded_file is None:
        return None

    try:
        bytes_data = uploaded_file.getvalue()

        image_array = np.frombuffer(
            bytes_data,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(image)

        if data:
            return data.strip()

    except Exception:
        return None

    return None


# =========================================================
# Session
# =========================================================

if "page" not in st.session_state:
    st.session_state.page = "student"

if "teacher_logged" not in st.session_state:
    st.session_state.teacher_logged = False


# =========================================================
# التصميم
# =========================================================

st.title("🎓 Teacher System")
st.subheader("نظام إدارة المدرس والحضور الذكي")

st.divider()


# =========================================================
# اختيار الصفحة
# =========================================================

if st.session_state.teacher_logged:

    mode = st.radio(
        "اختر الصفحة",
        ["لوحة المدرس", "صفحة الطالب"],
        horizontal=True
    )

else:

    mode = "صفحة الطالب"


# =========================================================
# صفحة الطالب
# =========================================================

if mode == "صفحة الطالب":

    st.header("👨‍🎓 صفحة الطالب")

    st.info(
        "الطالب يسجل بياناته أول مرة فقط، "
        "وبعد ذلك يستخدم QR الخاص بالحصة لتسجيل الحضور."
    )

    tab1, tab2 = st.tabs([
        "📝 التسجيل لأول مرة",
        "📷 تسجيل الحضور"
    ])

    # -----------------------------------------------------
    # تسجيل الطالب
    # -----------------------------------------------------

    with tab1:

        st.subheader("📝 تسجيل بيانات الطالب")

        name = st.text_input(
            "اسم الطالب"
        )

        grade = st.selectbox(
            "الصف",
            GRADES
        )

        phone = st.text_input(
            "رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "رقم هاتف ولي الأمر"
        )

        if st.button(
            "✅ تسجيل الطالب",
            use_container_width=True
        ):

            if not name.strip():
                st.error("اكتب اسم الطالب.")

            elif not phone.strip():
                st.error("اكتب رقم هاتف الطالب.")

            elif not parent_phone.strip():
                st.error("اكتب رقم ولي الأمر.")

            else:

                ok, message = add_student(
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip()
                )

                if ok:
                    st.success(message)
                    st.balloons()

                else:
                    st.warning(message)

    # -----------------------------------------------------
    # الحضور
    # -----------------------------------------------------

    with tab2:

        st.subheader("📷 تسجيل حضور الحصة")

        phone_check = st.text_input(
            "اكتب رقم هاتفك المسجل",
            key="attendance_phone"
        )

        student = None

        if phone_check.strip():

            conn = get_db()

            student = conn.execute("""
                SELECT *
                FROM students
                WHERE phone = ?
                LIMIT 1
            """, (phone_check.strip(),)).fetchone()

            conn.close()

        if student:

            st.success(
                f"👨‍🎓 الطالب: {student['name']}"
            )

            st.write(
                f"الصف: **{student['grade']}**"
            )

            lesson = get_active_lesson()

            if not lesson:

                st.warning(
                    "🔴 لا توجد حصة نشطة حاليًا."
                )

            else:

                if lesson["grade"] != student["grade"]:

                    st.warning(
                        "⚠️ الحصة الحالية ليست لنفس صف الطالب."
                    )

                else:

                    st.info(
                        f"🟢 الحصة الحالية: {lesson['lesson_name']}"
                    )

                    st.write(
                        "وجّه الكاميرا إلى QR الموجود عند المدرس."
                    )

                    camera = st.camera_input(
                        "📷 صوّر QR الخاص بالحصة"
                    )

                    if camera:

                        token = scan_qr_from_image(
                            camera
                        )

                        if token:

                            if token == lesson["token"]:

                                ok, message = mark_attendance(
                                    token,
                                    student["id"]
                                )

                                if ok:
                                    st.success(
                                        f"✅ {student['name']} تم تسجيل حضورك."
                                    )
                                    st.balloons()

                                else:
                                    st.warning(message)

                            else:

                                st.error(
                                    "❌ هذا QR ليس للحصة الحالية."
                                )

                        else:

                            st.warning(
                                "لم يتم التعرف على QR. "
                                "قرّب الكاميرا وحاول مرة أخرى."
                            )

        elif phone_check.strip():

            st.error(
                "❌ رقم الهاتف غير مسجل."
            )


# =========================================================
# لوحة المدرس
# =========================================================

elif mode == "لوحة المدرس":

    st.header("👨‍🏫 لوحة تحكم المدرس")

    if not st.session_state.teacher_logged:

        st.subheader("🔐 تسجيل دخول المدرس")

        password = st.text_input(
            "كلمة المرور",
            type="password"
        )

        if st.button(
            "دخول",
            use_container_width=True
        ):

            if password == get_teacher_password():

                st.session_state.teacher_logged = True
                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )

    else:

        # =================================================
        # تسجيل الخروج
        # =================================================

        if st.button("🚪 تسجيل الخروج"):

            st.session_state.teacher_logged = False
            st.rerun()

        # =================================================
        # إنشاء حصة
        # =================================================

        st.subheader("📚 إنشاء حصة جديدة")

        lesson_grade = st.selectbox(
            "الصف",
            GRADES,
            key="lesson_grade"
        )

        lesson_name = st.text_input(
            "اسم الحصة",
            value="الحصة الحالية"
        )

        if st.button(
            "🟢 بدء الحصة",
            use_container_width=True
        ):

            if not lesson_name.strip():

                st.error(
                    "اكتب اسم الحصة."
                )

            else:

                lesson_id, token = create_lesson(
                    lesson_name.strip(),
                    lesson_grade
                )

                st.success(
                    "✅ تم بدء الحصة."
                )

                st.session_state.current_lesson_id = lesson_id

        # =================================================
        # الحصة الحالية
        # =================================================

        lesson = get_active_lesson()

        if lesson:

            st.divider()

            st.subheader(
                f"🟢 الحصة الحالية: {lesson['lesson_name']}"
            )

            st.write(
                f"الصف: **{lesson['grade']}**"
            )

            qr_image = make_qr(
                lesson["token"]
            )

            st.image(
                qr_image,
                caption="📷 QR الخاص بالحصة"
            )

            st.info(
                "الطالب يصوّر QR ده من صفحة الحضور "
                "ويسجل حضوره مباشرة."
            )

            # ---------------------------------------------
            # الإحصائيات
            # ---------------------------------------------

            students = get_students_by_grade(
                lesson["grade"]
            )

            attendance = get_lesson_attendance(
                lesson["id"]
            )

            total_students = len(students)
            attended = len(attendance)
            absent = max(
                total_students - attended,
                0
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "👨‍🎓 إجمالي الطلاب",
                    total_students
                )

            with col2:
                st.metric(
                    "🟢 حضر",
                    attended
                )

            with col3:
                st.metric(
                    "🔴 غاب",
                    absent
                )

            if total_students > 0:

                if attended == total_students:

                    st.success(
                        "🎉 العدد اكتمل — كل الطلاب حضروا."
                    )

                else:

                    st.warning(
                        f"⚠️ لسه في {absent} طالب غائب."
                    )

            # ---------------------------------------------
            # الطلاب الذين حضروا
            # ---------------------------------------------

            st.divider()

            st.subheader(
                "🟢 الطلاب الذين سجلوا الحضور"
            )

            if attendance:

                for student in attendance:

                    st.success(
                        f"👨‍🎓 {student['name']} | "
                        f"📱 {student['phone']} | "
                        f"📞 ولي الأمر: {student['parent_phone']} | "
                        f"⏰ {student['attended_at']}"
                    )

            else:

                st.info(
                    "لم يسجل أي طالب حضوره حتى الآن."
                )

            # ---------------------------------------------
            # الغياب
            # ---------------------------------------------

            st.divider()

            st.subheader(
                "🔴 الطلاب الغائبون"
            )

            attended_ids = {
                row["id"]
                for row in attendance
            }

            absent_students = [
                student
                for student in students
                if student["id"] not in attended_ids
            ]

            if absent_students:

                for student in absent_students:

                    st.error(
                        f"🔴 {student['name']} | "
                        f"📱 {student['phone']} | "
                        f"📞 ولي الأمر: {student['parent_phone']}"
                    )

            else:

                st.success(
                    "لا يوجد طلاب غائبون."
                )

        # =================================================
        # جميع الطلاب
        # =================================================

        st.divider()

        st.subheader(
            "👨‍🎓 جميع الطلاب المسجلين"
        )

        all_students = get_all_students()

        st.write(
            f"إجمالي الطلاب: **{len(all_students)}**"
        )

        for student in all_students:

            with st.expander(
                f"👨‍🎓 {student['name']} — {student['grade']}"
            ):

                st.write(
                    f"📱 رقم الطالب: {student['phone']}"
                )

                st.write(
                    f"📞 رقم ولي الأمر: {student['parent_phone']}"
                )

        # =================================================
        # تغيير كلمة المرور
        # =================================================

        st.divider()

        st.subheader(
            "🔑 تغيير كلمة مرور المدرس"
        )

        new_password = st.text_input(
            "كلمة المرور الجديدة",
            type="password"
        )

        confirm_password = st.text_input(
            "تأكيد كلمة المرور",
            type="password"
        )

        if st.button(
            "🔐 تغيير كلمة المرور"
        ):

            if len(new_password) < 4:

                st.error(
                    "كلمة المرور يجب أن تكون 4 أحرف أو أرقام على الأقل."
                )

            elif new_password != confirm_password:

                st.error(
                    "كلمتا المرور غير متطابقتين."
                )

            else:

                change_teacher_password(
                    new_password
                )

                st.success(
                    "✅ تم تغيير كلمة مرور المدرس بنجاح."
                )


# =========================================================
# تذييل
# =========================================================

st.divider()

st.caption(
    "🎓 Teacher System — Smart Attendance"
            )
