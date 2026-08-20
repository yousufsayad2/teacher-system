import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
from datetime import datetime
import secrets

# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

# قاعدة بيانات جديدة تمامًا
DB = "attendance_system_new.db"

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

def db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = db()
    cur = conn.cursor()

    # جدول الطلاب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # جدول الحصص
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            qr_code TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # جدول الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # جدول إعدادات المدرس
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teacher_settings (
            id INTEGER PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)

    # كلمة المرور الافتراضية
    cur.execute("""
        SELECT COUNT(*)
        FROM teacher_settings
    """)

    count = cur.fetchone()[0]

    if count == 0:
        cur.execute(
            "INSERT INTO teacher_settings(id, password) VALUES(1, ?)",
            (DEFAULT_PASSWORD,)
        )

    conn.commit()
    conn.close()


# تشغيل قاعدة البيانات
init_db()


# =========================================================
# كلمة مرور المدرس
# =========================================================

def get_password():

    conn = db()

    row = conn.execute(
        "SELECT password FROM teacher_settings WHERE id = 1"
    ).fetchone()

    conn.close()

    if row:
        return row["password"]

    return DEFAULT_PASSWORD


def update_password(new_password):

    conn = db()

    conn.execute(
        "UPDATE teacher_settings SET password = ? WHERE id = 1",
        (new_password,)
    )

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def register_student(
    name,
    grade,
    phone,
    parent_phone
):

    conn = db()

    old = conn.execute(
        "SELECT id FROM students WHERE phone = ?",
        (phone,)
    ).fetchone()

    if old:
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


def get_student(phone):

    conn = db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE phone = ?
    """, (phone,)).fetchone()

    conn.close()

    return student


def get_students(grade=None):

    conn = db()

    if grade:

        rows = conn.execute("""
            SELECT *
            FROM students
            WHERE grade = ?
            ORDER BY name
        """, (grade,)).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM students
            ORDER BY name
        """).fetchall()

    conn.close()

    return rows


# =========================================================
# الحصص
# =========================================================

