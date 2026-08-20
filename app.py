import streamlit as st
import sqlite3
import hashlib
import secrets
import io
from datetime import datetime
from urllib.parse import urlencode

import qrcode
import cv2
import numpy as np


# =========================================================
# إعداد التطبيق
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)


# =========================================================
# إعدادات عامة
# =========================================================

DB = "teacher_system.db"

DEFAULT_PASSWORD = "123456"

APP_URL = "https://teacher-system-2t8fcv45z3sqh8zn75s38m.streamlit.app/"


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
# قاعدة البيانات
# =========================================================

def connect():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = connect()

    cursor = conn.cursor()

    # -----------------------------------------
    # إعدادات النظام
    # -----------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # -----------------------------------------
    # الطلاب
    # -----------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            token TEXT UNIQUE NOT NULL,

            name TEXT NOT NULL,

            grade TEXT NOT NULL,

            phone TEXT NOT NULL,

            guardian_phone TEXT NOT NULL,

            created_at TEXT NOT NULL
        )
    """)

    # -----------------------------------------
    # الحصص
    # -----------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            lesson_token TEXT UNIQUE NOT NULL,

            grade TEXT NOT NULL,

            title TEXT NOT NULL,

            started_at TEXT NOT NULL,

            ended_at TEXT,

            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    # -----------------------------------------
    # الحضور
    # -----------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            lesson_id INTEGER NOT NULL,

            student_id INTEGER NOT NULL,

            attended_at TEXT NOT NULL,

            UNIQUE(lesson_id, student_id),

            FOREIGN KEY(lesson_id)
                REFERENCES lessons(id),

            FOREIGN KEY(student_id)
                REFERENCES students(id)
        )
    """)

    # -----------------------------------------
    # إنشاء باسورد المدرس لو أول مرة
    # -----------------------------------------

    password_row = cursor.execute("""
        SELECT value
        FROM settings
        WHERE key = 'teacher_password'
    """).fetchone()

    if password_row is None:

        hashed = hash_password(DEFAULT_PASSWORD)

        cursor.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
        """, (
            "teacher_password",
            hashed
        ))

    conn.commit()

    conn.close()


# =========================================================
# أدوات مساعدة
# =========================================================

def hash_password(password):

    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def current_time():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_setting(key):

    conn = connect()

    row = conn.execute("""
        SELECT value
        FROM settings
        WHERE key = ?
    """, (key,)).fetchone()

    conn.close()

    if row:
        return row["value"]

    return None


def save_setting(key, value):

    conn = connect()

    conn.execute("""
        INSERT INTO settings(key, value)
        VALUES(?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (
        key,
        value
    ))

    conn.commit()

    conn.close()


# =========================================================
# إنشاء QR
# =========================================================

def generate_qr(data):

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

    return buffer.getvalue()


# =========================================================
# قراءة QR بالكاميرا
# =========================================================

