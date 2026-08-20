import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import uuid
from datetime import datetime
from urllib.parse import urlencode

# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

# =========================================================
# قاعدة البيانات
# =========================================================

DB = "teacher_system.db"


def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            class_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(session_id, student_id)
        )
    """)

    conn.commit()
    conn.close()


init_db()

# =========================================================
# دوال قاعدة البيانات
# =========================================================

def add_student(name, class_name, phone, parent_phone):
    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO students
        (name, class_name, phone, parent_phone, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        name,
        class_name,
        phone,
        parent_phone,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    student_id = cur.lastrowid

    conn.commit()
    conn.close()

    return student_id


def get_student(student_id):
    conn = get_db()

    row = conn.execute(
        "SELECT * FROM students WHERE id = ?",
        (student_id,)
    ).fetchone()

    conn.close()

    return row


def get_all_students():
    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM students ORDER BY name"
    ).fetchall()

    conn.close()

    return rows


def create_session(class_name):
    conn = get_db()

    token = str(uuid.uuid4())

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sessions
        (session_token, class_name, started_at, active)
        VALUES (?, ?, ?, 1)
    """, (
        token,
        class_name,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    session_id = cur.lastrowid

    conn.commit()
    conn.close()

    return session_id, token


def get_active_session():
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM sessions
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return row


def close_sessions():
    conn = get_db()

    conn.execute(
        "UPDATE sessions SET active = 0 WHERE active = 1"
    )

    conn.commit()
    conn.close()


def add_attendance(session_id, student_id):
    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO attendance
            (session_id, student_id, attended_at)
            VALUES (?, ?, ?)
        """, (
            session_id,
            student_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()

        success = True

    except sqlite3.IntegrityError:
        success = False

    conn.close()

    return success


def get_attendance(session_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT
            students.name,
            students.class_name,
            students.phone,
            students.parent_phone,
            attendance.attended_at
        FROM attendance
        JOIN students
        ON students.id = attendance.student_id
        WHERE attendance.session_id = ?
        ORDER BY attendance.attended_at
    """, (session_id,)).fetchall()

    conn.close()

    return rows


