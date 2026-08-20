import streamlit as st
import sqlite3
import hashlib
import secrets
import json
from datetime import datetime

import cv2
import numpy as np
import qrcode


# =========================================================
# إعدادات التطبيق
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

DB = "teacher_system_v3.db"

DEFAULT_TEACHER_PASSWORD = "123456"

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

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            phone TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id)
        )
    """)

    # باسورد المدرس الافتراضي
    password_exists = conn.execute(
        "SELECT value FROM settings WHERE key='teacher_password'"
    ).fetchone()

    if password_exists is None:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?)",
            ("teacher_password", hash_password(DEFAULT_TEACHER_PASSWORD))
        )

    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_teacher_password(password):
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key='teacher_password'"
    ).fetchone()
    conn.close()

    if row is None:
        return False

    return hash_password(password) == row["value"]


def change_teacher_password(new_password):
    conn = get_conn()
    conn.execute(
        "UPDATE settings SET value=? WHERE key='teacher_password'",
        (hash_password(new_password),)
    )
    conn.commit()
    conn.close()


# =========================================================
# الطلاب
# =========================================================

def find_student(phone):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM students WHERE phone=?",
        (phone,)
    ).fetchone()
    conn.close()
    return row


def add_student(name, grade, phone, parent_phone):
    conn = get_conn()

    existing = conn.execute(
        "SELECT * FROM students WHERE phone=?",
        (phone,)
    ).fetchone()

    if existing:
        conn.close()
        return existing

    cur = conn.execute("""
        INSERT INTO students
        (name, grade, phone, parent_phone, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        name,
        grade,
        phone,
        parent_phone,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    student_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    ).fetchone()

    conn.close()
    return row


# =========================================================
# الحصص
# =========================================================

