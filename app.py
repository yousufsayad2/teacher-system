import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import hashlib
import secrets
from datetime import datetime

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

DB = "teacher_system.db"

# باسورد المدرس الافتراضي
DEFAULT_PASSWORD = "123456"


# =========================
# قاعدة البيانات
# =========================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            teacher_password TEXT NOT NULL
        )
    """)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            checkin_time TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    existing = cur.execute(
        "SELECT id FROM settings WHERE id = 1"
    ).fetchone()

    if not existing:
        cur.execute(
            "INSERT INTO settings (id, teacher_password) VALUES (1, ?)",
            (hash_password(DEFAULT_PASSWORD),)
        )

    conn.commit()
    conn.close()


init_db()


# =========================
# الصفوف
# =========================
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


# =========================
# وظائف مساعدة
# =========================
def get_setting_password():
    conn = get_conn()
    row = conn.execute(
        "SELECT teacher_password FROM settings WHERE id=1"
    ).fetchone()
    conn.close()
    return row["teacher_password"]


def set_teacher_password(password):
    conn = get_conn()
    conn.execute(
        "UPDATE settings SET teacher_password=? WHERE id=1",
        (hash_password(password),)
    )
    conn.commit()
    conn.close()


def get_student_by_code(code):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM students WHERE student_code=?",
        (code,)
    ).fetchone()
    conn.close()
    return row


def create_student(name, grade, phone, parent_phone):
    code = "ST-" + secrets.token_hex(4).upper()

    conn = get_conn()

    try:
        conn.execute("""
            INSERT INTO students
            (student_code, name, grade, phone, parent_phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            code,
            name,
            grade,
            phone,
            parent_phone,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return None

    conn.close()
    return code


def create_lesson(grade, lesson_name):
    code = "LESSON-" + secrets.token_hex(6).upper()

    conn = get_conn()

    conn.execute("""
        UPDATE lessons
        SET active=0, ended_at=?
        WHERE active=1
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

    cur = conn.execute("""
        INSERT INTO lessons
        (lesson_code, grade, lesson_name, active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (
        code,
        grade,
        lesson_name,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """, (code,)).fetchone()

    conn.close()
    return row


def record_attendance(lesson_id, student_id):
    conn = get_conn()

    existing = conn.execute("""
        SELECT id
        FROM attendance
        WHERE lesson_id=? AND student_id=?
    """, (lesson_id, student_id)).fetchone()

    if existing:
        conn.close()
        return False

    conn.execute("""
        INSERT INTO attendance
        (lesson_id, student_id, checkin_time)
        VALUES (?, ?, ?)
    """, (
        lesson_id,
        student_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """, (lesson_id,)).fetchall()

    conn.close()

    return rows


def get_students_for_grade(grade):
    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM students
        WHERE grade=?
        ORDER BY name
    """, (grade,)).fetchall()

    conn.close()

    return rows


def get_all_students():
    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return rows


def end_lesson(lesson_id):
    conn = get_conn()

    conn.execute("""
        UPDATE lessons
        SET active=0, ended_at=?
        WHERE id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        lesson_id
    ))

    conn.commit()
    conn.close()


# =========================
# QR
# =========================
def make_qr(data):
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    output = io.BytesIO()
    img.save(output, format="PNG")

    return output.getvalue()


def read_qr(uploaded_file):
    try:
        data = uploaded_file.getvalue()

        image = cv2.imdecode(
            np.frombuffer(data, np.uint8),
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(image)

        if text:
            return text.strip()

    except Exception:
        pass

    return None


# =========================
# Header
# =========================
def header():
    st.markdown(
        """
        <div style="text-align:center">
            <h1>🎓 Teacher System</h1>
            <h3>نظام إدارة المدرس والحضور الذكي</h3>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# صفحة تسجيل الطالب
# =========================
def student_page():
    header()

    st.markdown("## 🧑‍🎓 صفحة الطالب")

    # student code من الرابط
    student_code = st.query_params.get("student")

    student = None

    if student_code:
        student = get_student_by_code(student_code)

    if not student:

        st.info(
            "سجل بياناتك أول مرة فقط. بعد التسجيل احتفظ برابط الطالب الخاص بك."
        )

        with st.form("student_registration"):

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

            submitted = st.form_submit_button(
                "💾 تسجيل الطالب"
            )

        if submitted:

            if not name.strip():
                st.error("اكتب اسم الطالب.")

            elif not phone.strip():
                st.error("اكتب رقم الطالب.")

            elif not parent_phone.strip():
                st.error("اكتب رقم ولي الأمر.")

            else:

                code = create_student(
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip()
                )

                if code:

                    base_url = (
                        "https://teacher-system-2t8fcv45z3sqh8zn75s38m.streamlit.app/"
                    )

                    personal_url = (
                        base_url +
                        "?student=" +
                        code
                    )

                    st.success(
                        "تم تسجيل بياناتك بنجاح."
                    )

                    st.markdown(
                        f"""
                        ### 🔐 كود الطالب
                        **{code}**

                        احتفظ بالرابط التالي على هاتفك:

                        `{personal_url}`
                        """
                    )

                    st.info(
                        "بعد كده مش محتاج تسجل بياناتك مرة ثانية."
                    )

                    st.code(personal_url)

                else:
                    st.error(
                        "حدث خطأ أثناء التسجيل."
                    )

        return

    # =========================
    # طالب مسجل
    # =========================
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

    # لا يسمح للطالب بحضور حصة لصف مختلف
    if active["grade"] != student["grade"]:

        st.warning(
            f"الحصة الحالية للـ {active['grade']}."
        )

        st.info(
            "لا يمكنك تسجيل حضور هذه الحصة."
        )

        return

    st.success(
        f"🟢 الحصة الحالية: {active['lesson_name']}"
    )

    st.markdown(
        """
        ## 📷 تسجيل الحضور

        وجّه الكاميرا إلى QR الخاص بالحصة.
        """
    )

    picture = st.camera_input(
        "📷 تصوير QR",
        resolution="720p"
    )

    if picture:

        qr_text = read_qr(picture)

        if not qr_text:

            st.error(
                "❌ لم يتم التعرف على QR. حاول تصويره بوضوح أكبر."
            )

            return

        lesson = get_lesson_by_code(qr_text)

        if not lesson:

            st.error(
                "❌ QR غير صحيح."
            )

            return

        if not lesson["active"]:

            st.error(
                "❌ هذه الحصة انتهت."
            )

            return

        if lesson["id"] != active["id"]:

            st.error(
                "❌ هذا QR ليس للحصة الحالية."
            )

            return

        if lesson["grade"] != student["grade"]:

            st.error(
                "❌ هذه الحصة ليست للصف الخاص بك."
            )

            return

        saved = record_attendance(
            lesson["id"],
            student["id"]
        )

        if saved:

            st.success(
                f"✅ تم تسجيل حضورك يا {student['name']}"
            )

            st.balloons()

        else:

            st.info(
                "ℹ️ أنت مسجل بالفعل في هذه الحصة."
            )


# =========================
# صفحة المدرس
# =========================
def teacher_page():
    header()

    # =========================
    # تسجيل الدخول
    # =========================
    if not st.session_state.get("teacher_logged_in", False):

        st.markdown("## 👨‍🏫 دخول المدرس")

        password = st.text_input(
            "🔐 كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "دخول",
            use_container_width=True
        ):

            if hash_password(password) == get_setting_password():

                st.session_state.teacher_logged_in = True

                st.success(
                    "🟢 تم تسجيل دخول المدرس."
                )

                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية أول مرة: 123456"
        )

        return

    # =========================
    # لوحة المدرس
    # =========================
    st.success(
        "🟢 تم تسجيل دخول المدرس"
    )

    if st.button("🚪 تسجيل خروج"):

        st.session_state.teacher_logged_in = False

        st.rerun()

    st.markdown("## 👨‍🏫 لوحة تحكم المدرس")

    # =========================
    # Tabs
    # =========================
    tab1, tab2, tab3, tab4 = st.tabs([
        "➕ إنشاء حصة",
        "📊 الحصة الحالية",
        "👨‍🎓 الطلاب",
        "⚙️ الإعدادات"
    ])

    # =========================
    # إنشاء حصة
    # =========================
    with tab1:

        st.markdown("### ➕ إنشاء حصة جديدة")

        grade = st.selectbox(
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

            lesson_id, lesson_code = create_lesson(
                grade,
                lesson_name
            )

            st.success(
                "تم إنشاء الحصة."
            )

            st.rerun()

    # =========================
    # الحصة الحالية
    # =========================
    with tab2:

        active = get_active_lesson()

        if not active:

            st.warning(
                "🔴 لا توجد حصة نشطة."
            )

        else:

            st.success(
                f"🟢 {active['lesson_name']}"
            )

            st.write(
                f"**الصف:** {active['grade']}"
            )

            st.write(
                f"**بدأت:** {active['created_at']}"
            )

            qr_bytes = make_qr(
                active["lesson_code"]
            )

            st.image(
                qr_bytes,
                caption="📱 QR الخاص بالحصة"
            )

            st.download_button(
                "⬇️ تحميل QR",
                data=qr_bytes,
                file_name="lesson_qr.png",
                mime="image/png",
                use_container_width=True
            )

            st.divider()

            students = get_students_for_grade(
                active["grade"]
            )

            attendance = get_attendance(
                active["id"]
            )

            total = len(students)
            present = len(attendance)
            absent = max(total - present, 0)

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

            if total > 0 and present == total:

                st.success(
                    "🎉 العدد اكتمل — كل الطلاب سجلوا الحضور."
                )

            elif total > 0:

                st.warning(
                    f"⚠️ لسه فيه {absent} طالب لم يسجل الحضور."
                )

            st.divider()

            st.markdown(
                "### 🟢 الطلاب الذين سجلوا الحضور"
            )

            if attendance:

                for row in attendance:

                    st.write(
                        f"✅ **{row['name']}** — "
                        f"{row['student_code']} — "
                        f"{row['phone']} — "
                        f"ولي الأمر: {row['parent_phone']} — "
                        f"{row['checkin_time']}"
                    )

            else:

                st.info(
                    "لا يوجد حضور حتى الآن."
                )

            st.divider()

            st.markdown(
                "### 🔴 الطلاب الغائبون"
            )

            present_codes = {
                row["student_code"]
                for row in attendance
            }

            absent_students = [
                s for s in students
                if s["student_code"] not in present_codes
            ]

            if absent_students:

                for s in absent_students:

                    st.write(
                        f"🔴 **{s['name']}** — "
                        f"{s['student_code']} — "
                        f"{s['phone']} — "
                        f"ولي الأمر: {s['parent_phone']}"
                    )

            else:

                if total > 0:

                    st.success(
                        "لا يوجد غياب."
                    )

            st.divider()

            if st.button(
                "🔴 إنهاء الحصة",
                use_container_width=True
            ):

                end_lesson(active["id"])

                st.success(
                    "تم إنهاء الحصة."
                )

                st.rerun()

    # =========================
    # الطلاب
    # =========================
    with tab3:

        st.markdown(
            "### 👨‍🎓 جميع الطلاب المسجلين"
        )

        students = get_all_students()

        st.metric(
            "إجمالي الطلاب",
            len(students)
        )

        if students:

            for s in students:

                with st.expander(
                    f"👨‍🎓 {s['name']} — {s['grade']}"
                ):

                    st.write(
                        f"**كود الطالب:** {s['student_code']}"
                    )

                    st.write(
                        f"**رقم الطالب:** {s['phone']}"
                    )

                    st.write(
                        f"**رقم ولي الأمر:** {s['parent_phone']}"
                    )

                    st.write(
                        f"**تاريخ التسجيل:** {s['created_at']}"
                    )

        else:

            st.info(
                "لا يوجد طلاب مسجلون."
            )

    # =========================
    # الإعدادات
    # =========================
    with tab4:

        st.markdown(
            "### ⚙️ إعدادات المدرس"
        )

        st.markdown(
            "#### 🔐 تغيير كلمة المرور"
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
            "🔄 تغيير كلمة المرور"
        ):

            if hash_password(old_password) != get_setting_password():

                st.error(
                    "❌ كلمة المرور الحالية غير صحيحة."
                )

            elif len(new_password) < 4:

                st.error(
                    "❌ كلمة المرور الجديدة قصيرة."
                )

            elif new_password != confirm_password:

                st.error(
                    "❌ كلمتا المرور غير متطابقتين."
                )

            else:

                set_teacher_password(
                    new_password
                )

                st.success(
                    "✅ تم تغيير كلمة المرور."
                )


# =========================
# تحديد الصفحة
# =========================
params = st.query_params

page = params.get("page", "")

if page == "teacher":

    teacher_page()

else:

    student_page()
