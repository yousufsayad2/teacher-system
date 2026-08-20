import streamlit as st
import sqlite3
import secrets
import hashlib
from datetime import datetime
from urllib.parse import urlencode
import qrcode
import io

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

DB = "teacher_system.db"
DEFAULT_PASSWORD = "123456"

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
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def init_db():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            phone TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            student_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
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

    row = cur.execute("""
        SELECT password_hash
        FROM settings
        WHERE id = 1
    """).fetchone()

    if row is None:

        cur.execute("""
            INSERT INTO settings
            (id, password_hash)
            VALUES (?, ?)
        """, (
            1,
            hash_password(DEFAULT_PASSWORD)
        ))

    conn.commit()
    conn.close()


# =========================
# PASSWORD
# =========================

def get_password_hash():

    conn = get_db()

    row = conn.execute("""
        SELECT password_hash
        FROM settings
        WHERE id = 1
    """).fetchone()

    conn.close()

    if row:
        return row["password_hash"]

    return hash_password(DEFAULT_PASSWORD)


def change_password(new_password):

    conn = get_db()

    conn.execute("""
        UPDATE settings
        SET password_hash = ?
        WHERE id = 1
    """, (
        hash_password(new_password),
    ))

    conn.commit()
    conn.close()


# =========================
# LESSONS
# =========================

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


def get_lesson(token):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token = ?
    """, (token,)).fetchone()

    conn.close()

    return row


def create_lesson(grade, lesson_name):

    conn = get_db()

    # إغلاق أي حصة قديمة
    conn.execute("""
        UPDATE lessons
        SET active = 0
        WHERE active = 1
    """)

    token = secrets.token_urlsafe(24)

    conn.execute("""
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
        lesson_name,
        token,
        1,
        datetime.now().isoformat(
            timespec="seconds"
        )
    ))

    conn.commit()
    conn.close()


def end_lesson(lesson_id):

    conn = get_db()

    conn.execute("""
        UPDATE lessons
        SET active = 0
        WHERE id = ?
    """, (
        lesson_id,
    ))

    conn.commit()
    conn.close()


# =========================
# STUDENTS
# =========================

def create_student(
    name,
    grade,
    phone,
    parent_phone
):

    token = secrets.token_urlsafe(20)

    conn = get_db()

    cur = conn.execute("""
        INSERT INTO students
        (
            name,
            grade,
            phone,
            parent_phone,
            student_token,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        grade,
        phone,
        parent_phone,
        token,
        datetime.now().isoformat(
            timespec="seconds"
        )
    ))

    conn.commit()

    student_id = cur.lastrowid

    conn.close()

    return student_id, token


def get_student(token):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM students
        WHERE student_token = ?
    """, (
        token,
    )).fetchone()

    conn.close()

    return row


def get_all_students():

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return rows


# =========================
# ATTENDANCE
# =========================

def register_attendance(
    lesson_token,
    student_token
):

    lesson = get_lesson(
        lesson_token
    )

    if lesson is None:
        return False, "الحصة غير موجودة."

    if lesson["active"] != 1:
        return False, "الحصة انتهت."

    student = get_student(
        student_token
    )

    if student is None:
        return False, "الطالب غير مسجل."

    if student["grade"] != lesson["grade"]:
        return False, (
            "الطالب مسجل في صف مختلف عن الحصة."
        )

    conn = get_db()

    try:

        conn.execute("""
            INSERT INTO attendance
            (
                lesson_id,
                student_id,
                attended_at
            )
            VALUES (?, ?, ?)
        """, (
            lesson["id"],
            student["id"],
            datetime.now().isoformat(
                timespec="seconds"
            )
        ))

        conn.commit()

        conn.close()

        return True, (
            "تم تسجيل حضورك بنجاح ✅"
        )

    except sqlite3.IntegrityError:

        conn.close()

        return True, (
            "أنت مسجل حضورك بالفعل في هذه الحصة ✅"
        )