def create_lesson(grade, lesson_name):
    conn = get_conn()

    # إنهاء أي حصة قديمة لنفس الصف
    conn.execute(
        "UPDATE lessons SET active=0 WHERE grade=? AND active=1",
        (grade,)
    )

    token = secrets.token_urlsafe(24)

    cur = conn.execute("""
        INSERT INTO lessons
        (grade, lesson_name, token, started_at, active)
        VALUES (?, ?, ?, ?, 1)
    """, (
        grade,
        lesson_name,
        token,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id, token


def get_active_lesson(grade=None):
    conn = get_conn()

    if grade:
        row = conn.execute("""
            SELECT * FROM lessons
            WHERE grade=? AND active=1
            ORDER BY id DESC
            LIMIT 1
        """, (grade,)).fetchone()
    else:
        row = conn.execute("""
            SELECT * FROM lessons
            WHERE active=1
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    conn.close()
    return row


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


# =========================================================
# الحضور
# =========================================================

def mark_attendance(lesson_id, student_id):
    conn = get_conn()

    try:
        conn.execute("""
            INSERT INTO attendance
            (lesson_id, student_id, marked_at)
            VALUES (?, ?, ?)
        """, (
            lesson_id,
            student_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        success = True

    except sqlite3.IntegrityError:
        success = False

    conn.close()
    return success


def get_attendance(lesson_id):
    conn = get_conn()

    rows = conn.execute("""
        SELECT
            students.id,
            students.name,
            students.grade,
            students.phone,
            students.parent_phone,
            attendance.marked_at
        FROM attendance
        JOIN students
        ON students.id = attendance.student_id
        WHERE attendance.lesson_id=?
        ORDER BY attendance.marked_at
    """, (lesson_id,)).fetchall()

    conn.close()
    return rows


def get_students_by_grade(grade):
    conn = get_conn()

    rows = conn.execute("""
        SELECT *
        FROM students
        WHERE grade=?
        ORDER BY name
    """, (grade,)).fetchall()

    conn.close()
    return rows


# =========================================================
# QR
# =========================================================

def make_qr(token):
    qr = qrcode.QRCode(
        version=None,
        box_size=10,
        border=4
    )

    data = json.dumps({
        "type": "teacher_system_attendance",
        "token": token
    })

    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image()
    return img


def read_qr(uploaded_file):
    if uploaded_file is None:
        return None

    try:
        file_bytes = np.asarray(
            bytearray(uploaded_file.read()),
            dtype=np.uint8
        )

        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(image)

        if data:
            try:
                obj = json.loads(data)

                if obj.get("type") == "teacher_system_attendance":
                    return obj.get("token")

            except Exception:
                return None

    except Exception:
        return None

    return None


def get_lesson_by_token(token):
    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token=? AND active=1
        LIMIT 1
    """, (token,)).fetchone()

    conn.close()
    return row


# =========================================================
# Session
# =========================================================

init_db()

if "teacher_logged" not in st.session_state:
    st.session_state.teacher_logged = False

if "student_id" not in st.session_state:
    st.session_state.student_id = None


# =========================================================
# الشكل العام
# =========================================================

st.markdown(
    """
    <style>
    .main-title {
        text-align:center;
        font-size:55px;
        font-weight:bold;
    }

    .subtitle {
        text-align:center;
        font-size:25px;
        color:#999;
        margin-bottom:40px;
    }

    .big-number {
        font-size:45px;
        font-weight:bold;
    }

    </style>
    """,
    unsafe_allow_html=True
)

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
    ["👨‍🏫 المدرس", "🧑‍🎓 الطالب"],
    horizontal=True
)


# =========================================================
# المدرس
# =========================================================

if mode == "👨‍🏫 المدرس":

    if not st.session_state.teacher_logged:

        st.header("👨‍🏫 دخول المدرس")

        password = st.text_input(
            "🔐 باسورد المدرس",
            type="password"
        )

        if st.button("دخول المدرس", use_container_width=True):

            if check_teacher_password(password):
                st.session_state.teacher_logged = True
                st.rerun()
            else:
                st.error("❌ الباسورد غير صحيح")

        st.info(
            "الباسورد الافتراضي لأول تشغيل هو: 123456\n\n"
            "بعد الدخول يمكنك تغييره من إعدادات المدرس."
        )

    else:

        st.success("🟢 تم تسجيل دخول المدرس")

        if st.button("🚪 تسجيل خروج"):
            st.session_state.teacher_logged = False
            st.rerun()

        st.header("👨‍🏫 لوحة تحكم المدرس")

        tabs = st.tabs([
            "📚 إنشاء حصة",
            "📊 الحصة الحالية",
            "👥 الطلاب",
            "⚙️ الإعدادات"
        ])

        # -------------------------------------------------
        # إنشاء حصة
        # -------------------------------------------------

        with tabs[0]:

            st.subheader("➕ إنشاء حصة جديدة")

            grade = st.selectbox(
                "الصف",
                GRADES
            )

            lesson_name = st.text_input(
                "اسم الحصة",
                value="الحصة الحالية"
            )

            if st.button(
                "🟢 بدء الحصة",
                use_container_width=True
            ):

                lesson_id, token = create_lesson(
                    grade,
                    lesson_name
                )

                st.session_state.current_lesson_id = lesson_id

                st.success("✅ تم بدء الحصة")

                st.subheader("📱 QR الخاص بالحصة")

                qr_img = make_qr(token)

                st.image(
                    qr_img,
                    caption="الطلاب يصورون هذا QR لتسجيل الحضور"
                )

                st.info(
                    "📌 كل طالب يتم تسجيله مرة واحدة فقط في نفس الحصة."
                )

        # -------------------------------------------------
        # الحصة الحالية
        # -------------------------------------------------

        with tabs[1]:

            st.subheader("📊 الحصة الحالية")

            lesson = get_active_lesson()

            if lesson is None:

                st.warning("🔴 لا توجد حصة نشطة حالياً.")

            else:

                st.success(
                    f"🟢 {lesson['lesson_name']} — {lesson['grade']}"
                )

                attendance = get_attendance(
                    lesson["id"]
                )

                students = get_students_by_grade(
                    lesson["grade"]
                )

                total = len(students)
                present = len(attendance)
                absent = max(total - present, 0)

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "👥 إجمالي الطلاب",
                        total
                    )

                with col2:
                    st.metric(
                        "✅ الحاضرين",
                        present
                    )

                with col3:
                    st.metric(
                        "❌ الغائبين",
                        absent
                    )

                if total > 0:

                    if present == total:
                        st.success(
                            "🎉 العدد اكتمل — كل الطلاب حضروا!"
                        )
                    else:
                        st.warning(
                            f"⏳ لسه في {absent} طالب لم يسجلوا حضور."
                        )

                st.divider()

                st.subheader("✅ الطلاب الحاضرين")

                if attendance:

                    for student in attendance:

                        st.success(
                            f"👨‍🎓 {student['name']} | "
                            f"📞 {student['phone']} | "
                            f"ولي الأمر: {student['parent_phone']}"
                        )

                else:
                    st.info("لا يوجد حضور حتى الآن.")

                st.divider()

                st.subheader("❌ الطلاب الغائبون")

                present_ids = {
                    row["id"] for row in attendance
                }

                absent_students = [
                    s for s in students
                    if s["id"] not in present_ids
                ]

                if absent_students:

                    for student in absent_students:

                        st.error(
                            f"❌ {student['name']} | "
                            f"📞 {student['phone']} | "
                            f"ولي الأمر: {student['parent_phone']}"
                        )

                else:

                    st.success("لا يوجد غياب 🎉")

                st.divider()

                qr_img = make_qr(
                    lesson["token"]
                )

                st.subheader("📱 QR الحصة")

                st.image(qr_img)

                if st.button(
                    "🔴 إنهاء الحصة",
                    use_container_width=True
                ):

                    end_lesson(lesson["id"])

                    st.success(
                        "✅ تم إنهاء الحصة وحساب الحضور والغياب."
                    )

                    st.rerun()

        # -------------------------------------------------
        # الطلاب
        # -------------------------------------------------

        with tabs[2]:

            st.subheader("👥 جميع الطلاب")

            grade_filter = st.selectbox(
                "اختار الصف",
                ["كل الصفوف"] + GRADES
            )

            conn = get_conn()

            if grade_filter == "كل الصفوف":

                rows = conn.execute("""
                    SELECT *
                    FROM students
                    ORDER BY name
                """).fetchall()

            else:

                rows = conn.execute("""
                    SELECT *
                    FROM students
                    WHERE grade=?
                    ORDER BY name
                """, (grade_filter,)).fetchall()

            conn.close()

            st.metric(
                "👨‍🎓 عدد الطلاب",
                len(rows)
            )

            for student in rows:

                with st.expander(
                    f"👨‍🎓 {student['name']} — {student['grade']}"
                ):

                    st.write(
                        f"📞 رقم الطالب: {student['phone']}"
                    )

                    st.write(
                        f"👨‍👩‍👦 رقم ولي الأمر: "
                        f"{student['parent_phone']}"
                    )

        # -------------------------------------------------
        # الإعدادات
        # -------------------------------------------------

        with tabs[3]:

            st.subheader("⚙️ إعدادات المدرس")

            st.write(
                "تغيير باسورد دخول لوحة المدرس"
            )

            old_password = st.text_input(
                "الباسورد الحالي",
                type="password"
            )

            new_password = st.text_input(
                "الباسورد الجديد",
                type="password"
            )

            confirm_password = st.text_input(
                "تأكيد الباسورد الجديد",
                type="password"
            )

            if st.button(
                "🔐 تغيير الباسورد",
                use_container_width=True
            ):

                if not check_teacher_password(
                    old_password
                ):
                    st.error(
                        "❌ الباسورد الحالي غير صحيح."
                    )

                elif len(new_password) < 4:
                    st.error(
                        "❌ الباسورد الجديد يجب أن يكون 4 أحرف/أرقام على الأقل."
                    )

                elif new_password != confirm_password:
                    st.error(
                        "❌ الباسوردان غير متطابقين."
                    )

                else:

                    change_teacher_password(
                        new_password
                    )

                    st.success(
                        "✅ تم تغيير باسورد المدرس بنجاح."
                    )


