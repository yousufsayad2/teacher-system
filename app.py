import streamlit as st
import sqlite3
import hashlib
import secrets
import io
from datetime import datetime

import qrcode
import cv2
import numpy as np


# =========================================================
# إعداد التطبيق
# =========================================================

st.set_page_config(
    page_title="Teacher System",
    page_icon="🎓",
    layout="wide"
)

# قاعدة بيانات جديدة تمامًا
DB = "teacher_system_v2.db"

APP_URL = "https://teacher-system-2t8fcv45z3sqh8zn75s38m.streamlit.app/"

DEFAULT_PASSWORD = "123456"


# =========================================================
# الصفوف
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
# قاعدة البيانات
# =========================================================

def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            guardian_phone TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            grade TEXT NOT NULL,
            title TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.execute("""
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

    password = conn.execute("""
        SELECT value
        FROM settings
        WHERE key = 'teacher_password'
    """).fetchone()

    if password is None:

        conn.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
        """, (
            "teacher_password",
            hash_password(DEFAULT_PASSWORD)
        ))

    conn.commit()
    conn.close()


# =========================================================
# أدوات
# =========================================================

def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_password():

    conn = db()

    row = conn.execute("""
        SELECT value
        FROM settings
        WHERE key = 'teacher_password'
    """).fetchone()

    conn.close()

    return row["value"] if row else None


