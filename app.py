import streamlit as st
import sqlite3
import hashlib
import secrets
import io
from datetime import datetime
import qrcode
import cv2
import numpy as np
import pandas as pd


# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# قاعدة بيانات جديدة تماماً
DB_FILE = "teacher_system_v2.db"


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


def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def init_db():

    conn = db()
    cur = conn.cursor()

    # إعدادات المدرس
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            teacher_password_hash TEXT NOT NULL
        )
    """)

    # الطلاب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            student_phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # الحصص
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            scanned_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # إنشاء باسورد المدرس الافتراضي
    row = cur.execute("""
        SELECT id
        FROM settings
        WHERE id = 1
    """).fetchone()

    if row is None:

        cur.execute("""
            INSERT INTO settings
            (id, teacher_password_hash)
            VALUES (?, ?)
        """, (
            1,
            hash_password("1234")
        ))

    conn.commit()
    conn.close()


# تشغيل قاعدة البيانات
init_db()


# =========================================================
# الصفوف
# =========================================================

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


# =========================================================
# المدرس - تسجيل الدخول
# =========================================================

def check_password(password):

    conn = db()

    row = conn.execute("""
        SELECT teacher_password_hash
        FROM settings
        WHERE id = 1
    """).fetchone()

    conn.close()

    if row is None:
        return False

    return (
        row["teacher_password_hash"]
        == hash_password(password)
    )


def change_password(new_password):

    conn = db()

    conn.execute("""
        UPDATE settings
        SET teacher_password_hash = ?
        WHERE id = 1
    """, (
        hash_password(new_password),
    ))

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def register_student(
    name,
    grade,
    student_phone,
    parent_phone
):

    conn = db()

    existing = conn.execute("""
        SELECT id
        FROM students
        WHERE student_phone = ?
    """, (
        student_phone.strip(),
    )).fetchone()

    if existing:

        conn.close()

        return (
            False,
            "رقم هاتف الطالب مسجل بالفعل."
        )

    conn.execute("""
        INSERT INTO students
        (
            name,
            grade,
            student_phone,
            parent_phone,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        name.strip(),
        grade,
        student_phone.strip(),
        parent_phone.strip(),
        now()
    ))

    conn.commit()
    conn.close()

    return (
        True,
        "تم تسجيل الطالب بنجاح ✅"
    )


def get_students(grade=None):

    conn = db()

    if grade:

        rows = conn.execute("""
            SELECT *
            FROM students
            WHERE grade = ?
            ORDER BY name
        """, (
            grade,
        )).fetchall()

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

