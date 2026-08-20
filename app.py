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
# إعداد الصفحة
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

DB_NAME = "teacher_system_v2.db"
DEFAULT_PASSWORD = "1234"

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

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # الطلاب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            lesson_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            qr_token TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            ended_at TEXT
        )
    """)

    # الحضور
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # إعدادات بسيطة بدون عمود id
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            setting_name TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
    """)

    # باسورد المدرس
    cur.execute("""
        INSERT OR IGNORE INTO settings
        (setting_name, setting_value)
        VALUES (?, ?)
    """, ("teacher_password", hash_password(DEFAULT_PASSWORD)))

    conn.commit()
    conn.close()


init_db()


# =========================================================
# أدوات قاعدة البيانات
# =========================================================

def get_setting(name):
    conn = get_db()
    row = conn.execute(
        "SELECT setting_value FROM settings WHERE setting_name=?",
        (name,)
    ).fetchone()
    conn.close()

    if row:
        return row["setting_value"]

    return None


def set_setting(name, value):
    conn = get_db()
    conn.execute("""
        INSERT INTO settings(setting_name, setting_value)
        VALUES (?, ?)
        ON CONFLICT(setting_name)
        DO UPDATE SET setting_value=excluded.setting_value
    """, (name, value))
    conn.commit()
    conn.close()


def get_students():
    conn = get_db()
    rows = conn.execute("""
        SELECT *
        FROM students
        ORDER BY name
    """).fetchall()
    conn.close()
    return rows


def get_active_lesson():
    conn = get_db()
    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active=1
        ORDER BY lesson_id DESC
        LIMIT 1
    """).fetchone()
    conn.close()
    return row


def get_lesson_attendance(lesson_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT
            s.student_id,
            s.student_code,
            s.name,
            s.grade,
            s.phone,
            s.parent_phone,
            a.attended_at
        FROM attendance a
        JOIN students s
            ON s.student_id = a.student_id
        WHERE a.lesson_id=?
        ORDER BY a.attended_at
    """, (lesson_id,)).fetchall()
    conn.close()
    return rows


def register_student(name, grade, phone, parent_phone):
    name = name.strip()
    phone = phone.strip()
    parent_phone = parent_phone.strip()

    if not name or not phone or not parent_phone:
        return False, "من فضلك املأ كل البيانات."

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM students
        WHERE phone=?
    """, (phone,)).fetchone()

    if existing:
        conn.close()
        return True, existing["student_code"]

    # إنشاء كود طالب تلقائي
    while True:
        code = "ST" + secrets.token_hex(3).upper()

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
            conn.close()
            return True, code

        except sqlite3.IntegrityError:
            pass


def start_lesson(lesson_name, grade):
    conn = get_db()

    # إنهاء أي حصة قديمة
    conn.execute("""
        UPDATE lessons
        SET active=0, ended_at=?
        WHERE active=1
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

    token = secrets.token_urlsafe(24)

    conn.execute("""
        INSERT INTO lessons
        (lesson_name, grade, qr_token, active, started_at)
        VALUES (?, ?, ?, 1, ?)
    """, (
        lesson_name,
        grade,
        token,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE qr_token=?
    """, (token,)).fetchone()

    conn.close()

    return row


def end_lesson(lesson_id):
    conn = get_db()
    conn.execute("""
        UPDATE lessons
        SET active=0,
            ended_at=?
        WHERE lesson_id=?
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        lesson_id
    ))
    conn.commit()
    conn.close()


def mark_attendance(student_id, lesson_id):
    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO attendance
            (lesson_id, student_id, attended_at)
            VALUES (?, ?, ?)
        """, (
            lesson_id,
            student_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()
        return True, "تم تسجيل الحضور بنجاح ✅"

    except sqlite3.IntegrityError:
        conn.close()
        return False, "الطالب مسجل حضور بالفعل في هذه الحصة."


def decode_qr(uploaded_file):
    try:
        image_bytes = uploaded_file.getvalue()
        image_array = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(image)

        if data:
            return data.strip()

        return None

    except Exception:
        return None


# =========================================================
# التصميم
# =========================================================

st.markdown("""
<style>
.main-title {
    text-align: center;
    font-size: 55px;
    font-weight: bold;
}