def set_password(password):

    conn = db()

    conn.execute("""
        INSERT INTO settings(key, value)
        VALUES(?, ?)

        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (
        "teacher_password",
        hash_password(password)
    ))

    conn.commit()
    conn.close()


# =========================================================
# QR
# =========================================================

def create_qr(text):

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(text)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG"
    )

    return buffer.getvalue()


def read_qr(file):

    if file is None:
        return None

    try:

        raw = file.getvalue()

        array = np.frombuffer(
            raw,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            array,
            cv2.IMREAD_COLOR
        )

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(
            image
        )

        if text:
            return text.strip()

    except Exception:
        pass

    return None


# =========================================================
# روابط
# =========================================================

def student_url(token):

    return f"{APP_URL}?student={token}"


def lesson_url(token):

    return f"{APP_URL}?lesson={token}"


# =========================================================
# تشغيل قاعدة البيانات
# =========================================================

init_db()


# =========================================================
# قراءة الرابط
# =========================================================

params = st.query_params

student_token = params.get("student")
lesson_token = params.get("lesson")

teacher_mode = params.get("teacher") == "1"


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    st.title("🎓 Teacher System")

    st.header("🔐 دخول المدرس")

    password = st.text_input(
        "كلمة المرور",
        type="password"
    )

    if st.button(
        "دخول المدرس",
        type="primary"
    ):

        saved = get_password()

        if (
            saved
            and hash_password(password) == saved
        ):

            st.session_state.teacher = True
            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة"
            )

    st.info(
        "كلمة المرور الافتراضية أول مرة: 123456"
    )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    st.title("👨‍🏫 لوحة تحكم المدرس")

    if st.button("🚪 تسجيل خروج"):

        st.session_state.teacher = False
        st.rerun()

    conn = db()

    # =====================================================
    # إحصائيات عامة
    # =====================================================

    total_students = conn.execute("""
        SELECT COUNT(*) AS c
        FROM students
    """).fetchone()["c"]

    st.metric(
        "👨‍🎓 إجمالي الطلاب المسجلين",
        total_students
    )

    st.divider()

    # =====================================================
    # الحصة الحالية
    # =====================================================

    active = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if active:

        lesson_id = active["id"]
        grade = active["grade"]

        st.success(
            f"🟢 الحصة شغالة: {active['title']}"
        )

        st.write(
            f"📚 الصف: **{grade}**"
        )

        st.write(
            f"🕐 بداية الحصة: {active['started_at']}"
        )

        # ---------------------------------------------
        # إجمالي طلاب الصف
        # ---------------------------------------------

        total = conn.execute("""
            SELECT COUNT(*) AS c
            FROM students
            WHERE grade = ?
        """, (
            grade,
        )).fetchone()["c"]

        # ---------------------------------------------
        # الحاضرين
        # ---------------------------------------------

        present = conn.execute("""
            SELECT COUNT(*) AS c
            FROM attendance
            WHERE lesson_id = ?
        """, (
            lesson_id,
        )).fetchone()["c"]

        absent = max(
            total - present,
            0
        )

        # ---------------------------------------------
        # الإحصائيات
        # ---------------------------------------------

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric(
                "🟢 الحاضر",
                present
            )

        with c2:
            st.metric(
                "🔴 الغائب",
                absent
            )

        with c3:
            st.metric(
                "👥 إجمالي الصف",
                total
            )

        # ---------------------------------------------
        # الحالة
        # ---------------------------------------------

        if total == 0:

            st.warning(
                "⚠️ لا يوجد طلاب مسجلون في هذا الصف."
            )

        elif present == total:

            st.success(
                "🎉 العدد اكتمل — كل الطلاب حضروا!"
            )

        else:

            st.warning(
                f"⚠️ لسه متبقي {absent} طالب لم يسجلوا الحضور."
            )

        st.divider()

        # =================================================
        # QR
        # =================================================

        st.header("📱 QR الخاص بالحصة")

        qr_link = lesson_url(
            active["token"]
        )

        st.image(
            create_qr(qr_link),
            width=350
        )

        st.code(qr_link)

        st.info(
            "📌 الطالب يمسح الكود من صفحة الطالب."
        )

        # =================================================
        # الحاضرين
        # =================================================

        st.header("👨‍🎓 الحاضرون")

        rows = conn.execute("""
            SELECT
                students.name,
                students.grade,
                students.phone,
                students.guardian_phone,
                attendance.attended_at

            FROM attendance

            JOIN students
            ON students.id =
               attendance.student_id

            WHERE attendance.lesson_id = ?

            ORDER BY attendance.attended_at
        """, (
            lesson_id,
        )).fetchall()

        if rows:

            data = []

            for row in rows:

                data.append({
                    "اسم الطالب": row["name"],
                    "الصف": row["grade"],
                    "رقم الطالب": row["phone"],
                    "رقم ولي الأمر": row["guardian_phone"],
                    "وقت الحضور": row["attended_at"]
                })

            st.dataframe(
                data,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "لم يسجل أي طالب الحضور حتى الآن."
            )

        # =================================================
        # إنهاء الحصة
        # =================================================

        st.divider()

        if st.button(
            "🔴 إنهاء الحصة وحساب الغياب",
            type="primary"
        ):

            conn.execute("""
                UPDATE lessons

                SET
                    active = 0,
                    ended_at = ?

                WHERE id = ?
            """, (
                now(),
                lesson_id
            ))

            conn.commit()

            st.success(
                f"تم إنهاء الحصة — الحاضر: {present} — الغائب: {absent}"
            )

            conn.close()

            st.rerun()

    # =====================================================
    # إنشاء حصة
    # =====================================================

    else:

        st.info(
            "🔵 لا توجد حصة نشطة الآن."
        )

        st.header("➕ إنشاء حصة جديدة")

        grade = st.selectbox(
            "اختر الصف",
            GRADES
        )

        title = st.text_input(
            "اسم الحصة",
            "الحصة الحالية"
        )

        if st.button(
            "🟢 بدء الحصة",
            type="primary"
        ):

            token = secrets.token_urlsafe(32)

            conn.execute("""
                INSERT INTO lessons(
                    token,
                    grade,
                    title,
                    started_at,
                    active
                )

                VALUES(
                    ?, ?, ?, ?, 1
                )
            """, (
                token,
                grade,
                title,
                now()
            ))

            conn.commit()

            conn.close()

            st.success(
                "✅ تم إنشاء الحصة."
            )

            st.rerun()

    # =====================================================
    # جميع الطلاب
    # =====================================================

    st.divider()

    st.header("👨‍🎓 جميع الطلاب المسجلين")

    students = conn.execute("""
        SELECT
            name,
            grade,
            phone,
            guardian_phone,
            created_at

        FROM students

        ORDER BY id DESC
    """).fetchall()

    if students:

        data = []

        for row in students:

            data.append({
                "اسم الطالب": row["name"],
                "الصف": row["grade"],
                "رقم الطالب": row["phone"],
                "رقم ولي الأمر": row["guardian_phone"],
                "تاريخ التسجيل": row["created_at"]
            })

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون."
        )

    # =====================================================
    # تغيير الباسورد
    # =====================================================

    st.divider()

    st.header("🔑 تغيير باسورد المدرس")

    old_password = st.text_input(
        "الباسورد الحالي",
        type="password"
    )

    new_password = st.text_input(
        "الباسورد الجديد",
        type="password"
    )

    confirm = st.text_input(
        "تأكيد الباسورد الجديد",
        type="password"
    )

    if st.button(
        "💾 حفظ الباسورد الجديد"
    ):

        if hash_password(old_password) != get_password():

            st.error(
                "❌ الباسورد الحالي غلط."
            )

        elif len(new_password) < 4:

            st.error(
                "❌ الباسورد لازم يكون 4 أحرف/أرقام على الأقل."
            )

        elif new_password != confirm:

            st.error(
                "❌ الباسورد الجديد وتأكيده غير متطابقين."
            )

        else:

            set_password(new_password)

            st.success(
                "✅ تم تغيير باسورد المدرس."
            )

    conn.close()


# =========================================================
# تسجيل الطالب
# =========================================================

def student_registration():

    st.title("🎓 Teacher System")

    st.header("📝 تسجيل الطالب")

    st.info(
        "التسجيل ده يتم مرة واحدة فقط."
    )

    name = st.text_input(
        "👤 اسم الطالب بالكامل"
    )

    grade = st.selectbox(
        "📚 الصف",
        GRADES
    )

    phone = st.text_input(
        "📱 رقم الطالب"
    )

    guardian = st.text_input(
        "👨‍👩‍👦 رقم ولي الأمر"
    )

    if st.button(
        "✅ تسجيل الطالب",
        type="primary"
    ):

        name = name.strip()
        phone = phone.strip()
        guardian = guardian.strip()

        if not name:

            st.error("اكتب اسم الطالب.")
            return

        if not phone:

            st.error("اكتب رقم الطالب.")
            return

        if not guardian:

            st.error("اكتب رقم ولي الأمر.")
            return

        conn = db()

        exists = conn.execute("""
            SELECT id
            FROM students
            WHERE phone = ?
        """, (
            phone,
        )).fetchone()

        if exists:

            st.error(
                "❌ الرقم ده مسجل بالفعل."
            )

            conn.close()
            return

        token = secrets.token_urlsafe(32)

        conn.execute("""
            INSERT INTO students(
                token,
                name,
                grade,
                phone,
                guardian_phone,
                created_at
            )

            VALUES(
                ?, ?, ?, ?, ?, ?
            )
        """, (
            token,
            name,
            grade,
            phone,
            guardian,
            now()
        ))

        conn.commit()
        conn.close()

        url = student_url(token)

        st.success(
            "🎉 تم التسجيل بنجاح!"
        )

        st.warning(
            "⚠️ احفظ رابط الطالب ده، لأنه هيكون صفحتك الخاصة."
        )

        st.code(url)

        st.link_button(
            "📱 فتح صفحة الطالب",
            url
        )


# =========================================================
# صفحة الطالب
# =========================================================

def student_page(token):

    conn = db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE token = ?
    """, (
        token,
    )).fetchone()

    if not student:

        conn.close()

        st.error(
            "❌ رابط الطالب غير صحيح."
        )

        return

    st.title(
        f"👋 أهلاً {student['name']}"
    )

    st.write(
        f"📚 الصف: **{student['grade']}**"
    )

    st.info(
        "📱 دي صفحة الطالب فقط."
    )

    # =====================================================
    # الحصة
    # =====================================================

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if not lesson:

        conn.close()

        st.warning(
            "🔴 لا توجد حصة نشطة حاليًا."
        )

        return

    # =====================================================
    # الصف
    # =====================================================

    if lesson["grade"] != student["grade"]:

        conn.close()

        st.warning(
            "⚠️ لا توجد حصة حاليًا لصفك."
        )

        return

    st.success(
        f"🟢 الحصة الحالية: {lesson['title']}"
    )

    st.header(
        "📷 تسجيل الحضور"
    )

    st.write(
        "وجّه كاميرا الموبايل إلى QR الموجود عند المدرس."
    )

    picture = st.camera_input(
        "📷 مسح QR الحصة"
    )

    if picture:

        scanned = read_qr(
            picture
        )

        if not scanned:

            st.error(
                "❌ لم يتم التعرف على QR."
            )

        else:

            expected = lesson_url(
                lesson["token"]
            )

            if scanned != expected:

                st.error(
                    "❌ QR غير صحيح أو خاص بحصة أخرى."
                )

            else:

                already = conn.execute("""
                    SELECT id

                    FROM attendance

                    WHERE lesson_id = ?

                    AND student_id = ?
                """, (
                    lesson["id"],
                    student["id"]
                )).fetchone()

                if already:

                    st.warning(
                        "⚠️ أنت مسجل حضور بالفعل."
                    )

                else:

                    conn.execute("""
                        INSERT INTO attendance(
                            lesson_id,
                            student_id,
                            attended_at
                        )

                        VALUES(
                            ?, ?, ?
                        )
                    """, (
                        lesson["id"],
                        student["id"],
                        now()
                    ))

                    conn.commit()

                    st.success(
                        "✅ تم تسجيل حضورك بنجاح!"
                    )

                    st.balloons()

                    st.info(
                        "👨‍🏫 تم تسجيل حضورك عند المدرس."
                    )

    conn.close()


# =========================================================
# صفحة QR الخاص بالحصة
# =========================================================

def lesson_page(token):

    conn = db()

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token = ?
    """, (
        token,
    )).fetchone()

    conn.close()

    if not lesson:

        st.error(
            "❌ QR غير صالح."
        )

        return

    st.title(
        "📚 Teacher System"
    )

    st.warning(
        "⚠️ QR الحصة ده لازم يتم مسحه من صفحة الطالب الخاصة به."
    )

    st.write(
        f"الحصة: **{lesson['title']}**"
    )

    st.write(
        f"الصف: **{lesson['grade']}**"
    )


# =========================================================
# التوجيه
# =========================================================

if teacher_mode:

    if st.session_state.get(
        "teacher",
        False
    ):

        teacher_dashboard()

    else:

        teacher_login()

elif student_token:

    student_page(
        student_token
    )

elif lesson_token:

    lesson_page(
        lesson_token
    )

else:

    student_registration()


# =========================================================
# نهاية
# =========================================================

st.caption(
    "Teacher System • Smart Attendance"
    )