def get_attendance_student_ids(session_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT student_id
        FROM attendance
        WHERE session_id = ?
    """, (session_id,)).fetchall()

    conn.close()

    return {row["student_id"] for row in rows}


# =========================================================
# قراءة QR من صورة الكاميرا
# =========================================================

def read_qr(image_bytes):

    try:
        image = cv2.imdecode(
            np.frombuffer(image_bytes, np.uint8),
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(image)

        if data:
            return data.strip()

    except Exception:
        pass

    return None


# =========================================================
# تصميم
# =========================================================

st.markdown("""
<style>

.main-title {
    text-align:center;
    font-size:55px;
    font-weight:800;
    margin-top:20px;
}

.sub-title {
    text-align:center;
    font-size:22px;
    color:#999;
    margin-bottom:40px;
}

.success-box {
    padding:20px;
    border-radius:15px;
    background:#103d27;
    color:#55e68a;
    font-size:22px;
    text-align:center;
}

.info-box {
    padding:20px;
    border-radius:15px;
    background:#12324d;
    color:#58aef5;
    font-size:20px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# تحديد نوع المستخدم
# =========================================================

params = st.query_params

role = params.get("role", "student")

# =========================================================
# لوحة المدرس
# =========================================================

if role == "teacher":

    st.markdown(
        '<div class="main-title">👨‍🏫 Teacher System</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">لوحة تحكم المدرس</div>',
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # كلمة مرور المدرس
    # -----------------------------------------------------

    if "teacher_logged" not in st.session_state:
        st.session_state.teacher_logged = False

    if not st.session_state.teacher_logged:

        st.subheader("🔐 دخول المدرس")

        password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button("دخول", use_container_width=True):

            if password == "123456":

                st.session_state.teacher_logged = True
                st.rerun()

            else:
                st.error("❌ كلمة المرور غير صحيحة")

        st.stop()

    # -----------------------------------------------------
    # لوحة التحكم
    # -----------------------------------------------------

    st.success("🟢 تم تسجيل دخول المدرس")

    students = get_all_students()

    total_students = len(students)

    st.subheader("📊 إحصائيات الطلاب")

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total_students
    )

    active_session = get_active_session()

    if active_session:

        attendance = get_attendance(active_session["id"])

        present = len(attendance)
        absent = max(total_students - present, 0)

    else:

        present = 0
        absent = total_students

    c2.metric(
        "✅ الحاضرون",
        present
    )

    c3.metric(
        "❌ الغائبون",
        absent
    )

    st.divider()

    # -----------------------------------------------------
    # بدء حصة
    # -----------------------------------------------------

    st.subheader("📚 إدارة الحصة")

    class_name = st.text_input(
        "اسم الصف / الحصة",
        placeholder="مثال: الصف الثالث - رياضة"
    )

    if st.button(
        "🚀 بدء حصة جديدة",
        use_container_width=True
    ):

        if not class_name.strip():

            st.warning("اكتب اسم الصف أولًا")

        else:

            close_sessions()

            session_id, token = create_session(
                class_name.strip()
            )

            st.session_state.session_id = session_id
            st.session_state.session_token = token

            st.success("✅ تم بدء الحصة")

            st.rerun()

    # -----------------------------------------------------
    # QR الحصة
    # -----------------------------------------------------

    active_session = get_active_session()

    if active_session:

        st.divider()

        st.subheader("📱 QR الخاص بالحصة")

        qr_payload = f"ATTENDANCE:{active_session['session_token']}"

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4
        )

        qr.add_data(qr_payload)
        qr.make(fit=True)

        qr_image = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        img_buffer = io.BytesIO()
        qr_image.save(img_buffer, format="PNG")

        st.image(
            img_buffer.getvalue(),
            width=350
        )

        st.info(
            "📱 خلي الطلاب يفتحوا صفحة الطالب ويمسحوا QR ده."
        )

        st.write(
            f"📚 الحصة: **{active_session['class_name']}**"
        )

        st.write(
            f"🕐 بدأت: **{active_session['started_at']}**"
        )

        # -------------------------------------------------
        # تحديث الحضور
        # -------------------------------------------------

        attendance = get_attendance(
            active_session["id"]
        )

        present = len(attendance)
        absent = max(total_students - present, 0)

        a, b, c = st.columns(3)

        a.metric("👨‍🎓 الطلاب", total_students)
        b.metric("✅ حاضر", present)
        c.metric("❌ غائب", absent)

        st.divider()

        st.subheader("✅ الطلاب الحاضرون")

        if attendance:

            for student in attendance:

                with st.container():

                    st.write(
                        f"👤 **{student['name']}**"
                    )

                    st.write(
                        f"📚 الصف: {student['class_name']}"
                    )

                    st.write(
                        f"📱 الهاتف: {student['phone']}"
                    )

                    st.write(
                        f"👨‍👩‍👦 ولي الأمر: {student['parent_phone']}"
                    )

                    st.write(
                        f"🕐 وقت الحضور: {student['attended_at']}"
                    )

                    st.divider()

        else:

            st.info(
                "لم يتم تسجيل أي حضور حتى الآن."
            )

        # -------------------------------------------------
        # إنهاء الحصة
        # -------------------------------------------------

        if st.button(
            "🔴 إنهاء الحصة",
            use_container_width=True
        ):

            close_sessions()

            st.success("تم إنهاء الحصة")

            st.rerun()

    st.divider()

    # -----------------------------------------------------
    # قائمة كل الطلاب
    # -----------------------------------------------------

    st.subheader("👨‍🎓 جميع الطلاب المسجلين")

    if students:

        for student in students:

            with st.expander(
                f"👤 {student['name']} — {student['class_name']}"
            ):

                st.write(
                    f"📱 الهاتف: {student['phone']}"
                )

                st.write(
                    f"👨‍👩‍👦 ولي الأمر: {student['parent_phone']}"
                )

    else:

        st.info("لا يوجد طلاب مسجلين حتى الآن.")

    st.stop()


# =========================================================
# صفحة الطالب
# =========================================================

st.markdown(
    '<div class="main-title">🎓 Teacher System</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">تسجيل حضور الطالب</div>',
    unsafe_allow_html=True
)

# =========================================================
# معرفة الطالب من الرابط
# =========================================================

student_id = params.get("student")

student = None

if student_id:

    try:
        student = get_student(int(student_id))
    except:
        student = None


# =========================================================
# تسجيل الطالب لأول مرة
# =========================================================

if student is None:

    st.header("👨‍🎓 تسجيل بيانات الطالب")

    st.info(
        "سجل بياناتك مرة واحدة، وبعدها تقدر تسجل حضورك عن طريق QR."
    )

    name = st.text_input(
        "👤 الاسم بالكامل",
        placeholder="اكتب اسمك بالكامل"
    )

    class_name = st.text_input(
        "📚 الصف / الفصل",
        placeholder="مثال: الصف الثالث - أ"
    )

    phone = st.text_input(
        "📱 رقم الهاتف",
        placeholder="01xxxxxxxxx"
    )

    parent_phone = st.text_input(
        "👨‍👩‍👦 رقم ولي الأمر",
        placeholder="01xxxxxxxxx"
    )

    if st.button(
        "✅ حفظ البيانات",
        use_container_width=True
    ):

        if not name.strip():
            st.error("اكتب الاسم")

        elif not class_name.strip():
            st.error("اكتب الصف")

        elif not phone.strip():
            st.error("اكتب رقم الهاتف")

        elif not parent_phone.strip():
            st.error("اكتب رقم ولي الأمر")

        else:

            new_id = add_student(
                name.strip(),
                class_name.strip(),
                phone.strip(),
                parent_phone.strip()
            )

            st.query_params["student"] = str(new_id)

            st.success(
                "✅ تم تسجيل بياناتك بنجاح"
            )

            st.rerun()

    st.stop()


# =========================================================
# الطالب مسجل
# =========================================================

st.success(
    f"👋 أهلاً يا {student['name']}"
)

st.write(
    f"📚 الصف: **{student['class_name']}**"
)

st.write(
    "بياناتك محفوظة، ولتسجيل الحضور امسح QR الخاص بالحصة."
)

st.divider()

# =========================================================
# حالة الحصة
# =========================================================

active_session = get_active_session()

if not active_session:

    st.warning(
        "🔴 لا توجد حصة نشطة حاليًا."
    )

    st.info(
        "انتظر حتى يبدأ المدرس الحصة."
    )

    st.stop()


st.success(
    f"🟢 الحصة الحالية: {active_session['class_name']}"
)

st.write(
    f"🕐 بدأت الساعة: {active_session['started_at']}"
)

st.divider()

# =========================================================
# مسح QR
# =========================================================

st.header("📷 مسح QR لتسجيل الحضور")

camera_image = st.camera_input(
    "وجه الكاميرا إلى QR الخاص بالحصة"
)

if camera_image:

    qr_data = read_qr(
        camera_image.getvalue()
    )

    if not qr_data:

        st.error(
            "❌ لم أستطع قراءة QR. قرب الكاميرا وحاول مرة أخرى."
        )

    else:

        expected = (
            f"ATTENDANCE:{active_session['session_token']}"
        )

        if qr_data != expected:

            st.error(
                "❌ QR غير صحيح أو ليس خاصًا بالحصة الحالية."
            )

        else:

            success = add_attendance(
                active_session["id"],
                student["id"]
            )

            if success:

                st.success(
                    f"✅ تم تسجيل حضورك يا {student['name']}"
                )

                st.balloons()

            else:

                st.info(
                    "ℹ️ أنت مسجل حضور بالفعل في هذه الحصة."
                )

st.divider()

st.caption(
    "🔒 صفحة الطالب لا تحتوي على لوحة تحكم المدرس."
    )