.subtitle {
    text-align: center;
    font-size: 25px;
    color: #999;
}

.success-box {
    padding: 20px;
    border-radius: 15px;
    background: #123d29;
    color: #65e69a;
    font-size: 22px;
}

.info-box {
    padding: 20px;
    border-radius: 15px;
    background: #173552;
    color: #70b7ff;
    font-size: 20px;
}

.danger-box {
    padding: 20px;
    border-radius: 15px;
    background: #4a2025;
    color: #ff8b95;
    font-size: 20px;
}
</style>
""", unsafe_allow_html=True)


st.markdown(
    '<div class="main-title">🎓 Teacher System</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">نظام إدارة المدرس والحضور الذكي</div>',
    unsafe_allow_html=True
)

st.write("")


# =========================================================
# تسجيل الدخول
# =========================================================

if "teacher_logged" not in st.session_state:
    st.session_state.teacher_logged = False


# =========================================================
# القائمة الجانبية
# =========================================================

with st.sidebar:
    st.header("🔐 النظام")

    mode = st.radio(
        "اختر الصفحة",
        [
            "👨‍🎓 الطالب",
            "👨‍🏫 المدرس"
        ]
    )


# =========================================================
# صفحة الطالب
# =========================================================

if mode == "👨‍🎓 الطالب":

    st.header("👨‍🎓 تسجيل حضور الطالب")

    active = get_active_lesson()

    if not active:
        st.info("🔴 لا توجد حصة نشطة حاليًا.")
        st.stop()

    st.success(
        f"🟢 الحصة الحالية: {active['lesson_name']}"
    )

    st.write(
        f"📚 الصف: **{active['grade']}**"
    )

    # -----------------------------------------------------
    # تسجيل الطالب أول مرة
    # -----------------------------------------------------

    st.subheader("📝 بيانات الطالب")

    students = get_students()

    if "student_code" not in st.session_state:

        with st.form("student_registration"):

            name = st.text_input(
                "اسم الطالب بالكامل"
            )

            grade = st.selectbox(
                "الصف",
                GRADES
            )

            phone = st.text_input(
                "رقم هاتف الطالب"
            )

            parent_phone = st.text_input(
                "رقم هاتف ولي الأمر"
            )

            submitted = st.form_submit_button(
                "💾 حفظ بياناتي"
            )

            if submitted:

                ok, result = register_student(
                    name,
                    grade,
                    phone,
                    parent_phone
                )

                if ok:
                    st.session_state.student_code = result

                    st.success(
                        f"تم تسجيل بياناتك ✅\n\n"
                        f"كود الطالب: **{result}**"
                    )

                    st.rerun()

                else:
                    st.error(result)

    else:

        conn = get_db()

        student = conn.execute("""
            SELECT *
            FROM students
            WHERE student_code=?
        """, (
            st.session_state.student_code,
        )).fetchone()

        conn.close()

        if not student:
            del st.session_state.student_code
            st.rerun()

        st.success(
            f"أهلًا يا **{student['name']}** 👋"
        )

        st.write(
            f"📚 الصف: {student['grade']}"
        )

        st.write(
            f"📱 رقم الطالب: {student['phone']}"
        )

        # -------------------------------------------------
        # QR
        # -------------------------------------------------

        st.subheader("📷 تسجيل الحضور")

        st.info(
            "وجه الكاميرا إلى QR الخاص بالحصة "
            "أو ارفع صورة الـQR."
        )

        camera = st.camera_input(
            "📷 امسح QR الحصة بالكاميرا"
        )

        uploaded = st.file_uploader(
            "أو ارفع صورة QR",
            type=["png", "jpg", "jpeg"]
        )

        qr_file = camera if camera else uploaded

        if qr_file:

            qr_data = decode_qr(qr_file)

            if not qr_data:

                st.error(
                    "❌ لم أستطع قراءة QR. "
                    "حاول تقريب الكاميرا من الكود."
                )

            else:

                # الـQR يحتوي على:
                # TEACHER_SYSTEM|TOKEN
                if qr_data.startswith("TEACHER_SYSTEM|"):

                    token = qr_data.split("|", 1)[1]

                    if token == active["qr_token"]:

                        ok, message = mark_attendance(
                            student["student_id"],
                            active["lesson_id"]
                        )

                        if ok:
                            st.success(message)

                            st.balloons()

                        else:
                            st.warning(message)

                    else:

                        st.error(
                            "❌ هذا QR ليس للحصة الحالية."
                        )

                else:

                    st.error(
                        "❌ QR غير صالح."
                    )


# =========================================================
# صفحة المدرس
# =========================================================

else:

    # -----------------------------------------------------
    # تسجيل دخول المدرس
    # -----------------------------------------------------

    if not st.session_state.teacher_logged:

        st.header("👨‍🏫 دخول المدرس")

        password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button("🔐 دخول"):

            saved_password = get_setting(
                "teacher_password"
            )

            if hash_password(password) == saved_password:

                st.session_state.teacher_logged = True
                st.success("تم تسجيل دخول المدرس ✅")
                st.rerun()

            else:

                st.error(
                    "❌ كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية أول مرة: 1234"
        )

        st.stop()

    # -----------------------------------------------------
    # لوحة المدرس
    # -----------------------------------------------------

    st.header("👨‍🏫 لوحة تحكم المدرس")

    if st.button("🚪 تسجيل خروج المدرس"):

        st.session_state.teacher_logged = False
        st.rerun()

    st.divider()

    # -----------------------------------------------------
    # تغيير الباسورد
    # -----------------------------------------------------

    with st.expander("🔐 تغيير كلمة مرور المدرس"):

        old_password = st.text_input(
            "كلمة المرور الحالية",
            type="password",
            key="old_pass"
        )

        new_password = st.text_input(
            "كلمة المرور الجديدة",
            type="password",
            key="new_pass"
        )

        confirm_password = st.text_input(
            "تأكيد كلمة المرور الجديدة",
            type="password",
            key="confirm_pass"
        )

        if st.button("💾 تغيير كلمة المرور"):

            saved = get_setting(
                "teacher_password"
            )

            if hash_password(old_password) != saved:

                st.error(
                    "❌ كلمة المرور الحالية غير صحيحة."
                )

            elif len(new_password) < 4:

                st.error(
                    "❌ كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل."
                )

            elif new_password != confirm_password:

                st.error(
                    "❌ كلمتا المرور غير متطابقتين."
                )

            else:

                set_setting(
                    "teacher_password",
                    hash_password(new_password)
                )

                st.success(
                    "تم تغيير كلمة المرور بنجاح ✅"
                )

    st.divider()

    # -----------------------------------------------------
    # بدء حصة
    # -----------------------------------------------------

    st.subheader("📚 إنشاء حصة جديدة")

    lesson_grade = st.selectbox(
        "الصف",
        GRADES,
        key="lesson_grade"
    )

    lesson_name = st.text_input(
        "اسم الحصة",
        value="الحصة الحالية"
    )

    if st.button("🟢 بدء الحصة"):

        lesson = start_lesson(
            lesson_name,
            lesson_grade
        )

        st.session_state.active_lesson_id = lesson[
            "lesson_id"
        ]

        st.success(
            "تم بدء الحصة بنجاح ✅"
        )

        st.rerun()

    # -----------------------------------------------------
    # الحصة الحالية
    # -----------------------------------------------------

    active = get_active_lesson()

    if active:

        st.divider()

        st.subheader("🟢 الحصة الحالية")

        st.write(
            f"📚 الصف: **{active['grade']}**"
        )

        st.write(
            f"📖 الحصة: **{active['lesson_name']}**"
        )

        # -------------------------------------------------
        # إنشاء QR
        # -------------------------------------------------

        qr_data = (
            "TEACHER_SYSTEM|"
            + active["qr_token"]
        )

        qr_image = qrcode.make(qr_data)

        buffer = io.BytesIO()
        qr_image.save(buffer, format="PNG")

        st.image(
            buffer.getvalue(),
            caption="📷 QR الحصة — يمسحه الطلاب لتسجيل الحضور",
            width=350
        )

        st.download_button(
            "⬇️ تحميل QR الحصة",
            data=buffer.getvalue(),
            file_name="lesson_qr.png",
            mime="image/png"
        )

        # -------------------------------------------------
        # الحضور
        # -------------------------------------------------

        attendance = get_lesson_attendance(
            active["lesson_id"]
        )

        all_students = get_students()

        total = len(all_students)
        present = len(attendance)
        absent = max(total - present, 0)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "👨‍🎓 إجمالي الطلاب",
                total
            )

        with col2:
            st.metric(
                "🟢 الحاضرون",
                present
            )

        with col3:
            st.metric(
                "🔴 الغائبون",
                absent
            )

        # -------------------------------------------------
        # حالة الحضور
        # -------------------------------------------------

        if total > 0 and present == total:

            st.success(
                "🎉 العدد اكتمل — كل الطلاب سجلوا حضورهم!"
            )

        elif total > 0:

            st.info(
                f"⏳ تم تسجيل حضور {present} من {total} طالب."
            )

        # -------------------------------------------------
        # الطلاب الحاضرون
        # -------------------------------------------------

        st.subheader("🟢 الطلاب الحاضرون")

        if attendance:

            for student in attendance:

                st.write(
                    f"✅ **{student['name']}** — "
                    f"📱 {student['phone']} — "
                    f"ولي الأمر: {student['parent_phone']} — "
                    f"🕐 {student['attended_at']}"
                )

        else:

            st.info(
                "لم يسجل أي طالب حضور حتى الآن."
            )

        # -------------------------------------------------
        # الطلاب الغائبون
        # -------------------------------------------------

        st.subheader("🔴 الطلاب الغائبون")

        present_ids = {
            row["student_id"]
            for row in attendance
        }

        absent_students = [
            s for s in all_students
            if s["student_id"] not in present_ids
        ]

        if absent_students:

            for student in absent_students:

                st.write(
                    f"🔴 **{student['name']}** — "
                    f"📱 {student['phone']} — "
                    f"ولي الأمر: {student['parent_phone']}"
                )

        else:

            st.success(
                "لا يوجد غائبون 🎉"
            )

        # -------------------------------------------------
        # إنهاء الحصة
        # -------------------------------------------------

        st.divider()

        if st.button("🔴 إنهاء الحصة"):

            end_lesson(
                active["lesson_id"]
            )

            st.success(
                "تم إنهاء الحصة وتسجيل الغياب ✅"
            )

            st.rerun()

    else:

        st.info(
            "لا توجد حصة نشطة. "
            "أنشئ حصة من الأعلى."
        )

    # -----------------------------------------------------
    # كل الطلاب المسجلين
    # -----------------------------------------------------

    st.divider()

    st.subheader("👨‍🎓 جميع الطلاب المسجلين")

    students = get_students()

    st.metric(
        "إجمالي الطلاب",
        len(students)
    )

    if students:

        for student in students:

            with st.expander(
                f"👤 {student['name']} — {student['grade']}"
            ):

                st.write(
                    f"🆔 كود الطالب: **{student['student_code']}**"
                )

                st.write(
                    f"📱 رقم الطالب: {student['phone']}"
                )

                st.write(
                    f"📞 رقم ولي الأمر: {student['parent_phone']}"
                )

    else:

        st.info(
            "لا يوجد طلاب مسجلون حتى الآن."
        )
