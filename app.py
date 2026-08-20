import streamlit as st
import sqlite3
import qrcode
import io
import uuid
import hashlib
import hmac
from datetime import datetime

# =========================================================
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# =========================================================
# قاعدة البيانات
# =========================================================

DB_NAME = "teacher_system.db"

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            phone TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            subject TEXT NOT NULL,
            start_time TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT NOT NULL,
            student_code TEXT NOT NULL,
            student_name TEXT NOT NULL,
            time TEXT NOT NULL,
            UNIQUE(session_token, student_code)
        )
    """)

    conn.commit()
    conn.close()


init_db()

# =========================================================
# كلمة مرور المدرس
# =========================================================

TEACHER_PASSWORD = st.secrets.get(
    "TEACHER_PASSWORD",
    "123456"
)

# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>
body {
    direction: rtl;
}

.main-title {
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    margin-top: 20px;
}

.subtitle {
    text-align: center;
    color: #888;
    font-size: 18px;
    margin-bottom: 30px;
}

.big-card {
    padding: 25px;
    border-radius: 20px;
    border: 1px solid rgba(120,120,120,.25);
    margin-bottom: 20px;
}

.qr-box {
    text-align: center;
}

.success-box {
    padding: 18px;
    border-radius: 15px;
    background: rgba(30, 180, 90, .15);
    text-align: center;
}

.warning-box {
    padding: 18px;
    border-radius: 15px;
    background: rgba(255, 170, 0, .15);
    text-align: center;
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
# تحديد نوع الدخول من الرابط
# =========================================================

params = st.query_params
role = params.get("role", "student")

# =========================================================
# أدوات مساعدة
# =========================================================

def hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def teacher_authenticated():
    return st.session_state.get("teacher_logged_in", False)


def create_qr(data):
    qr = qrcode.QRCode(
        version=None,
        box_size=10,
        border=4
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


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


# =========================================================
# 👨‍🏫 المدرس
# =========================================================

if role == "teacher":

    # -----------------------------------------------------
    # تسجيل دخول المدرس
    # -----------------------------------------------------

    if not teacher_authenticated():

        st.markdown("## 👨‍🏫 دخول المدرس")

        st.info(
            "هذه الصفحة خاصة بالمدرس فقط."
        )

        password = st.text_input(
            "🔐 كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "دخول لوحة المدرس",
            use_container_width=True
        ):

            if hmac.compare_digest(
                password,
                TEACHER_PASSWORD
            ):
                st.session_state.teacher_logged_in = True
                st.rerun()

            else:
                st.error("❌ كلمة المرور غير صحيحة.")

        st.stop()

    # -----------------------------------------------------
    # لوحة المدرس
    # -----------------------------------------------------

    st.success("👨‍🏫 تم تسجيل الدخول كمدرس")

    st.markdown("## 🧑‍🏫 لوحة تحكم المدرس")

    # -----------------------------------------------------
    # إضافة طالب
    # -----------------------------------------------------

    with st.expander("➕ إضافة طالب", expanded=True):

        student_code = st.text_input(
            "كود الطالب",
            placeholder="مثال: ST001"
        )

        student_name = st.text_input(
            "اسم الطالب بالكامل"
        )

        student_phone = st.text_input(
            "رقم الهاتف (اختياري)"
        )

        if st.button(
            "➕ إضافة الطالب",
            use_container_width=True
        ):

            if not student_code or not student_name:
                st.error("❌ اكتب كود الطالب والاسم.")

            else:

                try:

                    conn = get_db()

                    conn.execute("""
                        INSERT INTO students
                        (code, name, phone)
                        VALUES (?, ?, ?)
                    """, (
                        student_code.strip(),
                        student_name.strip(),
                        student_phone.strip()
                    ))

                    conn.commit()
                    conn.close()

                    st.success(
                        "✅ تم إضافة الطالب بنجاح."
                    )

                except sqlite3.IntegrityError:

                    st.error(
                        "❌ كود الطالب موجود بالفعل."
                    )

    # -----------------------------------------------------
    # قائمة الطلاب
    # -----------------------------------------------------

    st.markdown("## 👨‍🎓 قائمة الطلاب")

    conn = get_db()

    students = conn.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    if students:

        for student in students:

            st.write(
                f"👨‍🎓 **{student['name']}** — "
                f"`{student['code']}`"
            )

    else:

        st.info(
            "لا يوجد طلاب حتى الآن."
        )

    st.divider()

    # -----------------------------------------------------
    # الحصة الحالية
    # -----------------------------------------------------

    st.markdown("## 📚 إدارة الحصة")

    active_session = get_active_session()

    if active_session:

        st.success(
            f"🟢 الحصة الحالية: "
            f"**{active_session['subject']}**"
        )

        st.write(
            f"بدأت الساعة: "
            f"{active_session['start_time']}"
        )

        # إنشاء QR
        qr_data = (
            "TEACHER_SYSTEM_ATTENDANCE|"
            + active_session["token"]
        )

        qr_image = create_qr(qr_data)

        st.markdown(
            "<div class='qr-box'>"
            "<h2>📱 QR الخاص بالحصة</h2>"
            "</div>",
            unsafe_allow_html=True
        )

        st.image(
            qr_image,
            caption="الطلاب يمسحوا الكود ده"
        )

        st.info(
            "📱 الطالب يفتح رابط الطالب "
            "ويمسح QR بالكاميرا."
        )

        # -------------------------------------------------
        # الحضور
        # -------------------------------------------------

        conn = get_db()

        attendance = conn.execute("""
            SELECT *
            FROM attendance
            WHERE session_token = ?
            ORDER BY id DESC
        """, (
            active_session["token"],
        )).fetchall()

        conn.close()

        st.markdown("### ✅ حضور الحصة")

        st.write(
            f"إجمالي الحضور: **{len(attendance)}**"
        )

        if attendance:

            for record in attendance:

                st.write(
                    f"✅ {record['student_name']} "
                    f"— {record['student_code']} "
                    f"— {record['time']}"
                )

        else:

            st.info(
                "لم يتم تسجيل أي طالب حتى الآن."
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
                UPDATE sessions
                SET active = 0
                WHERE token = ?
            """, (
                active_session["token"],
            ))

            conn.commit()
            conn.close()

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

    else:

        st.info(
            "🔴 لا توجد حصة نشطة حاليًا."
        )

        subject = st.text_input(
            "📚 اسم المادة / الحصة",
            placeholder="مثال: رياضة الصف الثالث"
        )

        if st.button(
            "🟢 بدء حصة جديدة",
            use_container_width=True
        ):

            if not subject:

                st.error(
                    "❌ اكتب اسم الحصة أولًا."
                )

            else:

                token = uuid.uuid4().hex

                now = datetime.now().strftime(
                    "%H:%M:%S %d-%m-%Y"
                )

                conn = get_db()

                conn.execute("""
                    INSERT INTO sessions
                    (token, subject, start_time, active)
                    VALUES (?, ?, ?, 1)
                """, (
                    token,
                    subject,
                    now
                ))

                conn.commit()
                conn.close()

                st.success(
                    "✅ تم بدء الحصة."
                )

                st.rerun()

    st.divider()

    # -----------------------------------------------------
    # تسجيل الخروج
    # -----------------------------------------------------

    if st.button(
        "🚪 تسجيل خروج المدرس",
        use_container_width=True
    ):

        st.session_state.teacher_logged_in = False
        st.rerun()

