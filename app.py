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
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# =========================================================
# قاعدة البيانات
# =========================================================

DB_NAME = "teacher_system_v3.db"


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
            lesson_token TEXT UNIQUE NOT NULL,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    # الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id),
            FOREIGN KEY(lesson_id) REFERENCES lessons(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# وظائف مساعدة
# =========================================================

def hash_code(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10].upper()


def create_student_code(name, phone):
    raw = f"{name}-{phone}-{uuid.uuid4()}"
    return "ST-" + hash_code(raw)


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


def get_students():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY name
    """).fetchall()

    conn.close()
    return rows


def get_attendance_count(lesson_id):
    conn = get_db()

    row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE lesson_id = ?
    """, (lesson_id,)).fetchone()

    conn.close()

    return row["total"]


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

    return rows


def decode_qr(uploaded_file):
    try:
        image_bytes = uploaded_file.getvalue()

        image_array = np.frombuffer(
            image_bytes,
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
        pass

    return None


def mark_attendance(student_code, lesson_token):
    conn = get_db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE student_code = ?
    """, (student_code,)).fetchone()

    if not student:
        conn.close()
        return False, "❌ كود الطالب غير موجود."

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE lesson_token = ?
        AND active = 1
    """, (lesson_token,)).fetchone()

    if not lesson:
        conn.close()
        return False, "❌ الحصة غير موجودة أو انتهت."

    # التأكد أن الطالب من نفس الصف
    if student["grade"] != lesson["grade"]:
        conn.close()
        return False, "❌ الطالب ليس من نفس الصف الخاص بالحصة."

    # هل حضر بالفعل؟
    existing = conn.execute("""
        SELECT *
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student["id"]
    )).fetchone()

    if existing:
        conn.close()
        return True, "⚠️ تم تسجيل حضورك بالفعل."

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    return True, f"✅ تم تسجيل حضور {student['name']} بنجاح."


# =========================================================
# التصميم
# =========================================================

st.markdown("""
<style>

.block-container {
    max-width: 1000px;
    padding-top: 25px;
    padding-bottom: 80px;
}

.main-title {
    text-align: center;
    font-size: 52px;
    font-weight: 800;
    margin-bottom: 5px;
}

.subtitle {
    text-align: center;
    color: #999;
    font-size: 20px;
    margin-bottom: 35px;
}

.big-number {
    font-size: 42px;
    font-weight: 800;
    text-align: center;
}

.student-card {
    padding: 15px;
    border-radius: 15px;
    margin-bottom: 10px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# العنوان
# =========================================================

st.markdown(
    '<div class="main-title">🎓 Teacher System</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">نظام إدارة المدرس والحضور الذكي</div>',
    unsafe_allow_html=True
)


# =========================================================
# اختيار نوع الدخول
# =========================================================

mode = st.radio(
    "اختر نوع الدخول",
    [
        "👨‍🏫 لوحة المدرس",
        "👨‍🎓 تسجيل حضور الطالب"
    ],
    horizontal=True
)


# =========================================================
# لوحة المدرس
# =========================================================

if mode == "👨‍🏫 لوحة المدرس":

    st.header("👨‍🏫 لوحة تحكم المدرس")

    # -----------------------------------------------------
    # تسجيل دخول المدرس
    # -----------------------------------------------------

    if "teacher_logged" not in st.session_state:
        st.session_state.teacher_logged = False

    if not st.session_state.teacher_logged:

        password = st.text_input(
            "🔐 كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "دخول المدرس",
            use_container_width=True
        ):

            # كلمة المرور الافتراضية
            if password == "123456":

                st.session_state.teacher_logged = True
                st.rerun()

            else:
                st.error("❌ كلمة المرور غير صحيحة.")

    else:

        st.success("🟢 تم تسجيل دخول المدرس")

        if st.button("🚪 تسجيل خروج"):
            st.session_state.teacher_logged = False
            st.rerun()

        st.divider()

        # -------------------------------------------------
        # بيانات الطلاب
        # -------------------------------------------------

        students = get_students()

        st.subheader("👨‍🎓 الطلاب المسجلون")

        st.metric(
            "إجمالي الطلاب",
            len(students)
        )

        st.divider()

        # -------------------------------------------------
        # الحصة الحالية
        # -------------------------------------------------

        lesson = get_active_lesson()

        if not lesson:

            st.subheader("📚 إنشاء حصة جديدة")

            lesson_name = st.text_input(
                "اسم الحصة",
                placeholder="مثال: رياضة الصف الثالث"
            )

            grade = st.selectbox(
                "الصف",
                [
                    "الصف الأول",
                    "الصف الثاني",
                    "الصف الثالث",
                    "الصف الرابع",
                    "الصف الخامس",
                    "الصف السادس"
                ]
            )

            if st.button(
                "▶️ بدء الحصة",
                use_container_width=True
            ):

                if not lesson_name:
                    st.warning("اكتب اسم الحصة أولًا.")

                else:

                    token = str(uuid.uuid4())

                    now = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    conn = get_db()

                    # إغلاق أي حصة قديمة
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
                        lesson_name,
                        grade,
                        now
                    ))

                    conn.commit()
                    conn.close()

                    st.success("✅ تم بدء الحصة.")

                    st.rerun()

        else:

            st.success(
                f"🟢 الحصة الحالية: {lesson['lesson_name']}"
            )

            st.info(
                f"📚 الصف: {lesson['grade']}"
            )

            # -------------------------------------------------
            # إحصائيات الحضور
            # -------------------------------------------------

            total_students = len(
                get_students()
            )

            present = get_attendance_count(
                lesson["id"]
            )

            absent = max(
                total_students - present,
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
                    "✅ الحاضرون",
                    present
                )

            with col3:
                st.metric(
                    "❌ الغائبون",
                    absent
                )

            st.divider()

            # -------------------------------------------------
            # QR Code
            # -------------------------------------------------

            st.subheader("📱 QR الخاص بالحصة")

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4
            )

            qr.add_data(
                "TEACHER_SYSTEM:" +
                lesson["lesson_token"]
            )

            qr.make(
                fit=True
            )

            qr_image = qr.make_image(
                fill_color="black",
                back_color="white"
            )

            buffer = io.BytesIO()

            qr_image.save(
                buffer,
                format="PNG"
            )

            st.image(
                buffer.getvalue(),
                caption="الطلاب يصورون هذا الكود لتسجيل الحضور",
                use_container_width=False
            )

            st.divider()

            # -------------------------------------------------
            # الطلاب الحاضرون
            # -------------------------------------------------

            st.subheader("✅ الطلاب الحاضرون")

            present_students = get_present_students(
                lesson["id"]
            )

            if not present_students:

                st.info(
                    "لم يتم تسجيل أي طالب حتى الآن."
                )

            else:

                for student in present_students:

                    with st.container(border=True):

                        st.markdown(
                            f"### 👨‍🎓 {student['name']}"
                        )

                        st.write(
                            f"📚 الصف: {student['grade']}"
                        )

                        st.write(
                            f"📱 رقم الطالب: {student['phone']}"
                        )

                        st.write(
                            f"👨‍👩‍👦 رقم ولي الأمر: "
                            f"{student['parent_phone']}"
                        )

                        st.write(
                            f"🕐 وقت الحضور: "
                            f"{student['attended_at']}"
                        )

            st.divider()

            # -------------------------------------------------
            # إنهاء الحصة
            # -------------------------------------------------

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
# صفحة الطالب
# =========================================================