def get_attendance_stats(lesson_id):

    conn = get_db()

    lesson = conn.execute("""
        SELECT grade
        FROM lessons
        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    if lesson is None:
        conn.close()
        return 0, 0, 0

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM students
        WHERE grade = ?
    """, (
        lesson["grade"],
    )).fetchone()["count"]

    present = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE lesson_id = ?
    """, (
        lesson_id,
    )).fetchone()["count"]

    absent = max(
        total - present,
        0
    )

    conn.close()

    return total, present, absent


def get_present_students(lesson_id):

    conn = get_db()

    rows = conn.execute("""
        SELECT
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
    """, (
        lesson_id,
    )).fetchall()

    conn.close()

    return rows


# =========================
# QR
# =========================

def create_qr(text):

    qr = qrcode.QRCode(
        version=None,
        box_size=10,
        border=4
    )

    qr.add_data(text)

    qr.make(
        fit=True
    )

    image = qr.make_image()

    output = io.BytesIO()

    image.save(
        output,
        format="PNG"
    )

    return output.getvalue()


# =========================
# LINKS
# =========================

def get_app_url():

    try:

        if "APP_URL" in st.secrets:

            return st.secrets["APP_URL"]

    except Exception:
        pass

    return (
        "https://teacher-system-2t8fcv45z3sqh8zn75s38m."
        "streamlit.app"
    )


def make_student_link(
    lesson_token=None,
    student_token=None
):

    params = {
        "mode": "student"
    }

    if lesson_token:
        params["lesson"] = lesson_token

    if student_token:
        params["student"] = student_token

    return (
        get_app_url()
        + "?"
        + urlencode(params)
    )


def make_teacher_link():

    return (
        get_app_url()
        + "?mode=teacher"
    )


# =========================
# TEACHER LOGIN
# =========================

def teacher_login():

    if st.session_state.get(
        "teacher_logged",
        False
    ):
        return True

    st.title("🎓 Teacher System")

    st.subheader(
        "🔐 دخول المدرس"
    )

    password = st.text_input(
        "كلمة المرور",
        type="password"
    )

    if st.button(
        "دخول المدرس",
        use_container_width=True
    ):

        if (
            hash_password(password)
            == get_password_hash()
        ):

            st.session_state[
                "teacher_logged"
            ] = True

            st.rerun()

        else:

            st.error(
                "كلمة المرور غير صحيحة ❌"
            )

    st.info(
        "كلمة المرور الافتراضية أول مرة: 123456"
    )

    return False


# =========================
# TEACHER PAGE
# =========================

def teacher_page():

    if not teacher_login():
        return

    st.title(
        "👨‍🏫 لوحة تحكم المدرس"
    )

    st.success(
        "🟢 تم تسجيل دخول المدرس"
    )

    if st.button(
        "🚪 تسجيل الخروج"
    ):

        st.session_state[
            "teacher_logged"
        ] = False

        st.rerun()

    st.divider()

    # =====================
    # CHANGE PASSWORD
    # =====================

    st.header(
        "🔐 تغيير كلمة مرور المدرس"
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
        "💾 تغيير كلمة المرور"
    ):

        if len(new_password) < 6:

            st.error(
                "كلمة المرور لازم تكون 6 أحرف أو أرقام على الأقل."
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
                "تم تغيير كلمة المرور بنجاح ✅"
            )

    st.divider()

    # =====================
    # CREATE LESSON
    # =====================

    st.header(
        "➕ إنشاء حصة جديدة"
    )

    col1, col2 = st.columns(2)

    with col1:

        grade = st.selectbox(
            "الصف",
            GRADES
        )

    with col2:

        lesson_name = st.text_input(
            "اسم الحصة",
            value="الحصة الحالية"
        )

    if st.button(
        "🟢 بدء الحصة",
        type="primary",
        use_container_width=True
    ):

        create_lesson(
            grade,
            lesson_name.strip()
            or "الحصة الحالية"
        )

        st.success(
            "تم إنشاء الحصة وبدأت الآن ✅"
        )

        st.rerun()

    st.divider()

    # =====================
    # ACTIVE LESSON
    # =====================

    lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "لا توجد حصة نشطة حاليًا."
        )

    else:

        st.header(
            "🟢 الحصة الحالية"
        )

        st.write(
            f"**اسم الحصة:** {lesson['lesson_name']}"
        )

        st.write(
            f"**الصف:** {lesson['grade']}"
        )

        # الإحصائيات

        total, present, absent = (
            get_attendance_stats(
                lesson["id"]
            )
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "👨‍🎓 إجمالي الطلاب",
                total
            )

        with col2:

            st.metric(
                "✅ الحاضرون",
                present
            )

        with col3:

            st.metric(
                "❌ الغائبون",
                absent
            )

        # QR

        st.subheader(
            "📱 QR الحصة"
        )

        student_link = make_student_link(
            lesson_token=lesson["token"]
        )

        qr_image = create_qr(
            student_link
        )

        st.image(
            qr_image,
            width=350
        )

        st.caption(
            "الطالب يمسح هذا الـ QR لتسجيل الحضور."
        )

        # حالة العدد

        if total == 0:

            st.info(
                "لسه مفيش طلاب مسجلين في هذا الصف."
            )

        elif present == total:

            st.success(
                "🎉 العدد اكتمل — كل الطلاب حضروا."
            )

        else:

            st.warning(
                f"⏳ يوجد {absent} طالب لم يسجل الحضور بعد."
            )

        st.divider()

        # الطلاب الحاضرين

        st.subheader(
            "👥 الطلاب الذين حضروا"
        )

        rows = get_present_students(
            lesson["id"]
        )

        if len(rows) == 0:

            st.info(
                "لم يسجل أي طالب حضور حتى الآن."
            )

        else:

            for student in rows:

                st.success(
                    f"""
                    👤 {student['name']}
                    
                    📚 {student['grade']}
                    
                    📱 رقم الطالب: {student['phone']}
                    
                    👨‍👩‍👦 رقم ولي الأمر: {student['parent_phone']}
                    
                    🕐 وقت الحضور: {student['attended_at']}
                    """
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

    st.divider()

    # =====================
    # ALL REGISTERED STUDENTS
    # =====================

    st.header(
        "📋 الطلاب المسجلون"
    )

    students = get_all_students()

    st.metric(
        "إجمالي الطلاب",
        len(students)
    )

    for student in students:

        with st.expander(
            f"👤 {student['name']} — {student['grade']}"
        ):

            st.write(
                f"📱 رقم الطالب: {student['phone']}"
            )

            st.write(
                f"👨‍👩‍👦 رقم ولي الأمر: {student['parent_phone']}"
            )


# =========================
# STUDENT PAGE
# =========================

def student_page():

    st.title(
        "🎓 تسجيل حضور الطالب"
    )

    st.info(
        "هذه صفحة الطالب فقط."
    )

    student_token = st.query_params.get(
        "student"
    )

    lesson_token = st.query_params.get(
        "lesson"
    )

    # =====================
    # EXISTING STUDENT
    # =====================

    if student_token:

        student = get_student(
            student_token
        )

        if student:

            st.success(
                f"أهلًا يا {student['name']} 👋"
            )

            st.write(
                f"📚 الصف: **{student['grade']}**"
            )

            if lesson_token:

                success, message = (
                    register_attendance(
                        lesson_token,
                        student_token
                    )
                )

                if success:

                    st.success(
                        message
                    )

                else:

                    st.error(
                        message
                    )

            else:

                st.info(
                    "امسح QR الحصة لتسجيل الحضور."
                )

            return

    # =====================
    # FIRST REGISTRATION
    # =====================

    st.header(
        "📝 التسجيل لأول مرة"
    )

    st.write(
        "اكتب بياناتك مرة واحدة فقط."
    )

    with st.form(
        "student_registration"
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
            "💾 تسجيل البيانات",
            use_container_width=True
        )

    if submit:

        if not name.strip():

            st.error(
                "اكتب اسم الطالب."
            )

        elif not phone.strip():

            st.error(
                "اكتب رقم الطالب."
            )

        elif not parent_phone.strip():

            st.error(
                "اكتب رقم ولي الأمر."
            )

        else:

            try:

                _, token = create_student(
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip()
                )

                st.success(
                    "تم تسجيل بياناتك بنجاح ✅"
                )

                url = make_student_link(
                    student_token=token
                )

                st.write(
                    "احتفظ بالرابط ده للحصص القادمة:"
                )

                st.code(
                    url
                )

                st.markdown(
                    f"[📱 فتح صفحة الطالب]({url})"
                )

            except sqlite3.IntegrityError:

                st.error(
                    "حدثت مشكلة أثناء التسجيل، حاول مرة أخرى."
                )


# =========================
# START
# =========================

init_db()

mode = st.query_params.get(
    "mode",
    "student"
)

if mode == "teacher":

    teacher_page()

else:

    student_page()