def start_lesson(name, grade):

    conn = db()

    # إيقاف أي حصة قديمة
    conn.execute("""
        UPDATE lessons
        SET active = 0
        WHERE active = 1
    """)

    qr_code = secrets.token_urlsafe(24)

    cur = conn.execute("""
        INSERT INTO lessons
        (name, grade, qr_code, active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (
        name,
        grade,
        qr_code,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id, qr_code


def active_lesson():

    conn = db()

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return lesson


# =========================================================
# الحضور
# =========================================================

def take_attendance(lesson_id, student_id):

    conn = db()

    already = conn.execute("""
        SELECT id
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson_id,
        student_id
    )).fetchone()

    if already:

        conn.close()

        return False, "الطالب سجل الحضور بالفعل."

    conn.execute("""
        INSERT INTO attendance
        (lesson_id, student_id, attended_at)
        VALUES (?, ?, ?)
    """, (
        lesson_id,
        student_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return True, "تم تسجيل الحضور."


def get_attendance(lesson_id):

    conn = db()

    rows = conn.execute("""
        SELECT
            students.id,
            students.name,
            students.grade,
            students.phone,
            students.parent_phone,
            attendance.attended_at
        FROM attendance
        JOIN students
        ON students.id = attendance.student_id
        WHERE attendance.lesson_id = ?
        ORDER BY attendance.id DESC
    """, (lesson_id,)).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def create_qr(text):

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(text)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    output = io.BytesIO()

    image.save(
        output,
        format="PNG"
    )

    output.seek(0)

    return output


def read_qr(uploaded_file):

    try:

        data = uploaded_file.getvalue()

        array = np.frombuffer(
            data,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            array,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(
            image
        )

        if text:
            return text.strip()

    except Exception:
        pass

    return None


# =========================================================
# Session
# =========================================================

if "teacher_logged" not in st.session_state:
    st.session_state.teacher_logged = False

if "student_registered" not in st.session_state:
    st.session_state.student_registered = False

if "student_phone" not in st.session_state:
    st.session_state.student_phone = ""


# =========================================================
# العنوان
# =========================================================

st.title("🎓 Teacher System")
st.subheader("نظام إدارة المدرس والحضور الذكي")

st.divider()


# =========================================================
# الصفحة الرئيسية
# =========================================================

if not st.session_state.teacher_logged:

    st.header("👨‍🎓 صفحة الطالب")

    st.info(
        "المدرس فقط يستطيع الدخول إلى لوحة التحكم. "
        "الطالب لن تظهر له لوحة المدرس."
    )

    tab_register, tab_attendance = st.tabs([
        "📝 تسجيل الطالب",
        "📷 تسجيل الحضور"
    ])


    # =====================================================
    # تسجيل الطالب أول مرة
    # =====================================================

    with tab_register:

        st.subheader(
            "📝 تسجيل بيانات الطالب لأول مرة"
        )

        student_name = st.text_input(
            "اسم الطالب",
            key="student_name"
        )

        student_grade = st.selectbox(
            "الصف",
            GRADES,
            key="student_grade"
        )

        student_phone = st.text_input(
            "رقم هاتف الطالب",
            key="student_phone_register"
        )

        parent_phone = st.text_input(
            "رقم هاتف ولي الأمر",
            key="parent_phone"
        )

        if st.button(
            "✅ تسجيل الطالب",
            use_container_width=True
        ):

            if not student_name.strip():

                st.error("اكتب اسم الطالب.")

            elif not student_phone.strip():

                st.error("اكتب رقم هاتف الطالب.")

            elif not parent_phone.strip():

                st.error("اكتب رقم ولي الأمر.")

            else:

                success, message = register_student(
                    student_name.strip(),
                    student_grade,
                    student_phone.strip(),
                    parent_phone.strip()
                )

                if success:

                    st.session_state.student_registered = True
                    st.session_state.student_phone = student_phone.strip()

                    st.success(message)

                    st.info(
                        "✅ خلاص، بياناتك اتسجلت. "
                        "في الحصص القادمة استخدم صفحة تسجيل الحضور."
                    )

                else:

                    st.warning(message)


    # =====================================================
    # تسجيل الحضور
    # =====================================================

    with tab_attendance:

        st.subheader(
            "📷 تسجيل حضور الحصة"
        )

        phone = st.text_input(
            "رقم هاتف الطالب المسجل",
            value=st.session_state.student_phone,
            key="attendance_phone"
        )

        student = None

        if phone.strip():

            student = get_student(
                phone.strip()
            )

        if student:

            st.success(
                f"👨‍🎓 الطالب: {student['name']}"
            )

            st.write(
                f"📚 الصف: **{student['grade']}**"
            )

            lesson = active_lesson()

            if not lesson:

                st.warning(
                    "🔴 لا توجد حصة مفتوحة حاليًا."
                )

            elif lesson["grade"] != student["grade"]:

                st.error(
                    "❌ الحصة الحالية ليست لنفس صف الطالب."
                )

            else:

                st.success(
                    f"🟢 الحصة الحالية: {lesson['name']}"
                )

                st.write(
                    "📷 صوّر QR الموجود عند المدرس."
                )

                camera = st.camera_input(
                    "فتح الكاميرا"
                )

                if camera:

                    qr_text = read_qr(
                        camera
                    )

                    if not qr_text:

                        st.warning(
                            "لم أستطع قراءة QR. "
                            "قرّب الكاميرا وحاول مرة أخرى."
                        )

                    elif qr_text != lesson["qr_code"]:

                        st.error(
                            "❌ QR ده مش خاص بالحصة الحالية."
                        )

                    else:

                        success, message = take_attendance(
                            lesson["id"],
                            student["id"]
                        )

                        if success:

                            st.success(
                                f"🎉 تم تسجيل حضور {student['name']} بنجاح."
                            )

                            st.balloons()

                        else:

                            st.info(
                                message
                            )

        elif phone.strip():

            st.error(
                "❌ الطالب غير مسجل. "
                "سجل بياناتك أولًا."
            )


# =========================================================
# لوحة المدرس
# =========================================================

else:

    st.header("👨‍🏫 لوحة تحكم المدرس")

    if st.button("🚪 تسجيل الخروج"):

        st.session_state.teacher_logged = False

        st.rerun()


    # =====================================================
    # إنشاء حصة
    # =====================================================

    st.divider()

    st.subheader(
        "📚 إنشاء حصة"
    )

    lesson_grade = st.selectbox(
        "اختر الصف",
        GRADES,
        key="teacher_grade"
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

            lesson_id, code = start_lesson(
                lesson_name.strip(),
                lesson_grade
            )

            st.success(
                "✅ تم بدء الحصة."
            )

            st.rerun()


    # =====================================================
    # الحصة الحالية
    # =====================================================

    lesson = active_lesson()

    if lesson:

        st.divider()

        st.subheader(
            f"🟢 {lesson['name']}"
        )

        st.write(
            f"📚 الصف: **{lesson['grade']}**"
        )

        st.write(
            "📷 خلي الطلاب يصوروا QR ده:"
        )

        qr = create_qr(
            lesson["qr_code"]
        )

        st.image(
            qr,
            width=350
        )


        # =================================================
        # الإحصائيات
        # =================================================

        students = get_students(
            lesson["grade"]
        )

        attendance = get_attendance(
            lesson["id"]
        )

        total = len(students)

        present = len(attendance)

        absent = max(
            total - present,
            0
        )

        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric(
                "👨‍🎓 إجمالي الطلاب",
                total
            )

        with c2:

            st.metric(
                "🟢 الحضور",
                present
            )

        with c3:

            st.metric(
                "🔴 الغياب",
                absent
            )


        # =================================================
        # حالة العدد
        # =================================================

        if total == 0:

            st.info(
                "لا يوجد طلاب مسجلون في هذا الصف."
            )

        elif present == total:

            st.success(
                "🎉 العدد اكتمل — كل الطلاب حضروا."
            )

        else:

            st.warning(
                f"⚠️ باقي {absent} طالب لم يسجلوا الحضور."
            )


        # =================================================
        # الحاضرون
        # =================================================

        st.divider()

        st.subheader(
            "🟢 الطلاب الذين سجلوا الحضور"
        )

        if attendance:

            for student in attendance:

                st.success(
                    f"👨‍🎓 {student['name']}  |  "
                    f"📱 {student['phone']}  |  "
                    f"📞 ولي الأمر: {student['parent_phone']}  |  "
                    f"⏰ {student['attended_at']}"
                )

        else:

            st.info(
                "لم يسجل أي طالب الحضور حتى الآن."
            )


        # =================================================
        # الغائبون
        # =================================================

        st.divider()

        st.subheader(
            "🔴 الطلاب الغائبون"
        )

        present_ids = set(
            student["id"]
            for student in attendance
        )

        absent_students = [
            student
            for student in students
            if student["id"] not in present_ids
        ]

        if absent_students:

            for student in absent_students:

                st.error(
                    f"🔴 {student['name']}  |  "
                    f"📱 {student['phone']}  |  "
                    f"📞 ولي الأمر: {student['parent_phone']}"
                )

        else:

            st.success(
                "🎉 لا يوجد غياب."
            )


# =========================================================
# تسجيل دخول المدرس
# =========================================================

if not st.session_state.teacher_logged:

    st.divider()

    with st.expander(
        "👨‍🏫 دخول المدرس"
    ):

        teacher_password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "🔐 دخول المدرس",
            use_container_width=True
        ):

            if teacher_password == get_password():

                st.session_state.teacher_logged = True

                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )


# =========================================================
# تغيير كلمة المرور
# =========================================================

if st.session_state.teacher_logged:

    st.divider()

    st.subheader(
        "🔑 تغيير كلمة مرور المدرس"
    )

    new_pass = st.text_input(
        "كلمة المرور الجديدة",
        type="password"
    )

    confirm_pass = st.text_input(
        "تأكيد كلمة المرور",
        type="password"
    )

    if st.button(
        "🔐 تغيير كلمة المرور"
    ):

        if len(new_pass) < 4:

            st.error(
                "كلمة المرور لازم تكون 4 أحرف/أرقام على الأقل."
            )

        elif new_pass != confirm_pass:

            st.error(
                "كلمتا المرور غير متطابقتين."
            )

        else:

            update_password(
                new_pass
            )

            st.success(
                "✅ تم تغيير كلمة المرور."
            )


# =========================================================
# النهاية
# =========================================================

st.divider()

st.caption(
    "🎓 Teacher System — Smart Attendance"
                )
