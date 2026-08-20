import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import uuid
import hashlib
from datetime import datetime


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed"
)


# =========================================================
# DATABASE
# =========================================================

DB_NAME = "teacher_system_v4.db"


def get_db():
    conn = sqlite3.connect(
        DB_NAME,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()
    cur = conn.cursor()

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
            lesson_token TEXT UNIQUE NOT NULL,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# GRADES
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
    "الصف الثالث الثانوي",
]


# =========================================================
# HELPERS
# =========================================================

def create_student_code(name, phone):

    raw = f"{name}-{phone}-{uuid.uuid4()}"

    code = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:10].upper()

    return "ST-" + code


def get_active_lesson():

    conn = get_db()

    row = conn.execute("""
        SELECT
            id,
            lesson_token,
            lesson_name,
            grade,
            created_at,
            active
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    if row is None:
        return None

    return dict(row)


def get_students():

    conn = get_db()

    rows = conn.execute("""
        SELECT
            id,
            student_code,
            name,
            grade,
            phone,
            parent_phone,
            created_at
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def get_total_students():

    conn = get_db()

    row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM students
    """).fetchone()

    conn.close()

    return int(row["total"])


def get_present_count(lesson_id):

    conn = get_db()

    row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE lesson_id = ?
    """, (lesson_id,)).fetchone()

    conn.close()

    return int(row["total"])


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
        JOIN students
            ON attendance.student_id = students.id
        WHERE attendance.lesson_id = ?
        ORDER BY attendance.id DESC
    """, (lesson_id,)).fetchall()

    conn.close()

    return [dict(row) for row in rows]


# =========================================================
# QR DECODER
# =========================================================

def decode_qr(uploaded_file):

    try:

        data = uploaded_file.getvalue()

        image_array = np.frombuffer(
            data,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        decoded, points, _ = detector.detectAndDecode(
            image
        )

        if decoded:
            return decoded.strip()

    except Exception:
        return None

    return None


# =========================================================
# ATTENDANCE
# =========================================================

def register_attendance(
    student_code,
    lesson_token
):

    conn = get_db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE student_code = ?
    """, (
        student_code,
    )).fetchone()

    if student is None:

        conn.close()

        return (
            False,
            "❌ بيانات الطالب غير موجودة."
        )

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE lesson_token = ?
        AND active = 1
    """, (
        lesson_token,
    )).fetchone()

    if lesson is None:

        conn.close()

        return (
            False,
            "❌ الحصة غير موجودة أو انتهت."
        )

    # التأكد من الصف
    if student["grade"] != lesson["grade"]:

        conn.close()

        return (
            False,
            "❌ الطالب ليس من نفس الصف الخاص بالحصة."
        )

    # هل سجل حضور من قبل؟
    old = conn.execute("""
        SELECT id
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student["id"]
    )).fetchone()

    if old is not None:

        conn.close()

        return (
            True,
            f"⚠️ {student['name']} "
            "تم تسجيل حضوره بالفعل."
        )

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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
        now
    ))

    conn.commit()
    conn.close()

    return (
        True,
        f"✅ تم تسجيل حضور "
        f"{student['name']} بنجاح."
    )


# =========================================================
# STYLE
# =========================================================