def read_qr(uploaded_file):

    if uploaded_file is None:
        return None

    try:

        data = uploaded_file.getvalue()

        array = np.frombuffer(
            data,
            np.uint8
        )

        image = cv2.imdecode(
            array,
            cv2.IMREAD_COLOR
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        decoded_text, points, _ = detector.detectAndDecode(
            image
        )

        if decoded_text:

            return decoded_text.strip()

    except Exception:

        return None

    return None


# =========================================================
# روابط النظام
# =========================================================

def make_student_url(student_token):

    return (
        APP_URL
        + "?"
        + urlencode({
            "student": student_token
        })
    )


def make_lesson_url(lesson_token):

    return (
        APP_URL
        + "?"
        + urlencode({
            "lesson": lesson_token
        })
    )


# =========================================================
# تشغيل قاعدة البيانات
# =========================================================

init_database()


# =========================================================
# قراءة الرابط
# =========================================================

params = st.query_params

student_token = params.get(
    "student"
)

teacher_mode = (
    params.get("teacher") == "1"
)


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    st.title("🎓 Teacher System")

    st.subheader(
        "🔐 دخول المدرس"
    )

    password = st.text_input(
        "كلمة مرور المدرس",
        type="password"
    )

    if st.button(
        "دخول",
        type="primary"
    ):

        saved_password = get_setting(
            "teacher_password"
        )

        if (
            saved_password
            and hash_password(password)
            == saved_password
        ):

            st.session_state[
                "teacher_logged"
            ] = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.info(
        "كلمة المرور الافتراضية أول مرة: 123456"
    )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    st.title(
        "👨‍🏫 لوحة تحكم المدرس"
    )

    # -----------------------------------------
    # تسجيل خروج
    # -----------------------------------------

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state[
            "teacher_logged"
        ] = False

        st.rerun()

    conn = connect()

    # -----------------------------------------
    # إجمالي الطلاب
    # -----------------------------------------

    total_students = conn.execute("""
        SELECT COUNT(*) AS count
        FROM students
    """).fetchone()["count"]

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
        total_students
    )

    st.divider()

    # =====================================================
    # الحصة
    # =====================================================

    st.subheader(
        "📚 إدارة الحصة"
    )

    active_lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    # =====================================================
    # لو فيه حصة شغالة
    # =====================================================

    if active_lesson:

        lesson_id = active_lesson["id"]

        lesson_grade = active_lesson["grade"]

        lesson_title = active_lesson["title"]

        st.success(
            f"🟢 الحصة الحالية: {lesson_title}"
        )

        st.write(
            f"📚 الصف: {lesson_grade}"
        )

        st.write(
            f"🕐 بدأت: {active_lesson['started_at']}"
        )

        # -----------------------------------------
        # عدد طلاب الصف
        # -----------------------------------------

        class_total = conn.execute("""
            SELECT COUNT(*) AS count
            FROM students
            WHERE grade = ?
        """, (
            lesson_grade,
        )).fetchone()["count"]

        # -----------------------------------------
        # عدد الحاضرين
        # -----------------------------------------

        present_count = conn.execute("""
            SELECT COUNT(*) AS count
            FROM attendance
            WHERE lesson_id = ?
        """, (
            lesson_id,
        )).fetchone()["count"]

        # -----------------------------------------
        # الغياب الحالي
        # -----------------------------------------

        absent_count = max(
            class_total - present_count,
            0
        )

        # -----------------------------------------
        # الإحصائيات
        # -----------------------------------------

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "🟢 الحاضر",
                present_count
            )

        with col2:

            st.metric(
                "🔴 الغائب",
                absent_count
            )

        with col3:

            st.metric(
                "👥 إجمالي الصف",
                class_total
            )

        st.divider()

        # =================================================
        # حالة الحضور
        # =================================================

        if class_total == 0:

            st.warning(
                "⚠️ لا يوجد طلاب مسجلين في هذا الصف."
            )

        elif present_count == class_total:

            st.success(
                "🎉 العدد اكتمل — كل طلاب الصف حضروا."
            )

        else:

            st.warning(
                f"⚠️ متبقي {absent_count} طالب لم يسجلوا الحضور."
            )

        # =================================================
        # QR الحصة
        # =================================================

        st.subheader(
            "📱 QR الخاص بالحصة"
        )

        qr_data = make_lesson_url(
            active_lesson["lesson_token"]
        )

        qr_image = generate_qr(
            qr_data
        )

        st.image(
            qr_image,
            width=350
        )

        st.caption(
            "الطلاب يمسحون هذا الـQR من صفحة الطالب."
        )

        # =================================================
        # جدول الحضور
        # =================================================

        st.subheader(
            "👨‍🎓 الطلاب الذين سجلوا الحضور"
        )

        attendance_rows = conn.execute("""
            SELECT
                students.name,
                students.grade,
                students.phone,
                students.guardian_phone,
                attendance.attended_at

            FROM attendance

            INNER JOIN students
                ON students.id =
                   attendance.student_id

            WHERE attendance.lesson_id = ?

            ORDER BY attendance.attended_at ASC
        """, (
            lesson_id,
        )).fetchall()

        if attendance_rows:

            attendance_data = []

            for row in attendance_rows:

                attendance_data.append({
                    "اسم الطالب": row["name"],
                    "الصف": row["grade"],
                    "رقم الطالب": row["phone"],
                    "رقم ولي الأمر": row["guardian_phone"],
                    "وقت الحضور": row["attended_at"],
                })

            st.dataframe(
                attendance_data,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "لم يسجل أي طالب الحضور حتى الآن."
            )

        # =================================================
        # إنهاء الحصة
        # =================================================

        st.divider()

        if st.button(
            "🔴 إنهاء الحصة وحساب الغياب النهائي",
            type="primary"
        ):

            conn.execute("""
                UPDATE lessons

                SET
                    active = 0,
                    ended_at = ?

                WHERE id = ?
            """, (
                current_time(),
                lesson_id
            ))

            conn.commit()

            conn.close()

            st.success(
                f"✅ انتهت الحصة. الحاضر: {present_count} — الغائب: {absent_count}"
            )

            st.rerun()

    # =====================================================
    # لا توجد حصة
    # =====================================================

    else:

        st.info(
            "🔵 لا توجد حصة نشطة حاليًا."
        )

        st.subheader(
            "➕ إنشاء حصة جديدة"
        )

        lesson_grade = st.selectbox(
            "اختر الصف",
            GRADES
        )

        lesson_title = st.text_input(
            "اسم الحصة",
            value="الحصة الحالية"
        )

        if st.button(
            "🟢 بدء الحصة",
            type="primary"
        ):

            lesson_token = secrets.token_urlsafe(
                24
            )

            conn.execute("""
                INSERT INTO lessons(
                    lesson_token,
                    grade,
                    title,
                    started_at,
                    active
                )

                VALUES(
                    ?, ?, ?, ?, 1
                )
            """, (
                lesson_token,
                lesson_grade,
                lesson_title,
                current_time()
            ))

            conn.commit()

            conn.close()

            st.success(
                "✅ تم إنشاء الحصة."
            )

            st.rerun()

    # =====================================================
    # الطلاب المسجلون
    # =====================================================

    st.divider()

    st.subheader(
        "👨‍🎓 جميع الطلاب المسجلين"
    )

    students = conn.execute("""
        SELECT
            name,
            grade,
            phone,
            guardian_phone,
            created_at

        FROM students

        ORDER BY grade, name
    """).fetchall()

    if students:

        students_data = []

        for student in students:

            students_data.append({
                "اسم الطالب": student["name"],
                "الصف": student["grade"],
                "رقم الطالب": student["phone"],
                "رقم ولي الأمر": student["guardian_phone"],
                "تاريخ التسجيل": student["created_at"],
            })

        st.dataframe(
            students_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )

    # =====================================================
    # تغيير باسورد المدرس
    # =====================================================

    st.divider()

    st.subheader(
        "🔑 تغيير كلمة مرور المدرس"
    )

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

    if st.button(
        "💾 تغيير كلمة المرور"
    ):

        saved_password = get_setting(
            "teacher_password"
        )

        if (
            hash_password(old_password)
            != saved_password
        ):

            st.error(
                "❌ كلمة المرور الحالية غير صحيحة."
            )

        elif len(new_password) < 4:

            st.error(
                "❌ كلمة المرور لازم تكون 4 أحرف/أرقام على الأقل."
            )

        elif new_password != confirm_password:

            st.error(
                "❌ تأكيد كلمة المرور غير مطابق."
            )

        else:

            save_setting(
                "teacher_password",
                hash_password(new_password)
            )

            st.success(
                "✅ تم تغيير كلمة المرور بنجاح."
            )

    conn.close()


