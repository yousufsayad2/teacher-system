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
# إعداد التطبيق
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

# قاعدة بيانات جديدة تمامًا
DB = "teacher_system_v2.db"

DEFAULT_PASSWORD = "123456"

BASE_URL = "https://teacher-system-2t8fcv45z3sqh8zn75s38m.streamlit.app/"


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
# قاعدة البيانات
# =========================================================

def get_conn():
    conn = sqlite3.connect(
        DB,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_conn()
    cur = conn.cursor()

    # إعدادات المدرس
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            teacher_password TEXT NOT NULL
        )
    """)

    # الطلاب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT UNIQUE NOT NULL,
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
            lesson_code TEXT UNIQUE NOT NULL,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            ended_at TEXT
        )
    """)

    # الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            checkin_time TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # كلمة مرور افتراضية
    row = cur.execute("""
        SELECT id
        FROM settings
        WHERE id=1
    """).fetchone()

    if row is None:

        cur.execute("""
            INSERT INTO settings
            (id, teacher_password)
            VALUES (1, ?)
        """, (
            hash_password(DEFAULT_PASSWORD),
        ))

    conn.commit()
    conn.close()


# =========================================================
# كلمة المرور
# =========================================================

def hash_password(password):

    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def get_teacher_password():

    conn = get_conn()

    row = conn.execute("""
        SELECT teacher_password
        FROM settings
        WHERE id=1
    """).fetchone()

    conn.close()

    return row["teacher_password"]


def change_teacher_password(new_password):

    conn = get_conn()

    conn.execute("""
        UPDATE settings
        SET teacher_password=?
        WHERE id=1
    """, (
        hash_password(new_password),
    ))

    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def create_student(
    name,
    grade,
    phone,
    parent_phone
):

    code = "ST-" + secrets.token_hex(5).upper()

    conn = get_conn()

    try:

        conn.execute("""
            INSERT INTO students
            (
                student_code,
                name,
                grade,
                phone,
                parent_phone,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            code,
            name,
            grade,
            phone,
            parent_phone,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        conn.commit()
        conn.close()

        return code

    except Exception:

        conn.close()

        return None


def get_student(code):

    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM students
        WHERE student_code=?
    """, (
        code,
    )).fetchone()

    conn.close()

    return row


def get_all_students():

    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return rows


def get_students_by_grade(grade):

    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM students
        WHERE grade=?
        ORDER BY name
    """, (
        grade,
    )).fetchall()

    conn.close()

    return rows


# =========================================================
# الحصص
# =========================================================

def create_lesson(
    grade,
    lesson_name
):

    code = "LESSON-" + secrets.token_hex(6).upper()

    conn = get_conn()

    # إغلاق أي حصة قديمة
    conn.execute("""
        UPDATE lessons
        SET active=0,
            ended_at=?
        WHERE active=1
    """, (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    ))

    cur = conn.execute("""
        INSERT INTO lessons
        (
            lesson_code,
            grade,
            lesson_name,
            active,
            created_at
        )
        VALUES (?, ?, ?, 1, ?)
    """, (
        code,
        grade,
        lesson_name,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id, code


def get_active_lesson():

    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active=1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return row


def get_lesson_by_code(code):

    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE lesson_code=?
    """, (
        code,
    )).fetchone()

    conn.close()

    return row


def end_lesson(lesson_id):

    conn = get_conn()

    conn.execute("""
        UPDATE lessons
        SET active=0,
            ended_at=?
        WHERE id=?
    """, (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        lesson_id
    ))

    conn.commit()
    conn.close()


# =========================================================
# الحضور
# =========================================================