def create_lesson(
    grade,
    lesson_name
):

    token = secrets.token_urlsafe(32)

    conn = db()

    # إغلاق أي حصة قديمة
    conn.execute("""
        UPDATE lessons
        SET active = 0
    """)

    cur = conn.execute("""
        INSERT INTO lessons
        (
            grade,
            lesson_name,
            token,
            active,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        grade,
        lesson_name.strip(),
        token,
        1,
        now()
    ))

    lesson_id = cur.lastrowid

    conn.commit()

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    conn.close()

    return lesson


def get_active_lesson():

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


def close_lesson():

    conn = db()

    conn.execute("""
        UPDATE lessons
        SET active = 0
    """)

    conn.commit()
    conn.close()


# =========================================================
# الحضور
# =========================================================

def mark_attendance(
    token,
    student_phone
):

    conn = db()

    # البحث عن الحصة
    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
    """, (
        token.strip(),
    )).fetchone()

    if lesson is None:

        conn.close()

        return (
            False,
            "الحصة غير موجودة أو تم إنهاؤها."
        )

    # البحث عن الطالب
    student = conn.execute("""
        SELECT *
        FROM students
        WHERE student_phone = ?
    """, (
        student_phone.strip(),
    )).fetchone()

    if student is None:

        conn.close()

        return (
            False,
            "الطالب غير مسجل. يجب التسجيل أول مرة."
        )

    # التأكد أن الطالب من نفس الصف
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "الطالب تابع لصف مختلف عن الحصة."
        )

    # التأكد أنه لم يسجل من قبل
    already = conn.execute("""
        SELECT id
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student["id"]
    )).fetchone()

    if already:

        conn.close()

        return (
            False,
            "تم تسجيل حضورك بالفعل في هذه الحصة ✅"
        )

    # تسجيل الحضور
    conn.execute("""
        INSERT INTO attendance
        (
            lesson_id,
            student_id,
            scanned_at
        )
        VALUES (?, ?, ?)
    """, (
        lesson["id"],
        student["id"],
        now()
    ))

    conn.commit()
    conn.close()

    return (
        True,
        f"تم تسجيل حضور {student['name']} ✅"
    )


def get_attendance_stats(lesson):

    conn = db()

    # إجمالي طلاب الصف
    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM students
        WHERE grade = ?
    """, (
        lesson["grade"],
    )).fetchone()["count"]

    # الحاضرين
    present = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE lesson_id = ?
    """, (
        lesson["id"],
    )).fetchone()["count"]

    # الغائبين
    absent = max(
        total - present,
        0
    )

    # الحاضرون
    present_students = conn.execute("""
        SELECT
            students.name,
            students.student_phone,
            attendance.scanned_at
        FROM attendance
        JOIN students
        ON students.id = attendance.student_id
        WHERE attendance.lesson_id = ?
        ORDER BY attendance.scanned_at
    """, (
        lesson["id"],
    )).fetchall()

    # الغائبون
    absent_students = conn.execute("""
        SELECT
            students.name,
            students.student_phone
        FROM students
        WHERE students.grade = ?
        AND students.id NOT IN (
            SELECT student_id
            FROM attendance
            WHERE lesson_id = ?
        )
        ORDER BY students.name
    """, (
        lesson["grade"],
        lesson["id"]
    )).fetchall()

    conn.close()

    return (
        total,
        present,
        absent,
        present_students,
        absent_students
    )


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

    qr.make(
        fit=True
    )

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

        data = np.frombuffer(
            uploaded_file.getvalue(),
            dtype=np.uint8
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(
            image
        )

        if text:

            return text.strip()

        return ""

    except Exception:

        return ""


# =========================================================
# صفحة الطالب 👨‍🎓
# =========================================================

def student_page():

    st.title(
        "🎓 صفحة الطالب"
    )

    st.write(
        "التسجيل أول مرة فقط، وبعد ذلك امسح QR الحصة لتسجيل حضورك."
    )

    register_tab, attendance_tab = st.tabs([
        "📝 التسجيل أول مرة",
        "📷 تسجيل الحضور"
    ])


    # =====================================================
    # تسجيل الطالب
    # =====================================================

    with register_tab:

        st.subheader(
            "📝 تسجيل الطالب لأول مرة"
        )

        st.info(
            "بعد التسجيل لن تحتاج لإعادة تسجيل بياناتك."
        )

        name = st.text_input(
            "اسم الطالب",
            key="register_name"
        )

        grade = st.selectbox(
            "الصف",
            GRADES,
            key="register_grade"
        )

        phone = st.text_input(
            "رقم هاتف الطالب",
            key="register_phone"
        )

        parent_phone = st.text_input(
            "رقم هاتف ولي الأمر",
            key="register_parent"
        )

        if st.button(
            "✅ تسجيل الطالب",
            use_container_width=True
        ):

            if not name.strip():

                st.error(
                    "اكتب اسم الطالب."
                )

            elif not phone.strip():

                st.error(
                    "اكتب رقم هاتف الطالب."
                )

            else:

                success, message = register_student(
                    name,
                    grade,
                    phone,
                    parent_phone
                )

                if success:

                    st.success(
                        message
                    )

                else:

                    st.warning(
                        message
                    )


    # =====================================================
    # حضور الطالب
    # =====================================================

    with attendance_tab:

        st.subheader(
            "📷 حضور الحصة"
        )

        phone = st.text_input(
            "رقم هاتف الطالب",
            key="attendance_phone"
        )

        st.write(
            "وجّه الكاميرا إلى QR الموجود عند المدرس."
        )

        picture = st.camera_input(
            "📷 مسح QR الحصة"
        )

        token = ""

        if picture is not None:

            token = read_qr(
                picture
            )

            if token:

                st.success(
                    "تم قراءة QR بنجاح ✅"
                )

            else:

                st.error(
                    "لم يتم قراءة QR. قرب الكاميرا من الكود."
                )

        if st.button(
            "🟢 تسجيل الحضور",
            use_container_width=True
        ):

            if not phone.strip():

                st.error(
                    "اكتب رقم هاتف الطالب."
                )

            elif not token:

                st.error(
                    "امسح QR الحصة أولاً."
                )

            else:

                success, message = mark_attendance(
                    token,
                    phone
                )

                if success:

                    st.success(
                        message
                    )

                else:

                    st.warning(
                        message
                    )

    st.divider()

    st.caption(
        "👨‍🎓 هذه صفحة الطالب فقط — لا يوجد بها دخول المدرس."
    )


# =========================================================
# صفحة المدرس 👨‍🏫
# =========================================================

def teacher_page():

    st.title(
        "👨‍🏫 لوحة تحكم المدرس"
    )

    # =====================================================
    # تسجيل الدخول
    # =====================================================

    if not st.session_state.get(
        "teacher_logged_in",
        False
    ):

        st.subheader(
            "🔐 تسجيل دخول المدرس"
        )

        password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "🔓 دخول المدرس",
            use_container_width=True
        ):

            if check_password(
                password
            ):

                st.session_state.teacher_logged_in = True

                st.rerun()

            else:

                st.error(
                    "كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية: 1234"
        )

        return


    # =====================================================
    # خروج المدرس
    # =====================================================

    if st.button(
        "🚪 تسجيل الخروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()


    st.success(
        "تم تسجيل دخول المدرس ✅"
    )


    dashboard, lessons, students_tab, settings = st.tabs([
        "📊 الرئيسية",
        "➕ إنشاء حصة",
        "👥 الطلاب",
        "⚙️ الإعدادات"
    ])


    # =====================================================
    # الرئيسية
    # =====================================================

    with dashboard:

        lesson = get_active_lesson()

        if lesson is None:

            st.info(
                "لا توجد حصة مفتوحة حالياً."
            )

        else:

            st.subheader(
                f"📚 الحصة الحالية: {lesson['lesson_name']}"
            )

            st.write(
                f"الصف: **{lesson['grade']}**"
            )

            (
                total,
                present,
                absent,
                present_students,
                absent_students
            ) = get_attendance_stats(
                lesson
            )


            # الإحصائيات
            col1, col2, col3 = st.columns(3)

            col1.metric(
                "👥 إجمالي الطلاب",
                total
            )

            col2.metric(
                "✅ الحاضرون",
                present
            )

            col3.metric(
                "❌ الغائبون",
                absent
            )


            # حالة العدد
            if total == 0:

                st.info(
                    "لا يوجد طلاب مسجلون في هذا الصف."
                )

            elif present >= total:

                st.success(
                    "🎉 العدد اكتمل — كل الطلاب حاضرون!"
                )

            else:

                st.warning(
                    f"⚠️ الحصة لم تكتمل — يوجد {absent} طالب غائب."
                )


            st.divider()


            # QR
            st.subheader(
                "📷 QR الحصة"
            )

            st.image(
                create_qr(
                    lesson["token"]
                ),
                width=300
            )

            st.success(
                "الطلاب يمسحون هذا QR من صفحة الطالب."
            )


            st.divider()


            # الحاضرون
            st.subheader(
                "✅ الطلاب الحاضرون"
            )

            if present_students:

                present_df = pd.DataFrame([
                    {
                        "الطالب": row["name"],
                        "رقم الهاتف": row["student_phone"],
                        "وقت الحضور": row["scanned_at"]
                    }
                    for row in present_students
                ])

                st.dataframe(
                    present_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "لم يحضر أي طالب حتى الآن."
                )


            # الغائبون
            st.subheader(
                "❌ الطلاب الغائبون"
            )

            if absent_students:

                absent_df = pd.DataFrame([
                    {
                        "الطالب": row["name"],
                        "رقم الهاتف": row["student_phone"]
                    }
                    for row in absent_students
                ])

                st.dataframe(
                    absent_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.success(
                    "🎉 لا يوجد طلاب غائبون."
                )


            # إنهاء الحصة
            if st.button(
                "⛔ إنهاء الحصة",
                use_container_width=True
            ):

                close_lesson()

                st.success(
                    "تم إنهاء الحصة."
                )

                st.rerun()


    # =====================================================
    # إنشاء حصة
    # =====================================================

    with lessons:

        st.subheader(
            "➕ إنشاء حصة جديدة"
        )

        grade = st.selectbox(
            "الصف",
            GRADES,
            key="lesson_grade"
        )

        lesson_name = st.text_input(
            "اسم الحصة",
            placeholder="مثال: الرياضيات - الدرس الأول"
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

                create_lesson(
                    grade,
                    lesson_name
                )

                st.success(
                    "تم إنشاء الحصة وفتحها ✅"
                )

                st.rerun()


    # =====================================================
    # الطلاب
    # =====================================================

    with students_tab:

        st.subheader(
            "👥 جميع الطلاب المسجلين"
        )

        filter_grade = st.selectbox(
            "اختار الصف",
            ["كل الصفوف"] + GRADES,
            key="filter_grade"
        )

        if filter_grade == "كل الصفوف":

            students = get_students()

        else:

            students = get_students(
                filter_grade
            )


        st.metric(
            "عدد الطلاب",
            len(students)
        )


        if students:

            students_df = pd.DataFrame([
                {
                    "الاسم": row["name"],
                    "الصف": row["grade"],
                    "رقم الطالب": row["student_phone"],
                    "رقم ولي الأمر": row["parent_phone"],
                    "تاريخ التسجيل": row["created_at"]
                }
                for row in students
            ])

            st.dataframe(
                students_df,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "لا يوجد طلاب مسجلون."
            )


    # =====================================================
    # الإعدادات
    # =====================================================

    with settings:

        st.subheader(
            "⚙️ إعدادات المدرس"
        )

        st.write(
            "🔐 تغيير كلمة مرور المدرس"
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
            "🔑 تغيير كلمة المرور",
            use_container_width=True
        ):

            if not check_password(
                old_password
            ):

                st.error(
                    "كلمة المرور الحالية غير صحيحة."
                )

            elif len(new_password) < 4:

                st.error(
                    "كلمة المرور الجديدة يجب أن تكون 4 أحرف أو أرقام على الأقل."
                )

            elif new_password != confirm_password:

                st.error(
                    "كلمتا المرور غير متطابقتين."
                )

            else:

                change_password(
                    new_password
                )

                st.success(
                    "تم تغيير كلمة مرور المدرس بنجاح ✅"
                )


# =========================================================
# اختيار الصفحة
# =========================================================

page = st.query_params.get(
    "page",
    "student"
)

if page == "teacher":

    teacher_page()

else:

    student_page()
