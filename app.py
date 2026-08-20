import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
from datetime import datetime


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

DB_NAME = "teacher_system_v3.db"


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
            phone TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            ended_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            attended_at TEXT NOT NULL,

            UNIQUE(student_id, lesson_id),

            FOREIGN KEY(student_id)
            REFERENCES students(id),

            FOREIGN KEY(lesson_id)
            REFERENCES lessons(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# الطلاب
# =========================================================

def add_student(code, name, phone):

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO students
            (student_code, name, phone, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                code,
                name,
                phone,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        conn.commit()

        return True, "تم إضافة الطالب بنجاح ✅"

    except sqlite3.IntegrityError:

        return False, "كود الطالب موجود بالفعل ❌"

    finally:

        conn.close()


def get_students():

    conn = get_db()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return rows


def delete_student(student_id):

    conn = get_db()

    conn.execute(
        """
        DELETE FROM students
        WHERE id = ?
        """,
        (student_id,)
    )

    conn.commit()
    conn.close()


# =========================================================
# الحصص
# =========================================================

def create_lesson(title):

    conn = get_db()

    # إغلاق أي حصة قديمة
    conn.execute(
        """
        UPDATE lessons
        SET active = 0
        WHERE active = 1
        """
    )

    # QR جديد للحصة
    token = secrets.token_urlsafe(32)

    cur = conn.execute(
        """
        INSERT INTO lessons
        (title, token, active, created_at)
        VALUES (?, ?, 1, ?)
        """,
        (
            title,
            token,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    lesson_id = cur.lastrowid

    conn.commit()
    conn.close()

    return lesson_id


def get_active_lesson():

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


def end_lesson():

    conn = get_db()

    conn.execute(
        """
        UPDATE lessons
        SET active = 0,
            ended_at = ?
        WHERE active = 1
        """,
        (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        )
    )

    conn.commit()
    conn.close()


def change_lesson_qr(lesson_id):

    conn = get_db()

    new_token = secrets.token_urlsafe(32)

    conn.execute(
        """
        UPDATE lessons
        SET token = ?
        WHERE id = ?
        """,
        (
            new_token,
            lesson_id
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# الحضور
# =========================================================

def mark_attendance(student_id, lesson_id):

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO attendance
            (student_id, lesson_id, attended_at)
            VALUES (?, ?, ?)
            """,
            (
                student_id,
                lesson_id,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        conn.commit()

        return True, "تم تسجيل الحضور بنجاح ✅"

    except sqlite3.IntegrityError:

        return False, (
            "الطالب مسجل حضوره بالفعل "
            "في هذه الحصة ⚠️"
        )

    finally:

        conn.close()


def get_attendance(lesson_id=None):

    conn = get_db()

    if lesson_id:

        rows = conn.execute(
            """
            SELECT
                attendance.id,
                students.student_code,
                students.name,
                students.phone,
                lessons.title,
                attendance.attended_at

            FROM attendance

            JOIN students
            ON students.id = attendance.student_id

            JOIN lessons
            ON lessons.id = attendance.lesson_id

            WHERE attendance.lesson_id = ?

            ORDER BY attendance.id DESC
            """,
            (lesson_id,)
        ).fetchall()

    else:

        rows = conn.execute(
            """
            SELECT
                attendance.id,
                students.student_code,
                students.name,
                students.phone,
                lessons.title,
                attendance.attended_at

            FROM attendance

            JOIN students
            ON students.id = attendance.student_id

            JOIN lessons
            ON lessons.id = attendance.lesson_id

            ORDER BY attendance.id DESC
            """
        ).fetchall()

    conn.close()

    return rows


# =========================================================
# QR
# =========================================================

def generate_qr(data):

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )

    qr.add_data(data)
    qr.make(fit=True)

    return qr.make_image(
        fill_color="black",
        back_color="white"
    )


def qr_to_bytes(image):

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG"
    )

    return buffer.getvalue()


# =========================================================
# قراءة QR من الكاميرا
# =========================================================

def scan_qr(uploaded_image):

    try:

        image_bytes = uploaded_image.getvalue()

        array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            array,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        data, points, _ = detector.detectAndDecode(
            image
        )

        if data:

            return data.strip()

    except Exception:

        pass

    return ""


# =========================================================
# التحقق من QR الحصة
# =========================================================

def is_valid_lesson_qr(qr_data, lesson):

    prefix = "YOSEF_TEACHER_SYSTEM|LESSON|"

    if not qr_data.startswith(prefix):
        return False

    token = qr_data[len(prefix):]

    return token == lesson["token"]


# =========================================================
# QR الطالب الخاص بالحصة
# =========================================================

def make_student_lesson_qr(student, lesson):

    data = (
        "YOSEF_TEACHER_SYSTEM|STUDENT|"
        f"{student['id']}|"
        f"{student['student_code']}|"
        f"{lesson['token']}"
    )

    return generate_qr(data)


def parse_student_qr(qr_data):

    prefix = "YOSEF_TEACHER_SYSTEM|STUDENT|"

    if not qr_data.startswith(prefix):

        return None

    parts = qr_data.split("|")

    if len(parts) != 5:

        return None

    return {
        "student_id": parts[2],
        "student_code": parts[3],
        "lesson_token": parts[4]
    }


# =========================================================
# العنوان
# =========================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 800;
        text-align: center;
    }

    .subtitle {
        text-align: center;
        color: #888;
        font-size: 18px;
        margin-bottom: 30px;
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
    '<div class="subtitle">'
    'نظام إدارة المدرس والحضور الذكي'
    '</div>',
    unsafe_allow_html=True
)


# =========================================================
# اختيار نوع الدخول
# =========================================================

mode = st.radio(
    "اختار نوع الدخول",
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

    students = get_students()
    active_lesson = get_active_lesson()
    attendance = get_attendance()

    # -----------------------------------------------------
    # الإحصائيات
    # -----------------------------------------------------

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "👨‍🎓 عدد الطلاب",
            len(students)
        )

    with col2:

        st.metric(
            "✅ إجمالي الحضور",
            len(attendance)
        )

    with col3:

        st.metric(
            "📚 حالة الحصة",
            "🟢 نشطة"
            if active_lesson
            else "🔴 لا توجد"
        )

    st.divider()


    # =====================================================
    # إضافة طالب
    # =====================================================

    st.subheader("➕ إضافة طالب")

    with st.form("add_student"):

        col1, col2, col3 = st.columns(3)

        with col1:

            student_code = st.text_input(
                "كود الطالب",
                placeholder="ST001"
            )

        with col2:

            student_name = st.text_input(
                "اسم الطالب",
                placeholder="محمد أحمد"
            )

        with col3:

            student_phone = st.text_input(
                "رقم الهاتف",
                placeholder="اختياري"
            )

        submit = st.form_submit_button(
            "➕ إضافة الطالب",
            use_container_width=True
        )

        if submit:

            if not student_code.strip():

                st.error(
                    "اكتب كود الطالب ❌"
                )

            elif not student_name.strip():

                st.error(
                    "اكتب اسم الطالب ❌"
                )

            else:

                ok, message = add_student(
                    student_code.strip(),
                    student_name.strip(),
                    student_phone.strip()
                )

                if ok:

                    st.success(message)

                    st.rerun()

                else:

                    st.error(message)


    st.divider()


    # =====================================================
    # قائمة الطلاب
    # =====================================================

    st.subheader("👨‍🎓 قائمة الطلاب")

    students = get_students()

    if students:

        for student in students:

            col1, col2, col3, col4 = st.columns(
                [1.2, 3, 2, 1]
            )

            with col1:

                st.write(
                    student["student_code"]
                )

            with col2:

                st.write(
                    student["name"]
                )

            with col3:

                st.write(
                    student["phone"] or "-"
                )

            with col4:

                if st.button(
                    "🗑️ حذف",
                    key=f"delete_{student['id']}"
                ):

                    delete_student(
                        student["id"]
                    )

                    st.rerun()

    else:

        st.info(
            "لا يوجد طلاب حتى الآن."
        )


    st.divider()


    # =====================================================
    # إدارة الحصة
    # =====================================================

    st.subheader("📚 إدارة الحصة")

    if not active_lesson:

        lesson_title = st.text_input(
            "اسم الحصة",
            placeholder="رياضيات - الصف الثالث"
        )

        if st.button(
            "🟢 بدء حصة جديدة",
            use_container_width=True
        ):

            if not lesson_title.strip():

                st.warning(
                    "اكتب اسم الحصة أولًا."
                )

            else:

                create_lesson(
                    lesson_title.strip()
                )

                st.success(
                    "تم بدء الحصة وتوليد QR جديد ✅"
                )

                st.rerun()

    else:

        st.success(
            f"🟢 الحصة الحالية: "
            f"{active_lesson['title']}"
        )

        st.write(
            f"بدأت الساعة: "
            f"{active_lesson['created_at']}"
        )

        st.subheader(
            "🔳 QR الخاص بالحصة"
        )

        lesson_qr_data = (
            "YOSEF_TEACHER_SYSTEM|LESSON|"
            + active_lesson["token"]
        )

        lesson_qr = generate_qr(
            lesson_qr_data
        )

        st.image(
            qr_to_bytes(lesson_qr),
            width=350
        )

        st.info(
            "📱 الطالب يمسح QR الحصة "
            "لتسجيل حضوره."
        )

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "🔄 تغيير QR الحصة",
                use_container_width=True
            ):

                change_lesson_qr(
                    active_lesson["id"]
                )

                st.success(
                    "تم تغيير QR الحصة بنجاح 🔄"
                )

                st.rerun()

        with col2:

            if st.button(
                "🔴 إنهاء الحصة",
                use_container_width=True
            ):

                end_lesson()

                st.success(
                    "تم إنهاء الحصة."
                )

                st.rerun()


    st.divider()


    # =====================================================
    # QR الطلاب
    # =====================================================

    active_lesson = get_active_lesson()

    if active_lesson and students:

        st.subheader(
            "🎓 QR الطلاب للحصة الحالية"
        )

        st.info(
            "كل طالب له QR مختلف، "
            "والـQR يتغير تلقائيًا عند تغيير الحصة."
        )

        for student in students:

            with st.expander(
                f"🎓 {student['name']} "
                f"— {student['student_code']}"
            ):

                student_qr = make_student_lesson_qr(
                    student,
                    active_lesson
                )

                st.image(
                    qr_to_bytes(student_qr),
                    width=250
                )

                st.caption(
                    "هذا QR صالح للحصة الحالية فقط."
                )


    st.divider()


    # =====================================================
    # سجل الحضور
    # =====================================================

    st.subheader("📊 سجل الحضور")

    attendance = get_attendance()

    if attendance:

        for record in attendance:

            st.write(
                f"✅ **{record['name']}** "
                f"({record['student_code']}) — "
                f"{record['title']} — "
                f"{record['attended_at']}"
            )

    else:

        st.info(
            "لا توجد سجلات حضور حتى الآن."
        )


# =========================================================
# تسجيل حضور الطالب
# =========================================================

else:

    st.header("👨‍🎓 تسجيل حضور الطالب")

    active_lesson = get_active_lesson()

    # -----------------------------------------------------
    # لا توجد حصة
    # -----------------------------------------------------

    if not active_lesson:

        st.error(
            "🔴 لا توجد حصة نشطة حاليًا."
        )

        st.info(
            "انتظر حتى يبدأ المدرس الحصة."
        )

    else:

        st.success(
            f"🟢 الحصة الحالية: "
            f"{active_lesson['title']}"
        )

        students = get_students()

        if not students:

            st.warning(
                "⚠️ لا يوجد طلاب مسجلون."
            )

        else:

            # -------------------------------------------------
            # اختيار الطالب
            # -------------------------------------------------

            st.subheader(
                "👤 اختار اسم الطالب"
            )

            student_options = {}

            for student in students:

                label = (
                    f"{student['student_code']} - "
                    f"{student['name']}"
                )

                student_options[label] = student["id"]

            selected_student = st.selectbox(
                "اسم الطالب",
                list(student_options.keys())
            )

            student_id = student_options[
                selected_student
            ]

            selected_student_data = next(
                s for s in students
                if s["id"] == student_id
            )

            st.divider()


            # -------------------------------------------------
            # QR الحصة
            # -------------------------------------------------

            st.subheader(
                "📷 مسح QR الحصة"
            )

            st.info(
                "وجّه كاميرا الموبايل إلى QR "
                "الموجود عند المدرس."
            )

            camera_image = st.camera_input(
                "📷 افتح الكاميرا"
            )

            if camera_image:

                qr_result = scan_qr(
                    camera_image
                )

                if not qr_result:

                    st.error(
                        "❌ لم يتم اكتشاف QR."
                    )

                else:

                    # -----------------------------------------
                    # QR الحصة
                    # -----------------------------------------

                    if is_valid_lesson_qr(
                        qr_result,
                        active_lesson
                    ):

                        ok, message = mark_attendance(
                            student_id,
                            active_lesson["id"]
                        )

                        if ok:

                            st.success(
                                "🎉 تم تسجيل حضورك بنجاح!"
                            )

                            st.balloons()

                        else:

                            st.warning(
                                message
                            )

                    else:

                        # -------------------------------------
                        # QR الطالب
                        # -------------------------------------

                        student_qr_data = parse_student_qr(
                            qr_result
                        )

                        if student_qr_data:

                            if (
                                student_qr_data[
                                    "lesson_token"
                                ]
                                != active_lesson["token"]
                            ):

                                st.error(
                                    "❌ QR الطالب قديم "
                                    "أو تابع لحصة أخرى."
                                )

                            elif (
                                int(
                                    student_qr_data[
                                        "student_id"
                                    ]
                                )
                                != student_id
                            ):

                                st.error(
                                    "❌ QR لا يخص الطالب "
                                    "المختار."
                                )

                            else:

                                ok, message = (
                                    mark_attendance(
                                        student_id,
                                        active_lesson["id"]
                                    )
                                )

                                if ok:

                                    st.success(
                                        "🎉 تم تسجيل حضورك بنجاح!"
                                    )

                                    st.balloons()

                                else:

                                    st.warning(
                                        message
                                    )

                        else:

                            st.error(
                                "❌ QR غير صالح "
                                "أو لا ينتمي للنظام."
                            )


            st.divider()


            # -------------------------------------------------
            # QR الطالب
            # -------------------------------------------------

            st.subheader(
                "🎓 QR الطالب"
            )

            st.info(
                "يمكن للطالب عرض QR الخاص به "
                "للحصة الحالية."
            )

            own_qr = make_student_lesson_qr(
                selected_student_data,
                active_lesson
            )

            st.image(
                qr_to_bytes(own_qr),
                width=300
            )

            st.caption(
                "⚠️ هذا QR يتغير عند تغيير الحصة."
            )


            st.divider()

            st.caption(
                "🔒 لا يمكن تسجيل الحضور أكثر من مرة "
                "في نفس الحصة."
            )


# =========================================================
# Footer
# =========================================================

st.divider()

st.caption(
    "🎓 Teacher System — Developed by Yosef"
    )
