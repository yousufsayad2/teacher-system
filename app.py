import streamlit as st
import sqlite3
import hashlib


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


def get_connection():
    return sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )


def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def init_database():

    conn = get_connection()
    cursor = conn.cursor()

    # المدرسين
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # الطلاب
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            parent_name TEXT,
            parent_phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id)
            REFERENCES teachers(id)
        )
    """)

    # الحصص
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            lesson_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            qr_token TEXT,
            qr_expires_at TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id)
            REFERENCES teachers(id)
        )
    """)

    # الحضور
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(lesson_id, student_id),
            FOREIGN KEY (lesson_id)
            REFERENCES lessons(id),
            FOREIGN KEY (student_id)
            REFERENCES students(id)
        )
    """)

    # أولياء الأمور
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            qr_code TEXT UNIQUE,
            FOREIGN KEY (student_id)
            REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# إنشاء حساب مدرس
# =========================================================

def create_teacher(name, email, password):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO teachers
            (name, email, password)
            VALUES (?, ?, ?)
            """,
            (
                name.strip(),
                email.strip().lower(),
                hash_password(password)
            )
        )

        conn.commit()

        return True, "تم إنشاء الحساب بنجاح."

    except sqlite3.IntegrityError:

        return False, "الإيميل مستخدم بالفعل."

    finally:

        conn.close()


# =========================================================
# تسجيل الدخول
# =========================================================

def login_teacher(email, password):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, email
        FROM teachers
        WHERE email = ?
        AND password = ?
        """,
        (
            email.strip().lower(),
            hash_password(password)
        )
    )

    teacher = cursor.fetchone()

    conn.close()

    return teacher


# =========================================================
# إحصائيات
# =========================================================

def count_students(teacher_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM students
        WHERE teacher_id = ?
        """,
        (teacher_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


def count_lessons(teacher_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM lessons
        WHERE teacher_id = ?
        """,
        (teacher_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


def count_parents(teacher_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM parents
        WHERE student_id IN (
            SELECT id
            FROM students
            WHERE teacher_id = ?
        )
        """,
        (teacher_id,)
    )

    result = cursor.fetchone()[0]

    conn.close()

    return result


# =========================================================
# تشغيل قاعدة البيانات
# =========================================================

init_database()


# =========================================================
# Session State
# =========================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "teacher" not in st.session_state:
    st.session_state.teacher = None


# =========================================================
# التصميم
# =========================================================

st.markdown("""
<style>

.main-title {
    text-align: center;
    font-size: 44px;
    font-weight: 800;
    margin-bottom: 5px;
}

.subtitle {
    text-align: center;
    color: #888;
    font-size: 18px;
    margin-bottom: 30px;
}

.card {
    padding: 25px;
    border-radius: 18px;
    border: 1px solid #444;
    background: #202027;
    text-align: center;
}

.number {
    font-size: 35px;
    font-weight: 800;
    margin-top: 8px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# صفحة تسجيل الدخول
# =========================================================

if not st.session_state.logged_in:

    st.markdown(
        '<div class="main-title">🎓 Teacher System</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'نظام إدارة متكامل للمدرس والطلاب وأولياء الأمور'
        '</div>',
        unsafe_allow_html=True
    )

    login_tab, register_tab = st.tabs(
        [
            "🔐 تسجيل الدخول",
            "📝 إنشاء حساب مدرس"
        ]
    )

    # -----------------------------------------------------
    # تسجيل الدخول
    # -----------------------------------------------------

    with login_tab:

        st.subheader("👨‍🏫 تسجيل دخول المدرس")

        email = st.text_input(
            "البريد الإلكتروني",
            key="login_email"
        )

        password = st.text_input(
            "كلمة المرور",
            type="password",
            key="login_password"
        )

        if st.button(
            "دخول",
            use_container_width=True
        ):

            if not email or not password:

                st.warning(
                    "⚠️ اكتب الإيميل وكلمة المرور."
                )

            else:

                teacher = login_teacher(
                    email,
                    password
                )

                if teacher:

                    st.session_state.logged_in = True
                    st.session_state.teacher = teacher

                    st.rerun()

                else:

                    st.error(
                        "❌ الإيميل أو كلمة المرور غير صحيحة."
                    )

    # -----------------------------------------------------
    # إنشاء حساب
    # -----------------------------------------------------

    with register_tab:

        st.subheader("📝 إنشاء حساب مدرس")

        name = st.text_input(
            "اسم المدرس",
            key="register_name"
        )

        email = st.text_input(
            "البريد الإلكتروني",
            key="register_email"
        )

        password = st.text_input(
            "كلمة المرور",
            type="password",
            key="register_password"
        )

        confirm_password = st.text_input(
            "تأكيد كلمة المرور",
            type="password",
            key="confirm_password"
        )

        if st.button(
            "إنشاء الحساب",
            use_container_width=True
        ):

            if not name or not email or not password:

                st.warning(
                    "⚠️ من فضلك املأ جميع البيانات."
                )

            elif password != confirm_password:

                st.error(
                    "❌ كلمتا المرور غير متطابقتين."
                )

            elif len(password) < 6:

                st.error(
                    "❌ كلمة المرور لازم تكون 6 أحرف على الأقل."
                )

            else:

                success, message = create_teacher(
                    name,
                    email,
                    password
                )

                if success:

                    st.success(
                        "✅ تم إنشاء الحساب بنجاح. "
                        "ادخل من تبويب تسجيل الدخول."
                    )

                else:

                    st.error(message)


# =========================================================
# Dashboard
# =========================================================

else:

    teacher = st.session_state.teacher

    teacher_id = teacher[0]
    teacher_name = teacher[1]

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    col1, col2 = st.columns(
        [5, 1]
    )

    with col1:

        st.markdown(
            f"""
            <div class="main-title">
                👨‍🏫 أهلاً يا {teacher_name}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="subtitle">'
            'لوحة التحكم الخاصة بك'
            '</div>',
            unsafe_allow_html=True
        )

    with col2:

        if st.button(
            "🚪 خروج",
            use_container_width=True
        ):

            st.session_state.logged_in = False
            st.session_state.teacher = None

            st.rerun()

    st.divider()

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    students = count_students(
        teacher_id
    )

    lessons = count_lessons(
        teacher_id
    )

    parents = count_parents(
        teacher_id
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.markdown(
            f"""
            <div class="card">
                👨‍🎓
                <div class="number">
                    {students}
                </div>
                الطلاب
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:

        st.markdown(
            f"""
            <div class="card">
                📚
                <div class="number">
                    {lessons}
                </div>
                الحصص
            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:

        st.markdown(
            """
            <div class="card">
                ✅
                <div class="number">
                    0
                </div>
                حضور اليوم
            </div>
            """,
            unsafe_allow_html=True
        )

    with col4:

        st.markdown(
            f"""
            <div class="card">
                👨‍👩‍👦
                <div class="number">
                    {parents}
                </div>
                أولياء الأمور
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    # -----------------------------------------------------
    # أقسام النظام
    # -----------------------------------------------------

    st.subheader("⚡ إدارة النظام")

    col1, col2, col3 = st.columns(3)

    with col1:

        st.button(
            "👨‍🎓 إدارة الطلاب",
            use_container_width=True,
            disabled=True
        )

    with col2:

        st.button(
            "📚 إدارة الحصص",
            use_container_width=True,
            disabled=True
        )

    with col3:

        st.button(
            "📱 QR والحضور",
            use_container_width=True,
            disabled=True
        )

    st.divider()

    st.info(
        "🚀 الأساس جاهز. "
        "الخطوة القادمة: إضافة الطلاب وأولياء الأمور."
)