# =========================================================
# الطالب
# =========================================================

else:

    st.header("🧑‍🎓 تسجيل حضور الطالب")

    # -----------------------------------------------------
    # لو الطالب لسه مسجلش بياناته
    # -----------------------------------------------------

    if st.session_state.student_id is None:

        st.info(
            "👋 أول مرة فقط: سجل بياناتك، وبعدها تقدر تسجل حضورك في الحصص."
        )

        name = st.text_input(
            "👤 اسم الطالب بالكامل"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        phone = st.text_input(
            "📱 رقم الطالب"
        )

        parent_phone = st.text_input(
            "👨‍👩‍👦 رقم ولي الأمر"
        )

        if st.button(
            "💾 تسجيل بياناتي",
            use_container_width=True
        ):

            if not name.strip():
                st.error("❌ اكتب اسم الطالب.")

            elif not phone.strip():
                st.error("❌ اكتب رقم الطالب.")

            elif not parent_phone.strip():
                st.error("❌ اكتب رقم ولي الأمر.")

            else:

                student = add_student(
                    name.strip(),
                    grade,
                    phone.strip(),
                    parent_phone.strip()
                )

                st.session_state.student_id = student["id"]

                st.success(
                    "✅ تم تسجيل بياناتك بنجاح."
                )

                st.rerun()

    # -----------------------------------------------------
    # الطالب مسجل بالفعل
    # -----------------------------------------------------

    else:

        conn = get_conn()

        student = conn.execute(
            "SELECT * FROM students WHERE id=?",
            (st.session_state.student_id,)
        ).fetchone()

        conn.close()

        if student is None:

            st.session_state.student_id = None
            st.rerun()

        st.success(
            f"👋 أهلاً {student['name']}"
        )

        st.write(
            f"🎓 الصف: {student['grade']}"
        )

        st.write(
            f"📱 رقمك: {student['phone']}"
        )

        st.write(
            f"👨‍👩‍👦 ولي الأمر: {student['parent_phone']}"
        )

        st.divider()

        lesson = get_active_lesson(
            student["grade"]
        )

        if lesson is None:

            st.warning(
                "🔴 لا توجد حصة نشطة لصفك حالياً."
            )

        else:

            st.success(
                f"🟢 الحصة الحالية: {lesson['lesson_name']}"
            )

            st.info(
                "📷 افتح الكاميرا وصوّر QR الحصة الموجود عند المدرس."
            )

            camera = st.camera_input(
                "📸 تصوير QR الحصة"
            )

            if camera is not None:

                token = read_qr(camera)

                if not token:

                    st.error(
                        "❌ لم يتم التعرف على QR. "
                        "قرب الكاميرا من الكود وحاول مرة أخرى."
                    )

                else:

                    lesson_from_qr = get_lesson_by_token(
                        token
                    )

                    if lesson_from_qr is None:

                        st.error(
                            "❌ QR غير صالح أو الحصة انتهت."
                        )

                    elif lesson_from_qr["grade"] != student["grade"]:

                        st.error(
                            "❌ هذا QR خاص بصف آخر."
                        )

                    else:

                        success = mark_attendance(
                            lesson_from_qr["id"],
                            student["id"]
                        )

                        if success:

                            st.success(
                                "✅ تم تسجيل حضورك بنجاح!"
                            )

                            st.balloons()

                        else:

                            st.warning(
                                "⚠️ أنت مسجل حضور بالفعل في هذه الحصة."
                            )

        st.divider()

        if st.button(
            "🔄 تغيير الطالب على هذا الجهاز"
        ):

            st.session_state.student_id = None
            st.rerun()
