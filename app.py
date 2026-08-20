import streamlit as st
import sqlite3
import hashlib
import secrets
import io
from datetime import datetime
import qrcode
import cv2
import numpy as np
import pandas as pd

# =========================
# إعداد الصفحة
# =========================
st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_FILE = "teacher_system.db"

# =========================
# قاعدة البيانات
# =========================
def db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            teacher_password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            student_phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade TEXT NOT NULL,
            lesson_name TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            active INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            scanned_at TEXT NOT NULL,
            UNIQUE(lesson_id, student_id),
            FOREIGN KEY(lesson_id) REFERENCES lessons(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    row = cur.execute(
        "SELECT id FROM settings WHERE id=1"
    ).fetchone()

    if row is None:
        cur.execute(
            """
            INSERT INTO settings(id, teacher_password_hash)
            VALUES(1, ?)
            """,
            (hash_password("1234"),)
        )

    conn.commit()
    conn.close()


def check_password(password):
    conn = db()

    row = conn.execute(
        """
        SELECT teacher_password_hash
        FROM settings
        WHERE id=1
        """
    ).fetchone()

    conn.close()

    return (
        row is not None
        and row["teacher_password_hash"] == hash_password(password)
    )


def change_password(new_password):
    conn = db()

    conn.execute(
        """
        UPDATE settings
        SET teacher_password_hash=?
        WHERE id=1
        """,
        (hash_password(new_password),)
    )

    conn.commit()
    conn.close()


# =========================
# مساعدات
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


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_active_lesson():
    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE active=1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    conn.close()

    return row


def create_lesson(grade, lesson_name):
    token = secrets.token_urlsafe(24)

    conn = db()

    conn.execute(
        "UPDATE lessons SET active=0"
    )

    cur = conn.execute(
        """
        INSERT INTO lessons
        (grade, lesson_name, token, active, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (grade, lesson_name, token, 1, now())
    )

    lesson_id = cur.lastrowid

    conn.commit()

    row = conn.execute(
        "SELECT * FROM lessons WHERE id=?",
        (lesson_id,)
    ).fetchone()

    conn.close()

    return row


def close_lesson():
    conn = db()

    conn.execute(
        "UPDATE lessons SET active=0"
    )

    conn.commit()
    conn.close()


def get_students(grade=None):
    conn = db()

    if grade:
        rows = conn.execute(
            """
            SELECT *
            FROM students
            WHERE grade=?
            ORDER BY name
            """,
            (grade,)
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM students
            ORDER BY name
            """
        ).fetchall()

    conn.close()

    return rows


def register_student(
    name,
    grade,
    student_phone,
    parent_phone
):
    conn = db()

    existing = conn.execute(
        """
        SELECT *
        FROM students
        WHERE student_phone=?
        """,
        (student_phone.strip(),)
    ).fetchone()

    if existing:
        conn.close()
        return False, "رقم هاتف الطالب مسجل بالفعل."

    conn.execute(
        """
        INSERT INTO students
        (name, grade, student_phone, parent_phone, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name.strip(),
            grade,
            student_phone.strip(),
            parent_phone.strip(),
            now()
        )
    )

    conn.commit()
    conn.close()

    return True, "تم تسجيل الطالب بنجاح."


def mark_attendance(token, phone):
    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE token=?
        AND active=1
        """,
        (token,)
    ).fetchone()

    if not lesson:
        conn.close()
        return False, "الحصة غير موجودة أو تم إغلاقها."

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE student_phone=?
        """,
        (phone.strip(),)
    ).fetchone()

    if not student:
        conn.close()
        return False, "الطالب غير مسجل."

    if student["grade"] != lesson["grade"]:
        conn.close()
        return False, "الطالب تابع لصف مختلف عن الحصة الحالية."

    existing = conn.execute(
        """
        SELECT id
        FROM attendance
        WHERE lesson_id=?
        AND student_id=?
        """,
        (
            lesson["id"],
            student["id"]
        )
    ).fetchone()

    if existing:
        conn.close()
        return False, "تم تسجيل حضورك بالفعل في هذه الحصة."

    conn.execute(
        """
        INSERT INTO attendance
        (lesson_id, student_id, scanned_at)
        VALUES (?, ?, ?)
        """,
        (
            lesson["id"],
            student["id"],
            now()
        )
    )

    conn.commit()
    conn.close()

    return True, f"تم تسجيل حضور {student['name']} بنجاح."


def attendance_stats(lesson_id):
    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE id=?
        """,
        (lesson_id,)
    ).fetchone()

    total = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM students
        WHERE grade=?
        """,
        (lesson["grade"],)
    ).fetchone()["c"]

    present = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM attendance
        WHERE lesson_id=?
        """,
        (lesson_id,)
    ).fetchone()["c"]

    absent = max(total - present, 0)

    present_rows = conn.execute(
        """
        SELECT
            s.name,
            s.student_phone,
            a.scanned_at
        FROM attendance a
        JOIN students s
        ON s.id=a.student_id
        WHERE a.lesson_id=?
        ORDER BY a.scanned_at
        """,
        (lesson_id,)
    ).fetchall()

    absent_rows = conn.execute(
        """
        SELECT
            s.name,
            s.student_phone
        FROM students s
        WHERE s.grade=?
        AND s.id NOT IN (
            SELECT student_id
            FROM attendance
            WHERE lesson_id=?
        )
        ORDER BY s.name
        """,
        (
            lesson["grade"],
            lesson_id
        )
    ).fetchall()

    conn.close()

    return (
        total,
        present,
        absent,
        present_rows,
        absent_rows
    )


