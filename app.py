import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import hashlib
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

# =========================================================
# إعدادات المنصة
# =========================================================

DB_FILE = "attendance.db"
GROUP_SIZE = 70

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide"
)

# =========================================================
# التصميم
# =========================================================

st.markdown("""
<style>
body {
    direction: rtl;
}

.block-container {
    max-width: 1100px;
    padding-top: 25px;
}

.title {
    text-align: center;
    font-size: 48px;
    font-weight: bold;
}

.subtitle {
    text-align: center;
    font-size: 25px;
    margin-bottom: 30px;
}

.card {
    padding: 20px;
    border-radius: 15px;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_database():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            parent_phone TEXT DEFAULT '',
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_name TEXT NOT NULL,
            grade TEXT NOT NULL,
            group_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER DEFAULT 1,
            token TEXT UNIQUE NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            UNIQUE(lesson_id, student_id)
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

    conn.commit()
    conn.close()


# =========================================================
# أدوات
# =========================================================

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_password(password):
    salt = secrets.token_bytes(16)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        120000
    )

    return salt.hex() + ":" + key.hex()


def check_password(password, stored):

    try:
        salt, key = stored.split(":")

        new_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt),
            120000
        ).hex()

        return secrets.compare_digest(
            new_key,
            key
        )

    except Exception:
        return False


def get_base_url():

    try:
        current = st.context.url

        p = urlsplit(current)

        return urlunsplit(
            (
                p.scheme,
                p.netloc,
                p.path,
                "",
                ""
            )
        )

    except Exception:
        return ""


def student_main_url():

    base = get_base_url()

    if base:
        return f"{base}?page=student"

    return "?page=student"


def teacher_main_url():

    base = get_base_url()

    if base:
        return f"{base}?page=teacher"

    return "?page=teacher"


def lesson_url(token):

    base = get_base_url()

    if base:
        return f"{base}?page=student&lesson={token}"

    return f"?page=student&lesson={token}"


# =========================================================
# المجموعات
# =========================================================

def get_groups(grade):

    conn = get_db()

    rows = conn.execute("""
        SELECT group_name, COUNT(*) AS total
        FROM students
        WHERE grade = ?
        GROUP BY group_name
        ORDER BY group_name
    """, (grade,)).fetchall()

    conn.close()

    groups = []

    for row in rows:
        groups.append(row["group_name"])

    if not groups:
        groups = ["المجموعة 1"]

    return groups


def get_group_count(grade, group):

    conn = get_db()

    row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM students
        WHERE grade = ?
        AND group_name = ?
    """, (grade, group)).fetchone()

    conn.close()

    return row["total"]


def find_available_group(grade):

    conn = get_db()

    rows = conn.execute("""
        SELECT group_name, COUNT(*) AS total
        FROM students
        WHERE grade = ?
        GROUP BY group_name
        ORDER BY group_name
    """, (grade,)).fetchall()

    conn.close()

    for row in rows:

        if row["total"] < GROUP_SIZE:
            return row["group_name"]

    return f"المجموعة {len(rows) + 1}"


# =========================================================
# الحصص
# =========================================================

def get_active_lesson():

    conn = get_db()

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return lesson