# =========================================================
# صفحة الطالب
# =========================================================

def student_page(student_token):

    st.title(
        "🎓 Teacher System"
    )

    # =====================================================
    # التسجيل لأول مرة
    # =====================================================

    if not student_token:

        st.header(
            "📝 تسجيل الطالب لأول مرة"
        )

        st.info(
            "سجل بياناتك مرة واحدة فقط. "
            "بعد ذلك سيظهر لك رابط خاص تستخدمه في كل حصة."
        )

        with st.form(
            "student_registration"
        ):

            student_name = st.text_input(
                "👤 اسم الطالب بالكامل"
            )

            student_grade = st.selectbox(
                "📚 الصف",
                GRADES
            )

            student_phone = st.text_input(
                "📱 رقم الطالب"
            )

            guardian_phone = st.text_input(
                "👨‍👩‍👦 رقم ولي الأمر"
            )

            register = st.form_submit_button(
                "✅ تسجيل الطالب"
            )

        if register:

            student_name = student_name.strip()

            student_phone = student_phone.strip()

            guardian_phone = guardian_phone.strip()

            if not student_name:

                st.error(
                    "❌ اكتب اسم الطالب."
                )

                return

            if not student_phone:

                st.error(
                    "❌ اكتب رقم الطالب."
                )

                return

            if not guardian_phone:

                st.error(
                    "❌ اكتب رقم ولي الأمر."
                )

                return

            conn = connect()

            existing = conn.execute("""
                SELECT id
                FROM students
                WHERE phone = ?
            """, (
                student_phone,
            )).fetchone()

            if existing:

                st.error(
                    "❌ هذا الرقم مسجل بالفعل."
                )

                conn.close()

                return

            # -----------------------------------------
            # إنشاء توكن خاص بالطالب
            # -----------------------------------------

            token = secrets.token_urlsafe(
                32
            )

            conn.execute("""
                INSERT INTO students(
                    token,
                    name,
                    grade,
                    phone,
                    guardian_phone,
                    created_at
                )

                VALUES(
                    ?, ?, ?, ?, ?, ?
                )
            """, (
                token,
                student_name,
                student_grade,
                student_phone,
                guardian_phone,
                current_time()
            ))

            conn.commit()

            conn.close()

            personal_url = make_student_url(
                token
            )

            st.success(
                "🎉 تم تسجيل بياناتك بنجاح!"
            )

            st.subheader(
                "📱 مهم جدًا"
            )

            st.write(
                "احفظ الرابط ده على شاشة الموبايل. "
                "بعد كده كل حصة افتحه واضغط الكاميرا وامسح QR المدرس فقط."
            )

            st.code(
                personal_url
            )

            st.link_button(
                "📱 فتح صفحة الطالب",
                personal_url
            )

            st.warning(
                "⚠️ لا تشارك رابط الطالب الخاص بك مع شخص آخر."
            )

        return

    # =====================================================
    # البحث عن الطالب
    # =====================================================

    conn = connect()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE token = ?
    """, (
        student_token,
    )).fetchone()

    if student is None:

        conn.close()

        st.error(
            "❌ رابط الطالب غير صحيح."
        )

        return

    # =====================================================
    # بيانات الطالب
    # =====================================================

    st.success(
        f"👋 أهلاً {student['name']}"
    )

    st.write(
        f"📚 الصف: {student['grade']}"
    )

    st.info(
        "هذه صفحة الطالب فقط — لا توجد لوحة المدرس هنا."
    )

    # =====================================================
    # الحصة الحالية
    # =====================================================

    active_lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if active_lesson is None:

        conn.close()

        st.warning(
            "🟡 لا توجد حصة نشطة حاليًا."
        )

        return

    # =====================================================
    # التأكد أن الحصة للصف الصحيح
    # =====================================================

    if active_lesson["grade"] != student["grade"]:

        conn.close()

        st.error(
            "❌ الحصة الحالية ليست خاصة بصفك."
        )

        return

    st.header(
        "📷 تسجيل الحضور"
    )

    st.success(
        f"🟢 الحصة الحالية: {active_lesson['title']}"
    )

    st.write(
        f"📚 الصف: {active_lesson['grade']}"
    )

    st.write(
        "وجّه الكاميرا إلى QR الموجود عند المدرس."
    )

    # =====================================================
    # الكاميرا
    # =====================================================

    picture = st.camera_input(
        "📷 امسح QR الحصة",
        key="student_qr_camera",
        resolution="720p"
    )

    # =====================================================
    # معالجة QR
    # =====================================================

    if picture:

        qr_result = read_qr(
            picture
        )

        if not qr_result:

            st.error(
                "❌ لم أستطع قراءة QR. "
                "قرب الكاميرا من الكود وحاول مرة أخرى."
            )

        else:

            correct_qr = make_lesson_url(
                active_lesson["lesson_token"]
            )

            # -----------------------------------------
            # التأكد من أن QR للحصة الحالية
            # -----------------------------------------

            if qr_result != correct_qr:

                st.error(
                    "❌ QR غير صحيح أو خاص بحصة أخرى."
                )

            else:

                # -----------------------------------------
                # هل الطالب حضر بالفعل؟
                # -----------------------------------------

                already_attended = conn.execute("""
                    SELECT id

                    FROM attendance

                    WHERE lesson_id = ?

                    AND student_id = ?
                """, (
                    active_lesson["id"],
                    student["id"]
                )).fetchone()

                if already_attended:

                    st.warning(
                        "⚠️ أنت مسجل حضور بالفعل في هذه الحصة."
                    )

                else:

                    # -----------------------------------------
                    # تسجيل الحضور
                    # -----------------------------------------

                    conn.execute("""
                        INSERT INTO attendance(
                            lesson_id,
                            student_id,
                            attended_at
                        )

                        VALUES(
                            ?, ?, ?
                        )
                    """, (
                        active_lesson["id"],
                        student["id"],
                        current_time()
                    ))

                    conn.commit()

                    st.success(
                        "✅ تم تسجيل حضورك بنجاح!"
                    )

                    st.balloons()

                    st.info(
                        "👨‍🏫 تم إرسال حضورك إلى لوحة المدرس."
                    )

    conn.close()


# =========================================================
# التوجيه بين المدرس والطالب
# =========================================================

if teacher_mode:

    if st.session_state.get(
        "teacher_logged",
        False
    ):

        teacher_dashboard()

    else:

        teacher_login()

else:

    student_page(
        student_token
    )


# =========================================================
# نهاية التطبيق
# =========================================================

st.caption(
    "Teacher System • Smart QR Attendance"
            )