def qr_image(text):
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)

    return bio


def decode_qr(uploaded_file):
    try:
        data = np.frombuffer(
            uploaded_file.getvalue(),
            dtype=np.uint8
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(image)

        return text.strip() if text else ""

    except Exception:
        return ""


# =========================
# تشغيل قاعدة البيانات
# =========================
init_db()


# =========================
# تحديد الصفحة
# =========================
page = st.query_params.get(
    "page",
    "student"
)


# =========================================================
# 👨‍🎓 صفحة الطالب
# =========================================================
def student_page():

    st.title("🎓 صفحة الطالب")

    st.caption(
        "التسجيل أول مرة فقط، وبعد ذلك امسح QR الحصة لتسجيل الحضور."
    )

    tab1, tab2 = st.tabs(
        [
            "📝 تسجيل أول مرة",
            "📷 تسجيل الحضور"
        ]
    )

    # =====================
    # تسجيل أول مرة
    # =====================
    with tab1:

        st.subheader(
            "📝 تسجيل الطالب لأول مرة"
        )

        st.info(
            "بعد التسجيل لن تحتاج لإعادة تسجيل بياناتك."
        )

        name = st.text_input(
            "اسم الطالب"
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

        if st.button(
            "✅ تسجيل الطالب",
            use_container_width=True
        ):

            if not name.strip():
                st.error(
                    "اكتب اسم الطالب."
                )

            elif not phone.strip():
                st.error(
                    "اكتب رقم هاتف الطالب."
                )

            else:

                ok, message = register_student(
                    name,
                    grade,
                    phone,
                    parent_phone
                )

                if ok:
                    st.success(message)
                else:
                    st.warning(message)

    # =====================
    # الحضور
    # =====================
    with tab2:

        st.subheader(
            "📷 تسجيل حضور الحصة"
        )

        phone = st.text_input(
            "رقم هاتف الطالب",
            key="attendance_phone"
        )

        st.write(
            "📱 امسح QR الخاص بالحصة."
        )

        picture = st.camera_input(
            "📷 افتح الكاميرا ووجّهها إلى QR الحصة"
        )

        token = ""

        if picture is not None:

            token = decode_qr(
                picture
            )

            if token:
                st.success(
                    "✅ تم قراءة QR بنجاح."
                )
            else:
                st.error(
                    "❌ لم أستطع قراءة QR."
                )

        if st.button(
            "🟢 تسجيل الحضور",
            use_container_width=True
        ):

            if not phone.strip():
                st.error(
                    "اكتب رقم هاتف الطالب."
                )

            elif not token:
                st.error(
                    "امسح QR الحصة أولاً."
                )

            else:

                ok, message = mark_attendance(
                    token,
                    phone
                )

                if ok:
                    st.success(message)
                else:
                    st.warning(message)

    st.divider()

    st.caption(
        "👨‍🎓 هذه صفحة الطالب فقط."
    )


# =========================================================
# 👨‍🏫 صفحة المدرس
# =========================================================
def teacher_page():

    st.title(
        "👨‍🏫 لوحة تحكم المدرس"
    )

    # =====================
    # تسجيل الدخول
    # =====================
    if not st.session_state.get(
        "teacher_logged_in",
        False
    ):

        st.subheader(
            "🔐 تسجيل دخول المدرس"
        )

        password = st.text_input(
            "كلمة مرور المدرس",
            type="password"
        )

        if st.button(
            "🔓 دخول المدرس",
            use_container_width=True
        ):

            if check_password(password):

                st.session_state.teacher_logged_in = True

                st.rerun()

            else:

                st.error(
                    "كلمة المرور غير صحيحة."
                )

        st.info(
            "كلمة المرور الافتراضية: 1234"
        )

        return

    # =====================
    # خروج
    # =====================
    if st.button(
        "🚪 تسجيل الخروج"
    ):

        st.session_state.teacher_logged_in = False

        st.rerun()

    st.success(
        "تم تسجيل دخول المدرس."
    )

    tabs = st.tabs(
        [
            "📊 الرئيسية",
            "➕ إنشاء حصة",
            "👥 الطلاب",
            "⚙️ الإعدادات"
        ]
    )

    # =====================================================
    # الرئيسية
    # =====================================================
    with tabs[0]:

        lesson = get_active_lesson()

        if not lesson:

            st.info(
                "لا توجد حصة مفتوحة حالياً."
            )

        else:

            st.subheader(
                f"📚 الحصة الحالية: {lesson['lesson_name']}"
            )

            st.write(
                f"الصف: **{lesson['grade']}**"
            )

            (
                total,
                present,
                absent,
                present_rows,
                absent_rows
            ) = attendance_stats(
                lesson["id"]
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "👥 إجمالي الطلاب",
                total
            )

            c2.metric(
                "✅ الحاضرون",
                present
            )

            c3.metric(
                "❌ الغائبون",
                absent
            )

            if total > 0 and present >= total:

                st.success(
                    "🎉 العدد اكتمل — كل الطلاب حاضرون."
                )

            elif total > 0:

                st.warning(
                    f"⚠️ العدد لم يكتمل — يوجد {absent} طالب غائب."
                )

            else:

                st.info(
                    "لا يوجد طلاب مسجلون في هذا الصف."
                )

            st.divider()

            # QR
            st.subheader(
                "📷 QR الحصة"
            )

            st.image(
                qr_image(
                    lesson["token"]
                ),
                width=300
            )

            st.caption(
                "الطلاب يمسحون QR ده من صفحة الطالب."
            )

            st.divider()

            # الحاضرون
            st.subheader(
                "✅ الحاضرون"
            )

            if present_rows:

                df = pd.DataFrame(
                    [
                        {
                            "الطالب": r["name"],
                            "رقم الهاتف": r["student_phone"],
                            "وقت الحضور": r["scanned_at"]
                        }
                        for r in present_rows
                    ]
                )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "لم يسجل أي طالب حضور حتى الآن."
                )

            # الغائبون
            st.subheader(
                "❌ الغائبون"
            )

            if absent_rows:

                df = pd.DataFrame(
                    [
                        {
                            "الطالب": r["name"],
                            "رقم الهاتف": r["student_phone"]
                        }
                        for r in absent_rows
                    ]
                )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.success(
                    "🎉 لا يوجد غياب."
                )

            if st.button(
                "⛔ إنهاء الحصة",
                use_container_width=True
            ):

                close_lesson()

                st.success(
                    "تم إنهاء الحصة."
                )

                st.rerun()

    # =====================================================
    # إنشاء حصة
    # =====================================================
    with tabs[1]:

        st.subheader(
            "➕ إنشاء حصة جديدة"
        )

        grade = st.selectbox(
            "الصف",
            GRADES,
            key="new_lesson_grade"
        )

        lesson_name = st.text_input(
            "اسم الحصة",
            placeholder="مثال: رياضيات - الدرس الأول"
        )

        if st.button(
            "🟢 بدء الحصة",
            use_container_width=True
        ):

            if not lesson_name.strip():

                st.error(
                    "اكتب اسم الحصة."
                )

            else:

                create_lesson(
                    grade,
                    lesson_name
                )

                st.success(
                    "تم إنشاء الحصة وفتحها."
                )

                st.rerun()

    # =====================================================
    # الطلاب
    # =====================================================
    with tabs[2]:

        st.subheader(
            "👥 الطلاب المسجلون"
        )

        grade_filter = st.selectbox(
            "الصف",
            ["كل الصفوف"] + GRADES
        )

        students = get_students(
            None
            if grade_filter == "كل الصفوف"
            else grade_filter
        )

        st.metric(
            "عدد الطلاب",
            len(students)
        )

        if students:

            df = pd.DataFrame(
                [
                    {
                        "الاسم": s["name"],
                        "الصف": s["grade"],
                        "هاتف الطالب": s["student_phone"],
                        "هاتف ولي الأمر": s["parent_phone"],
                        "تاريخ التسجيل": s["created_at"]
                    }
                    for s in students
                ]
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "لا يوجد طلاب مسجلون."
            )

    # =====================================================
    # الإعدادات
    # =====================================================
    with tabs[3]:

        st.subheader(
            "⚙️ إعدادات المدرس"
        )

        st.write(
            "🔑 تغيير كلمة مرور المدرس"
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
            "🔐 تغيير كلمة المرور",
            use_container_width=True
        ):

            if not check_password(
                old_password
            ):

                st.error(
                    "كلمة المرور الحالية غير صحيحة."
                )

            elif len(new_password) < 4:

                st.error(
                    "كلمة المرور يجب أن تكون 4 أحرف أو أرقام على الأقل."
                )

            elif new_password != confirm_password:

                st.error(
                    "تأكيد كلمة المرور غير مطابق."
                )

            else:

                change_password(
                    new_password
                )

                st.success(
                    "✅ تم تغيير كلمة المرور بنجاح."
                )


# =========================================================
# تشغيل الصفحة
# =========================================================
if page == "teacher":

    teacher_page()

else:

    student_page()