st.markdown("""
<style>

.block-container {
    max-width: 950px;
    padding-top: 25px;
    padding-bottom: 80px;
}

.title {
    text-align: center;
    font-size: 52px;
    font-weight: 900;
    margin-bottom: 5px;
}

.subtitle {
    text-align: center;
    color: #999;
    font-size: 18px;
    margin-bottom: 35px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# GET PAGE
# =========================================================

params = st.query_params

page = params.get(
    "page",
    "student"
)

# لو حد فتح ?page=teacher
# يفتح المدرس فقط.
#
# لو فتح الرابط العادي
# يفتح الطالب فقط.


# =========================================================
# STUDENT PAGE
# =========================================================

if page == "student":

    st.markdown(
        '<div class="title">🎓 Teacher System</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'تسجيل حضور الطالب'
        '</div>',
        unsafe_allow_html=True
    )

    st.header("👨‍🎓 صفحة الطالب")

    st.info(
        "هذه صفحة الطالب فقط. "
        "لا توجد لوحة تحكم للمدرس هنا."
    )

    # -----------------------------------------------------
    # REGISTER STUDENT
    # -----------------------------------------------------

    st.subheader("📝 تسجيل بيانات الطالب")

    with st.form("student_form"):

        name = st.text_input(
            "👤 اسم الطالب بالكامل"
        )

        grade = st.selectbox(
            "📚 الصف",
            GRADES
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "👨‍👩‍👦 رقم ولي الأمر"
        )

        submit = st.form_submit_button(
            "✅ حفظ بياناتي",
            use_container_width=True
        )

    if submit:

        if not name.strip():

            st.error(
                "❌ اكتب اسم الطالب."
            )

        elif not phone.strip():

            st.error(
                "❌ اكتب رقم هاتف الطالب."
            )

        elif not parent_phone.strip():

            st.error(
                "❌ اكتب رقم ولي الأمر."
            )

        else:

            conn = get_db()

            existing = conn.execute("""
                SELECT *
                FROM students
                WHERE phone = ?
            """, (
                phone.strip(),
            )).fetchone()

            if existing:

                st.session_state.student_code = (
                    existing["student_code"]
                )

                st.success(
                    f"✅ بياناتك مسجلة بالفعل "
                    f"يا {existing['name']}."
                )

            else:

                code = create_student_code(
                    name.strip(),
                    phone.strip()
                )

                now = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

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
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip(),
                    now
                ))

                conn.commit()

                st.session_state.student_code = code

                st.success(
                    "🎉 تم تسجيل بياناتك بنجاح."
                )

            conn.close()

    st.divider()

    # -----------------------------------------------------
    # CURRENT LESSON
    # -----------------------------------------------------

    lesson = get_active_lesson()

    if lesson is None:

        st.warning(
            "🔴 لا توجد حصة نشطة حاليًا."
        )

        st.info(
            "لما المدرس يبدأ الحصة، "
            "هيظهر هنا مكان تسجيل الحضور."
        )

    else:

        st.success(
            f"🟢 الحصة الحالية: "
            f"{lesson.get('lesson_name', 'الحصة')}"
        )

        st.write(
            f"📚 الصف: "
            f"{lesson.get('grade', '')}"
        )

        st.divider()

        # -------------------------------------------------
        # SCAN QR
        # -------------------------------------------------

        st.subheader(
            "📷 امسح QR الخاص بالحصة"
        )

        student_code = st.session_state.get(
            "student_code"
        )

        if not student_code:

            st.warning(
                "⚠️ سجل بياناتك بالأعلى أولًا."
            )

        else:

            st.info(
                "وجّه الكاميرا إلى QR الموجود "
                "عند المدرس."
            )

            photo = st.camera_input(
                "📷 تصوير QR"
            )

            if photo:

                qr_data = decode_qr(
                    photo
                )

                if not qr_data:

                    st.error(
                        "❌ لم أستطع قراءة QR. "
                        "حاول تصوير الكود بوضوح."
                    )

                elif not qr_data.startswith(
                    "TEACHER_SYSTEM:"
                ):

                    st.error(
                        "❌ هذا QR غير تابع "
                        "لنظام Teacher System."
                    )

                else:

                    lesson_token = qr_data.replace(
                        "TEACHER_SYSTEM:",
                        "",
                        1
                    ).strip()

                    ok, message = register_attendance(
                        student_code,
                        lesson_token
                    )

                    if ok:

                        st.success(
                            message
                        )

                        st.balloons()

                    else:

                        st.error(
                            message
                        )


# =========================================================
# TEACHER PAGE
# =========================================================

elif page == "teacher":

    st.markdown(
        '<div class="title">🎓 Teacher System</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'لوحة تحكم المدرس'
        '</div>',
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    if "teacher_logged" not in st.session_state:

        st.session_state.teacher_logged = False

    if not st.session_state.teacher_logged:

        st.header("🔐 دخول المدرس")

        password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "👨‍🏫 دخول",
            use_container_width=True
        ):

            if password == "123456":

                st.session_state.teacher_logged = True

                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية: 123456"
        )

        st.stop()

    # -----------------------------------------------------
    # TEACHER DASHBOARD
    # -----------------------------------------------------

    st.success(
        "🟢 تم تسجيل دخول المدرس"
    )

    if st.button("🚪 تسجيل خروج"):

        st.session_state.teacher_logged = False

        st.rerun()

    st.divider()

    # -----------------------------------------------------
    # LIVE DASHBOARD
    # -----------------------------------------------------

    @st.fragment(run_every="3s")
    def live_dashboard():

        lesson = get_active_lesson()

        if lesson is None:

            st.subheader(
                "📚 لا توجد حصة نشطة"
            )

            st.info(
                "ابدأ حصة جديدة من الأسفل."
            )

        else:

            total = get_total_students()

            present = get_present_count(
                lesson["id"]
            )

            absent = max(
                total - present,
                0
            )

            st.success(
                "🟢 الحصة نشطة"
            )

            st.markdown(
                f"### 📚 {lesson['lesson_name']}"
            )

            st.write(
                f"الصف: {lesson['grade']}"
            )

            col1, col2, col3 = st.columns(3)

            with col1:

                st.metric(
                    "👨‍🎓 إجمالي الطلاب",
                    total
                )

            with col2:

                st.metric(
                    "✅ حضر",
                    present
                )

            with col3:

                st.metric(
                    "❌ غاب",
                    absent
                )

            st.divider()

            # ---------------------------------------------
            # PRESENT STUDENTS
            # ---------------------------------------------

            st.subheader(
                "✅ الحضور الآن"
            )

            students = get_present_students(
                lesson["id"]
            )

            if not students:

                st.info(
                    "لسه مفيش طالب سجل حضور."
                )

            else:

                for student in students:

                    with st.container(
                        border=True
                    ):

                        st.markdown(
                            f"### 🟢 {student['name']}"
                        )

                        st.write(
                            f"📚 الصف: "
                            f"{student['grade']}"
                        )

                        st.write(
                            f"📱 رقم الطالب: "
                            f"{student['phone']}"
                        )

                        st.write(
                            f"👨‍👩‍👦 رقم ولي الأمر: "
                            f"{student['parent_phone']}"
                        )

                        st.write(
                            f"🕐 وقت التسجيل: "
                            f"{student['attended_at']}"
                        )

    live_dashboard()

    st.divider()

    # -----------------------------------------------------
    # CREATE LESSON
    # -----------------------------------------------------

    lesson = get_active_lesson()

    if lesson is None:

        st.subheader(
            "➕ بدء حصة جديدة"
        )

        lesson_name = st.text_input(
            "اسم الحصة",
            placeholder="مثال: رياضيات"
        )

        grade = st.selectbox(
            "الصف",
            GRADES,
            key="teacher_grade"
        )

        if st.button(
            "▶️ بدء الحصة",
            use_container_width=True
        ):

            if not lesson_name.strip():

                st.warning(
                    "اكتب اسم الحصة."
                )

            else:

                token = str(
                    uuid.uuid4()
                )

                now = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                conn = get_db()

                conn.execute("""
                    UPDATE lessons
                    SET active = 0
                    WHERE active = 1
                """)

                conn.execute("""
                    INSERT INTO lessons
                    (
                        lesson_token,
                        lesson_name,
                        grade,
                        created_at,
                        active
                    )
                    VALUES (?, ?, ?, ?, 1)
                """, (
                    token,
                    lesson_name.strip(),
                    grade,
                    now
                ))

                conn.commit()
                conn.close()

                st.success(
                    "🎉 تم بدء الحصة."
                )

                st.rerun()

    else:

        # -------------------------------------------------
        # QR
        # -------------------------------------------------

        st.subheader(
            "📱 QR الخاص بالحصة"
        )

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4
        )

        qr.add_data(
            "TEACHER_SYSTEM:"
            + lesson["lesson_token"]
        )

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

        st.image(
            buffer.getvalue(),
            caption="📷 الطالب يصور هذا الكود لتسجيل الحضور"
        )

        st.divider()

        st.warning(
            "⚠️ لا تستخدم QR قديم بعد إنهاء الحصة."
        )

        if st.button(
            "🔴 إنهاء الحصة",
            use_container_width=True
        ):

            conn = get_db()

            conn.execute("""
                UPDATE lessons
                SET active = 0
                WHERE id = ?
            """, (
                lesson["id"],
            ))

            conn.commit()
            conn.close()

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()


# =========================================================
# INVALID PAGE
# =========================================================

else:

    st.error(
        "❌ الرابط غير صحيح."
    )

    st.info(
        "استخدم رابط الطالب أو رابط المدرس الصحيح."
        )