def record_attendance(
    lesson_id,
    student_id
):

    conn = get_conn()

    exists = conn.execute("""
        SELECT id
        FROM attendance
        WHERE lesson_id=?
        AND student_id=?
    """, (
        lesson_id,
        student_id
    )).fetchone()

    if exists:

        conn.close()

        return False

    conn.execute("""
        INSERT INTO attendance
        (
            lesson_id,
            student_id,
            checkin_time
        )
        VALUES (?, ?, ?)
    """, (
        lesson_id,
        student_id,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()
    conn.close()

    return True


def get_attendance(lesson_id):

    conn = get_conn()

    rows = conn.execute("""
        SELECT
            s.name,
            s.student_code,
            s.grade,
            s.phone,
            s.parent_phone,
            a.checkin_time
        FROM attendance a
        JOIN students s
        ON s.id = a.student_id
        WHERE a.lesson_id=?
        ORDER BY a.id DESC
    """, (
        lesson_id,
    )).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def create_qr(data):

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(data)
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

    return output.getvalue()


def read_qr(uploaded_file):

    try:

        data = uploaded_file.getvalue()

        image = cv2.imdecode(
            np.frombuffer(
                data,
                np.uint8
            ),
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(
            image
        )

        if text:

            return text.strip()

    except Exception:

        return None

    return None


# =========================================================
# الهيدر
# =========================================================

def show_header():

    st.markdown(
        """
        <div style="text-align:center">

        <h1 style="font-size:55px;">
        🎓 Teacher System
        </h1>

        <h3>
        نظام إدارة المدرس والحضور الذكي
        </h3>

        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# صفحة تسجيل الطالب
# =========================================================

def student_registration():

    show_header()

    st.markdown(
        "## 🧑‍🎓 تسجيل الطالب"
    )

    st.info(
        "سجل بياناتك أول مرة فقط. "
        "بعد التسجيل احتفظ برابطك الخاص."
    )

    with st.form(
        "student_register"
    ):

        name = st.text_input(
            "اسم الطالب بالكامل"
        )

        grade = st.selectbox(
            "الصف",
            GRADES
        )

        phone = st.text_input(
            "رقم الطالب"
        )

        parent_phone = st.text_input(
            "رقم ولي الأمر"
        )

        submit = st.form_submit_button(
            "💾 تسجيل البيانات"
        )

    if submit:

        if not name.strip():

            st.error(
                "اكتب اسم الطالب."
            )

            return

        if not phone.strip():

            st.error(
                "اكتب رقم الطالب."
            )

            return

        if not parent_phone.strip():

            st.error(
                "اكتب رقم ولي الأمر."
            )

            return

        code = create_student(
            name.strip(),
            grade,
            phone.strip(),
            parent_phone.strip()
        )

        if code:

            personal_url = (
                BASE_URL +
                "?student=" +
                code
            )

            st.success(
                "✅ تم تسجيل الطالب بنجاح."
            )

            st.markdown(
                "### 🔐 بيانات الطالب"
            )

            st.write(
                "اسم الطالب:",
                name
            )

            st.write(
                "الصف:",
                grade
            )

            st.write(
                "كود الطالب:",
                code
            )

            st.markdown(
                "### 🔗 رابط الطالب الخاص"
            )

            st.code(
                personal_url
            )

            st.warning(
                "احتفظ بالرابط على هاتف الطالب."
            )

        else:

            st.error(
                "حدث خطأ أثناء التسجيل."
            )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    show_header()

    student_code = st.query_params.get(
        "student"
    )

    # الطالب جديد
    if not student_code:

        student_registration()

        return

    student = get_student(
        student_code
    )

    if not student:

        st.error(
            "❌ الطالب غير موجود."
        )

        student_registration()

        return

    st.success(
        f"أهلاً يا {student['name']} 👋"
    )

    st.write(
        f"**الصف:** {student['grade']}"
    )

    st.write(
        f"**كود الطالب:** {student['student_code']}"
    )

    st.divider()

    active = get_active_lesson()

    if not active:

        st.warning(
            "🔴 لا توجد حصة نشطة حالياً."
        )

        return

    if active["grade"] != student["grade"]:

        st.warning(
            "⚠️ الحصة الحالية ليست لصفك."
        )

        return

    st.success(
        f"🟢 الحصة الحالية: "
        f"{active['lesson_name']}"
    )

    st.markdown(
        "## 📷 تسجيل الحضور"
    )

    st.info(
        "وجّه كاميرا الهاتف إلى QR الخاص بالحصة."
    )

    camera = st.camera_input(
        "📷 تصوير QR"
    )

    if not camera:

        return

    qr_code = read_qr(
        camera
    )

    if not qr_code:

        st.error(
            "❌ لم يتم قراءة QR."
        )

        return

    lesson = get_lesson_by_code(
        qr_code
    )

    if not lesson:

        st.error(
            "❌ QR غير صحيح."
        )

        return

    if not lesson["active"]:

        st.error(
            "❌ الحصة انتهت."
        )

        return

    if lesson["id"] != active["id"]:

        st.error(
            "❌ هذا QR ليس للحصة الحالية."
        )

        return

    if lesson["grade"] != student["grade"]:

        st.error(
            "❌ هذه الحصة ليست لصفك."
        )

        return

    saved = record_attendance(
        lesson["id"],
        student["id"]
    )

    if saved:

        st.success(
            f"🎉 تم تسجيل حضورك يا "
            f"{student['name']}"
        )

        st.balloons()

    else:

        st.info(
            "ℹ️ حضورك مسجل بالفعل."
        )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_page():

    show_header()

    # تسجيل الدخول
    if not st.session_state.get(
        "teacher_logged_in",
        False
    ):

        st.markdown(
            "## 👨‍🏫 دخول المدرس"
        )

        password = st.text_input(
            "🔐 كلمة المرور",
            type="password"
        )

        if st.button(
            "دخول",
            use_container_width=True
        ):

            if (
                hash_password(password)
                ==
                get_teacher_password()
            ):

                st.session_state.teacher_logged_in = True

                st.success(
                    "✅ تم الدخول."
                )

                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية: 123456"
        )

        return

    # لوحة التحكم
    st.markdown(
        "## 👨‍🏫 لوحة تحكم المدرس"
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "⚙️ الإعدادات"
        ]
    )

    # =====================================================
    # إنشاء حصة
    # =====================================================

    with tab1:

        st.markdown(
            "### ➕ إنشاء حصة جديدة"
        )

        grade = st.selectbox(
            "الصف",
            GRADES,
            key="new_lesson_grade"
        )

        lesson_name = st.text_input(
            "اسم الحصة",
            value="الحصة الحالية"
        )

        if st.button(
            "🟢 بدء الحصة",
            use_container_width=True
        ):

            create_lesson(
                grade,
                lesson_name
            )

            st.success(
                "🎉 تم بدء الحصة."
            )

            st.rerun()

    # =====================================================
    # الحصة الحالية
    # =====================================================

    with tab2:

        lesson = get_active_lesson()

        if not lesson:

            st.warning(
                "🔴 لا توجد حصة نشطة."
            )

        else:

            st.success(
                f"🟢 {lesson['lesson_name']}"
            )

            st.write(
                f"الصف: **{lesson['grade']}**"
            )

            st.write(
                f"وقت البداية: **{lesson['created_at']}**"
            )

            st.divider()

            # QR
            qr_image = create_qr(
                lesson["lesson_code"]
            )

            st.markdown(
                "## 📱 QR الخاص بالحصة"
            )

            st.image(
                qr_image
            )

            st.download_button(
                "⬇️ تحميل QR",
                data=qr_image,
                file_name="lesson_qr.png",
                mime="image/png",
                use_container_width=True
            )

            st.divider()

            students = get_students_by_grade(
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

            # الإحصائيات
            c1, c2, c3 = st.columns(3)

            c1.metric(
                "👨‍🎓 إجمالي الطلاب",
                total
            )

            c2.metric(
                "🟢 الحاضرون",
                present
            )

            c3.metric(
                "🔴 الغائبون",
                absent
            )

            # حالة العدد
            if total == 0:

                st.info(
                    "لا يوجد طلاب مسجلون لهذا الصف."
                )

            elif present == total:

                st.success(
                    "🎉 العدد اكتمل — كل الطلاب حضروا."
                )

            else:

                st.warning(
                    f"⚠️ باقي {absent} طالب لم يسجل الحضور."
                )

            st.divider()

            # الحاضرون
            st.markdown(
                "## 🟢 الحاضرون"
            )

            if attendance:

                for row in attendance:

                    st.success(
                        f"✅ {row['name']} | "
                        f"{row['phone']} | "
                        f"ولي الأمر: {row['parent_phone']} | "
                        f"{row['checkin_time']}"
                    )

            else:

                st.info(
                    "لم يسجل أحد الحضور حتى الآن."
                )

            st.divider()

            # الغائبون
            st.markdown(
                "## 🔴 الغائبون"
            )

            present_codes = {
                row["student_code"]
                for row in attendance
            }

            absent_students = [
                student
                for student in students
                if student["student_code"]
                not in present_codes
            ]

            if absent_students:

                for student in absent_students:

                    st.error(
                        f"🔴 {student['name']} | "
                        f"{student['phone']} | "
                        f"ولي الأمر: "
                        f"{student['parent_phone']}"
                    )

            else:

                if total > 0:

                    st.success(
                        "🎉 لا يوجد غياب."
                    )

            st.divider()

            if st.button(
                "🔴 إنهاء الحصة",
                use_container_width=True
            ):

                end_lesson(
                    lesson["id"]
                )

                st.success(
                    "تم إنهاء الحصة."
                )

                st.rerun()

    # =====================================================
    # الطلاب
    # =====================================================

    with tab3:

        st.markdown(
            "## 👨‍🎓 الطلاب المسجلون"
        )

        students = get_all_students()

        st.metric(
            "إجمالي الطلاب",
            len(students)
        )

        if students:

            for student in students:

                with st.expander(
                    f"👨‍🎓 {student['name']} — "
                    f"{student['grade']}"
                ):

                    st.write(
                        f"كود الطالب: "
                        f"**{student['student_code']}**"
                    )

                    st.write(
                        f"رقم الطالب: "
                        f"**{student['phone']}**"
                    )

                    st.write(
                        f"رقم ولي الأمر: "
                        f"**{student['parent_phone']}**"
                    )

                    personal_url = (
                        BASE_URL +
                        "?student=" +
                        student["student_code"]
                    )

                    st.code(
                        personal_url
                    )

        else:

            st.info(
                "لا يوجد طلاب حتى الآن."
            )

    # =====================================================
    # الإعدادات
    # =====================================================

    with tab4:

        st.markdown(
            "## ⚙️ إعدادات المدرس"
        )

        st.markdown(
            "### 🔐 تغيير كلمة المرور"
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
            "تأكيد كلمة المرور",
            type="password"
        )

        if st.button(
            "🔄 تغيير كلمة المرور"
        ):

            if (
                hash_password(old_password)
                !=
                get_teacher_password()
            ):

                st.error(
                    "❌ كلمة المرور الحالية غير صحيحة."
                )

            elif len(new_password) < 4:

                st.error(
                    "❌ كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل."
                )

            elif new_password != confirm_password:

                st.error(
                    "❌ تأكيد كلمة المرور غير مطابق."
                )

            else:

                change_teacher_password(
                    new_password
                )

                st.success(
                    "✅ تم تغيير كلمة المرور بنجاح."
                )


# =========================================================
# تشغيل قاعدة البيانات
# =========================================================

init_db()


# =========================================================
# تحديد الصفحة
# =========================================================

page = st.query_params.get(
    "page",
    ""
)

if page == "teacher":

    # رابط المدرس فقط
    teacher_page()

else:

    # الرابط العادي = الطالب فقط
    student_page()