def get_lesson_stats(lesson_id):

    conn = get_db()

    total = conn.execute("""
        SELECT COUNT(*) AS total
        FROM lesson_students
        WHERE lesson_id = ?
    """, (lesson_id,)).fetchone()["total"]

    present = conn.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE lesson_id = ?
    """, (lesson_id,)).fetchone()["total"]

    absent = total - present

    conn.close()

    return total, present, absent


def create_lesson(
    lesson_name,
    grade,
    group
):

    conn = get_db()

    try:

        # إنهاء أي حصة قديمة مفتوحة
        conn.execute("""
            UPDATE lessons
            SET active = 0,
                ended_at = ?
            WHERE active = 1
        """, (current_time(),))

        token = secrets.token_urlsafe(24)

        cur = conn.execute("""
            INSERT INTO lessons
            (
                lesson_name,
                grade,
                group_name,
                created_at,
                active,
                token
            )
            VALUES (?, ?, ?, ?, 1, ?)
        """, (
            lesson_name,
            grade,
            group,
            current_time(),
            token
        ))

        lesson_id = cur.lastrowid

        students = conn.execute("""
            SELECT id
            FROM students
            WHERE grade = ?
            AND group_name = ?
            ORDER BY id
        """, (
            grade,
            group
        )).fetchall()

        for student in students:

            conn.execute("""
                INSERT OR IGNORE INTO lesson_students
                (
                    lesson_id,
                    student_id
                )
                VALUES (?, ?)
            """, (
                lesson_id,
                student["id"]
            ))

        conn.commit()

        return True

    except Exception as e:

        conn.rollback()

        st.error(
            f"❌ حصل خطأ أثناء إنشاء الحصة: {e}"
        )

        return False

    finally:
        conn.close()


# =========================================================
# تسجيل حضور
# =========================================================

def mark_attendance(token, student_id):

    conn = get_db()

    lesson = conn.execute("""
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
    """, (token,)).fetchone()

    if not lesson:

        conn.close()

        return False, "❌ الحصة غير موجودة أو انتهت."

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (student_id,)).fetchone()

    if not student:

        conn.close()

        return False, "❌ الطالب غير موجود."

    if (
        student["grade"] != lesson["grade"]
        or
        student["group_name"] != lesson["group_name"]
    ):

        conn.close()

        return False, "❌ هذا الـ QR خاص بمجموعة أخرى."

    registered = conn.execute("""
        SELECT 1
        FROM lesson_students
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student_id
    )).fetchone()

    if not registered:

        conn.close()

        return False, "❌ الطالب ليس ضمن هذه المجموعة."

    already = conn.execute("""
        SELECT 1
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student_id
    )).fetchone()

    if already:

        conn.close()

        return True, "✅ حضورك مسجل بالفعل."

    try:

        conn.execute("""
            INSERT INTO attendance
            (
                lesson_id,
                student_id,
                marked_at
            )
            VALUES (?, ?, ?)
        """, (
            lesson["id"],
            student_id,
            current_time()
        ))

        conn.commit()

        return True, "🎉 تم تسجيل الحضور بنجاح."

    except Exception:

        conn.rollback()

        return False, "❌ تعذر تسجيل الحضور."

    finally:

        conn.close()


# =========================================================
# قراءة QR
# =========================================================

def read_qr(uploaded_file):

    try:

        data = np.frombuffer(
            uploaded_file.getvalue(),
            dtype=np.uint8
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR
        )

        if image is None:
            return None

        detector = cv2.QRCodeDetector()

        value, points, _ = detector.detectAndDecode(image)

        if value:
            return value.strip()

        return None

    except Exception:
        return None


# =========================================================
# رأس الصفحة
# =========================================================

def header(title, subtitle):

    st.markdown(
        f"""
        <div class="title">
            {title}
        </div>

        <div class="subtitle">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# تسجيل الطالب
# =========================================================

def student_register():

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب"
    )

    st.info(
        "👋 سجل بياناتك أول مرة فقط، "
        "وبعد ذلك استخدم رابط الحصة الذي يرسله المدرس."
    )

    with st.form("student_registration"):

        name = st.text_input(
            "👨‍🎓 اسم الطالب"
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        parent_phone = st.text_input(
            "👪 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True
        )

    if not submitted:
        return

    name = name.strip()
    phone = phone.strip()
    parent_phone = parent_phone.strip()

    if not name or not phone:

        st.error(
            "❌ اكتب اسم الطالب ورقم الهاتف."
        )

        return

    conn = get_db()

    try:

        old = conn.execute("""
            SELECT *
            FROM students
            WHERE phone = ?
        """, (phone,)).fetchone()

        if old:

            st.session_state.student_id = old["id"]

            st.query_params["student"] = str(
                old["id"]
            )

            st.success(
                "✅ الطالب مسجل بالفعل."
            )

            st.rerun()

        group = find_available_group(
            grade
        )

        cur = conn.execute("""
            INSERT INTO students
            (
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name,
            phone,
            parent_phone,
            grade,
            group,
            current_time()
        ))

        student_id = cur.lastrowid

        conn.commit()

        st.session_state.student_id = student_id

        st.query_params["student"] = str(
            student_id
        )

        st.success(
            f"🎉 تم التسجيل بنجاح — {group}"
        )

        st.rerun()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    finally:

        conn.close()


# =========================================================
# صفحة الطالب
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "📱 واجهة الطالب"
    )

    student_id = st.session_state.get(
        "student_id"
    )

    query_student = st.query_params.get(
        "student"
    )

    if student_id is None and query_student:

        try:

            student_id = int(
                query_student
            )

            st.session_state.student_id = (
                student_id
            )

        except Exception:

            student_id = None

    if student_id is None:

        student_register()

        return

    conn = get_db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (student_id,)).fetchone()

    conn.close()

    if not student:

        st.session_state.pop(
            "student_id",
            None
        )

        st.query_params.clear()

        st.rerun()

    st.success(
        f"👨‍🎓 {student['name']} | "
        f"{student['grade']} | "
        f"{student['group_name']}"
    )

    token = st.query_params.get(
        "lesson"
    )

    lesson = None

    if token:

        conn = get_db()

        lesson = conn.execute("""
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
        """, (token,)).fetchone()

        conn.close()

    if lesson is None:

        lesson = get_active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    if (
        lesson["grade"] != student["grade"]
        or
        lesson["group_name"] != student["group_name"]
    ):

        st.warning(
            "⚠️ لا توجد حصة مفتوحة لمجموعتك."
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"📅 التاريخ والوقت: "
        f"{lesson['created_at']}"
    )

    conn = get_db()

    already = conn.execute("""
        SELECT 1
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
    """, (
        lesson["id"],
        student_id
    )).fetchone()

    conn.close()

    if already:

        st.success(
            "✅ تم تسجيل حضورك في هذه الحصة."
        )

        return

    st.info(
        "📷 امسح QR الموجود عند المدرس."
    )

    image = st.camera_input(
        "📷 تصوير QR",
        key=f"camera_{lesson['id']}"
    )

    if image:

        decoded = read_qr(image)

        if not decoded:

            st.error(
                "❌ لم يتم التعرف على QR."
            )

            return

        ok, message = mark_attendance(
            decoded,
            student_id
        )

        if ok:
            st.success(message)
        else:
            st.error(message)

        st.rerun()


# =========================================================
# دخول المدرس
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 دخول المدرس"
    )

    password = st.text_input(
        "🔐 كلمة المرور",
        type="password"
    )

    if st.button(
        "👨‍🏫 دخول المدرس",
        use_container_width=True
    ):

        # كلمة المرور الافتراضية
        if password == "1234":

            st.session_state.teacher = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )

    st.caption(
        "كلمة المرور الافتراضية: 1234"
    )


# =========================================================
# إنشاء حصة
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="lesson_grade"
    )

    groups = get_groups(
        grade
    )

    group = st.selectbox(
        "👥 المجموعة",
        groups,
        key="lesson_group"
    )

    total = get_group_count(
        grade,
        group
    )

    st.info(
        f"👨‍🎓 عدد الطلاب في المجموعة: "
        f"{total}/{GROUP_SIZE}"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية"
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True
    ):

        if total == 0:

            st.error(
                "❌ لا يوجد طلاب في هذه المجموعة."
            )

            return

        success = create_lesson(
            lesson_name.strip()
            or "الحصة الحالية",
            grade,
            group
        )

        if success:

            st.success(
                "🎉 تم إنشاء الحصة."
            )

            st.rerun()


# =========================================================
# الحصة الحالية
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = get_active_lesson()

    if not lesson:

        st.info(
            "⏳ لا توجد حصة مفتوحة."
        )

        return

    total, present, absent = get_lesson_stats(
        lesson["id"]
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total
    )

    col2.metric(
        "✅ حضر",
        present
    )

    col3.metric(
        "❌ غاب",
        absent
    )

    st.write(
        f"**الصف:** {lesson['grade']}"
    )

    st.write(
        f"**المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"**الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"**التاريخ والوقت:** {lesson['created_at']}"
    )

    # الرابط
    link = lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        link,
        language="text"
    )

    st.success(
        "📱 ابعت الرابط ده للطلاب."
    )

    # QR
    qr = qrcode.make(link)

    buffer = io.BytesIO()

    qr.save(
        buffer,
        format="PNG"
    )

    st.image(
        buffer.getvalue(),
        caption="📷 QR تسجيل الحضور",
        width=300
    )

    # جدول الطلاب
    conn = get_db()

    rows = conn.execute("""
        SELECT
            s.name,
            s.phone,
            a.marked_at
        FROM lesson_students ls

        JOIN students s
        ON s.id = ls.student_id

        LEFT JOIN attendance a
        ON a.lesson_id = ls.lesson_id
        AND a.student_id = ls.student_id

        WHERE ls.lesson_id = ?

        ORDER BY s.name
    """, (
        lesson["id"],
    )).fetchall()

    conn.close()

    data = []

    for row in rows:

        data.append({
            "اسم الطالب": row["name"],
            "رقم الهاتف": row["phone"],
            "الحالة":
                "✅ حاضر"
                if row["marked_at"]
                else "❌ غائب",
            "وقت الحضور":
                row["marked_at"]
                if row["marked_at"]
                else "-"
        })

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "🔄 تحديث الحضور",
            use_container_width=True
        ):

            st.rerun()

    with col2:

        if st.button(
            "⛔ إنهاء الحصة وحفظها",
            use_container_width=True
        ):

            conn = get_db()

            conn.execute("""
                UPDATE lessons
                SET active = 0,
                    ended_at = ?
                WHERE id = ?
            """, (
                current_time(),
                lesson["id"]
            ))

            conn.commit()
            conn.close()

            st.success(
                "✅ تم حفظ الحصة بالكامل."
            )

            st.rerun()


# =========================================================
# التقارير
# =========================================================

def reports_page():

    st.subheader(
        "📋 تقارير الحصص"
    )

    conn = get_db()

    lessons = conn.execute("""
        SELECT *
        FROM lessons
        WHERE active = 0
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    if not lessons:

        st.info(
            "لا توجد حصص محفوظة حتى الآن."
        )

        return

    lesson_options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

        lesson_options[label] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(lesson_options.keys())
    )

    lesson_id = lesson_options[
        selected
    ]

    total, present, absent = get_lesson_stats(
        lesson_id
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total
    )

    c2.metric(
        "✅ الحضور",
        present
    )

    c3.metric(
        "❌ الغياب",
        absent
    )

    conn = get_db()

    rows = conn.execute("""
        SELECT
            s.name,
            s.phone,
            a.marked_at
        FROM lesson_students ls

        JOIN students s
        ON s.id = ls.student_id

        LEFT JOIN attendance a
        ON a.lesson_id = ls.lesson_id
        AND a.student_id = ls.student_id

        WHERE ls.lesson_id = ?

        ORDER BY s.name
    """, (
        lesson_id,
    )).fetchall()

    conn.close()

    data = []

    for row in rows:

        data.append({
            "الطالب": row["name"],
            "الهاتف": row["phone"],
            "الحالة":
                "✅ حاضر"
                if row["marked_at"]
                else "❌ غائب",
            "وقت الحضور":
                row["marked_at"]
                or "-"
        })

    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# إحصائيات الصفوف والمجموعات
# =========================================================

def statistics_page():

    st.subheader(
        "📊 إحصائيات الصفوف والمجموعات"
    )

    conn = get_db()

    groups = conn.execute("""
        SELECT
            grade,
            group_name,
            COUNT(*) AS total
        FROM students
        GROUP BY grade, group_name
        ORDER BY grade, group_name
    """).fetchall()

    conn.close()

    data = []

    for row in groups:

        data.append({
            "الصف": row["grade"],
            "المجموعة": row["group_name"],
            "عدد الطلاب": row["total"],
            "سعة المجموعة": GROUP_SIZE,
            "المقاعد المتبقية":
                max(
                    GROUP_SIZE - row["total"],
                    0
                )
        })

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلين."
        )