# =========================================================
# 👨‍🎓 الطالب
# =========================================================

else:

    st.markdown("## 👨‍🎓 تسجيل حضور الطالب")

    st.info(
        "هذه صفحة الطالب فقط — لا توجد هنا لوحة تحكم المدرس."
    )

    active_session = get_active_session()

    if not active_session:

        st.warning(
            "🔴 لا توجد حصة نشطة حاليًا."
        )

        st.stop()

    # -----------------------------------------------------
    # الحصة الحالية
    # -----------------------------------------------------

    st.success(
        f"🟢 الحصة الحالية: "
        f"**{active_session['subject']}**"
    )

    st.write(
        "📱 امسح QR الموجود عند المدرس لتسجيل حضورك."
    )

    # -----------------------------------------------------
    # كود الطالب
    # -----------------------------------------------------

    student_code = st.text_input(
        "🎓 كود الطالب",
        placeholder="مثال: ST001"
    )

    # -----------------------------------------------------
    # الكاميرا
    # -----------------------------------------------------

    picture = st.camera_input(
        "📷 افتح الكاميرا ووجّهها إلى QR"
    )

    if picture:

        try:

            import cv2
            import numpy as np

            image_bytes = picture.getvalue()

            image_array = np.frombuffer(
                image_bytes,
                dtype=np.uint8
            )

            image = cv2.imdecode(
                image_array,
                cv2.IMREAD_COLOR
            )

            detector = cv2.QRCodeDetector()

            data, points, _ = detector.detectAndDecode(
                image
            )

            if not data:

                st.error(
                    "❌ لم يتم قراءة QR. "
                    "قرّب الكاميرا من الكود وحاول مرة أخرى."
                )

            else:

                expected_prefix = (
                    "TEACHER_SYSTEM_ATTENDANCE|"
                )

                if not data.startswith(
                    expected_prefix
                ):

                    st.error(
                        "❌ QR غير صالح لهذا النظام."
                    )

                else:

                    scanned_token = data.replace(
                        expected_prefix,
                        "",
                        1
                    )

                    if not student_code:

                        st.warning(
                            "⚠️ اكتب كود الطالب أولًا."
                        )

                    else:

                        conn = get_db()

                        student = conn.execute("""
                            SELECT *
                            FROM students
                            WHERE code = ?
                            LIMIT 1
                        """, (
                            student_code.strip(),
                        )).fetchone()

                        if not student:

                            conn.close()

                            st.error(
                                "❌ كود الطالب غير موجود."
                            )

                        elif scanned_token != active_session["token"]:

                            conn.close()

                            st.error(
                                "❌ هذا QR ليس للحصة الحالية."
                            )

                        else:

                            now = datetime.now().strftime(
                                "%H:%M:%S %d-%m-%Y"
                            )

                            try:

                                conn.execute("""
                                    INSERT INTO attendance
                                    (
                                        session_token,
                                        student_code,
                                        student_name,
                                        time
                                    )
                                    VALUES (?, ?, ?, ?)
                                """, (
                                    scanned_token,
                                    student["code"],
                                    student["name"],
                                    now
                                ))

                                conn.commit()

                                st.success(
                                    f"✅ تم تسجيل حضورك يا "
                                    f"{student['name']}"
                                )

                                st.balloons()

                            except sqlite3.IntegrityError:

                                st.warning(
                                    "⚠️ أنت مسجل حضور بالفعل "
                                    "في هذه الحصة."
                                )

                            finally:

                                conn.close()

        except Exception as e:

            st.error(
                "❌ حصل خطأ أثناء قراءة QR."
            )