else:

    st.header("👨‍🎓 تسجيل حضور الطالب")

    st.info(
        "هذه صفحة الطالب فقط — لا توجد هنا لوحة تحكم المدرس."
    )

    # -----------------------------------------------------
    # تسجيل الطالب
    # -----------------------------------------------------

    st.subheader("📝 تسجيل بيانات الطالب")

    with st.form("student_registration"):

        name = st.text_input(
            "👤 اسم الطالب بالكامل"
        )

        grade = st.selectbox(
            "📚 الصف",
            [
                "الصف الأول",
                "الصف الثاني",
                "الصف الثالث",
                "الصف الرابع",
                "الصف الخامس",
                "الصف السادس"
            ]
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "👨‍👩‍👦 رقم ولي الأمر"
        )

        register = st.form_submit_button(
            "✅ تسجيل بياناتي",
            use_container_width=True
        )

    if register:

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

                student_code = existing["student_code"]

                st.session_state.student_code = student_code

                st.success(
                    f"✅ الطالب مسجل بالفعل: "
                    f"{existing['name']}"
                )

                st.info(
                    f"🔑 كود الطالب الخاص بك: "
                    f"{student_code}"
                )

            else:

                student_code = create_student_code(
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
                    student_code,
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip(),
                    now
                ))

                conn.commit()

                st.session_state.student_code = student_code

                st.success(
                    "🎉 تم تسجيل بياناتك بنجاح."
                )

                st.info(
                    f"🔑 كود الطالب الخاص بك: "
                    f"{student_code}"
                )

            conn.close()

    st.divider()

    # -----------------------------------------------------
    # تسجيل الحضور
    # -----------------------------------------------------

    st.subheader("📷 تسجيل الحضور بالـ QR")

    active_lesson = get_active_lesson()

    if not active_lesson:

        st.warning(
            "🔴 لا توجد حصة نشطة حاليًا. "
            "انتظر حتى يبدأ المدرس الحصة."
        )

    else:

        st.success(
            f"🟢 الحصة الحالية: "
            f"{active_lesson['lesson_name']}"
        )

        st.write(
            f"📚 الصف: {active_lesson['grade']}"
        )

        student_code = st.session_state.get(
            "student_code",
            ""
        )

        if not student_code:

            st.info(
                "👆 سجل بياناتك بالأعلى أولًا."
            )

        else:

            st.info(
                "📷 اضغط على الكاميرا وصوّر QR "
                "الموجود عند المدرس."
            )

            camera_photo = st.camera_input(
                "📷 تصوير QR الحصة"
            )

            if camera_photo:

                qr_data = decode_qr(
                    camera_photo
                )

                if not qr_data:

                    st.error(
                        "❌ لم يتم التعرف على QR. "
                        "قرّب الكاميرا من الكود وحاول مرة أخرى."
                    )

                else:

                    prefix = "TEACHER_SYSTEM:"

                    if not qr_data.startswith(prefix):

                        st.error(
                            "❌ هذا ليس QR الخاص بنظام Teacher System."
                        )

                    else:

                        lesson_token = qr_data[
                            len(prefix):
                        ]

                        success, message = mark_attendance(
                            student_code,
                            lesson_token
                        )

                        if success:

                            st.success(
                                message
                            )

                        else:

                            st.error(
                                message
            )