# =========================================================
# صفحة الطلاب
# =========================================================

def students_page():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
    )

    conn = get_db()

    rows = conn.execute("""
        SELECT
            id,
            name,
            phone,
            parent_phone,
            grade,
            group_name,
            created_at
        FROM students
        ORDER BY grade, group_name, name
    """).fetchall()

    conn.close()

    st.metric(
        "إجمالي الطلاب",
        len(rows)
    )

    data = []

    for row in rows:

        data.append({
            "ID": row["id"],
            "الاسم": row["name"],
            "هاتف الطالب": row["phone"],
            "هاتف ولي الأمر":
                row["parent_phone"],
            "الصف": row["grade"],
            "المجموعة": row["group_name"],
            "تاريخ التسجيل":
                row["created_at"]
        })

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# لوحة المدرس
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher",
        False
    ):

        teacher_login()

        return

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس"
    )

    if st.button(
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher = False

        st.rerun()

    tabs = st.tabs([
        "➕ إنشاء حصة",
        "📊 الحصة الحالية",
        "📋 التقارير",
        "📈 إحصائيات الصفوف",
        "👨‍🎓 الطلاب"
    ])

    with tabs[0]:

        create_lesson_page()

    with tabs[1]:

        current_lesson_page()

    with tabs[2]:

        reports_page()

    with tabs[3]:

        statistics_page()

    with tabs[4]:

        students_page()

    st.divider()

    st.subheader(
        "🔗 رابط الطالب العام"
    )

    st.code(
        student_main_url(),
        language="text"
    )

    st.info(
        "المدرس يفتح المنصة من رابط المدرس، "
        "وينشئ الحصة، وبعدها يرسل رابط الحصة للطلاب."
    )


# =========================================================
# التشغيل
# =========================================================

def main():

    init_database()

    page = st.query_params.get(
        "page",
        "teacher"
    )

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


if __name__ == "__main__":
    main()
