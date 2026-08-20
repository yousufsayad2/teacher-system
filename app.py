import streamlit as st
import sqlite3
import qrcode
import cv2
import numpy as np
import io
import secrets
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote


# =========================================================
# CONFIG
# =========================================================

DB_FILE = "attendance_platform.db"

GROUPS = [
    "المجموعة 1",
    "المجموعة 2",
    "المجموعة 3",
]

GROUP_LIMIT = 70

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

TEACHER_PASSWORD = "1234"


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
)


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1200px;
        padding-top: 25px;
        padding-bottom: 50px;
    }

    .main-title {
        text-align: center;
        font-size: 46px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 23px;
        margin-bottom: 28px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# DATABASE
# =========================================================

def db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA busy_timeout=30000"
    )

    return conn


def init_db():

    conn = db()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                parent_phone TEXT DEFAULT '',
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_name TEXT NOT NULL,
                grade TEXT NOT NULL,
                group_name TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                ended_at TEXT,
                active INTEGER DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                UNIQUE(lesson_id, student_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marked_at TEXT NOT NULL,
                UNIQUE(lesson_id, student_id)
            )
            """
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# HELPERS
# =========================================================

def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def clean_phone(phone):

    return re.sub(
        r"\D",
        "",
        phone or "",
    )


def header(title, subtitle):

    st.markdown(
        f"""
        <div class="main-title">
            {title}
        </div>

        <div class="sub-title">
            {subtitle}
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# STUDENT HELPERS
# =========================================================

def get_student(student_id):

    if not student_id:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()

    finally:

        conn.close()


def get_student_by_phone(phone):

    phone = clean_phone(phone)

    if not phone:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

    finally:

        conn.close()


def get_student_id():

    sid = st.session_state.get(
        "student_id"
    )

    if sid is None:

        sid = st.query_params.get(
            "student"
        )

    try:

        sid = int(sid)

        if get_student(sid):

            st.session_state.student_id = sid

            return sid

    except (
        TypeError,
        ValueError,
    ):

        pass

    return None


# =========================================================
# URL
# =========================================================

def get_base_url():

    try:

        current = st.context.url

        if current:

            parsed = urlparse(
                current
            )

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    except Exception:

        pass

    return ""


def student_url():

    base = get_base_url()

    if base:

        return (
            f"{base}?page=student"
        )

    return "?page=student"


def lesson_url(token):

    base = get_base_url()

    if base:

        return (
            f"{base}"
            f"?page=student"
            f"&lesson={token}"
        )

    return (
        f"?page=student"
        f"&lesson={token}"
    )


# =========================================================
# GROUP COUNT
# =========================================================

def group_count(
    grade,
    group,
):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()[0]

    finally:

        conn.close()


# =========================================================
# LESSON HELPERS
# =========================================================

def get_lesson_by_token(token):

    if not token:
        return None

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

    finally:

        conn.close()


def get_active_lessons():

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()


# =========================================================
# TOKEN
# =========================================================

def extract_token(value):

    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    if (
        "://" not in value
        and "lesson=" not in value
    ):

        return value

    try:

        result = parse_qs(
            urlparse(value).query
        ).get(
            "lesson"
        )

        if result:

            return unquote(
                result[0]
            ).strip()

    except Exception:

        pass

    match = re.search(
        r"lesson=([^&#\s]+)",
        value,
    )

    if match:

        return unquote(
            match.group(1)
        ).strip()

    return None


# =========================================================
# QR DECODER
# =========================================================

def decode_qr(image_bytes):

    try:

        data = np.frombuffer(
            image_bytes,
            dtype=np.uint8,
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_COLOR,
        )

        if image is None:

            return None

        detector = cv2.QRCodeDetector()

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        h, w = gray.shape[:2]

        attempts = [
            image,
            gray,
            cv2.resize(
                gray,
                (
                    max(1, w * 2),
                    max(1, h * 2),
                ),
                interpolation=cv2.INTER_CUBIC,
            ),
        ]

        for img in attempts:

            try:

                value, _, _ = (
                    detector.detectAndDecode(
                        img
                    )
                )

                if value:

                    return value.strip()

            except Exception:

                pass

    except Exception:

        pass

    return None


# =========================================================
# ATTENDANCE
# =========================================================

def mark_attendance(
    token,
    student_id,
):

    token = extract_token(token)

    lesson = get_lesson_by_token(
        token
    )

    if not lesson:

        return (
            False,
            "❌ الحصة غير موجودة أو انتهت.",
        )

    student = get_student(
        student_id
    )

    if not student:

        return (
            False,
            "❌ الطالب غير موجود.",
        )

    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        return (
            False,
            (
                "❌ لا يمكنك تسجيل الحضور في هذه الحصة.\n\n"
                f"📚 الحصة: "
                f"{lesson['grade']} - "
                f"{lesson['group_name']}\n\n"
                f"👨‍🎓 حسابك: "
                f"{student['grade']} - "
                f"{student['group_name']}"
            ),
        )

    conn = db()

    try:

        existing = conn.execute(
            """
            SELECT marked_at
            FROM attendance
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if existing:

            return (
                True,
                (
                    "✅ حضورك مسجل بالفعل.\n\n"
                    f"🕐 {existing['marked_at']}"
                ),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO
            lesson_students
            (
                lesson_id,
                student_id
            )
            VALUES (?, ?)
            """,
            (
                lesson["id"],
                student_id,
            ),
        )

        stamp = now()

        conn.execute(
            """
            INSERT INTO attendance
            (
                lesson_id,
                student_id,
                marked_at
            )
            VALUES (?, ?, ?)
            """,
            (
                lesson["id"],
                student_id,
                stamp,
            ),
        )

        conn.commit()

        return (
            True,
            (
                "🎉 تم تسجيل حضورك بنجاح.\n\n"
                f"🕐 {stamp}"
            ),
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except Exception as exc:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ: {exc}",
        )

    finally:

        conn.close()


# =========================================================
# STUDENT REGISTER
# =========================================================

def student_register():

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    st.info(
        """
👋 سجل بياناتك مرة واحدة فقط.

بعدها يمكنك الدخول في أي وقت.
        """
    )

    with st.form(
        "student_register_form"
    ):

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
            GRADES,
        )

        group = st.selectbox(
            "👥 المجموعة",
            GROUPS,
        )

        st.info(
            f"👥 {group}: "
            f"{group_count(grade, group)}"
            f"/{GROUP_LIMIT} طالب"
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submit:

        return

    name = name.strip()
    phone = clean_phone(phone)
    parent_phone = clean_phone(parent_phone)

    if not name:

        st.error(
            "❌ اكتب اسم الطالب."
        )

        return

    if len(phone) < 8:

        st.error(
            "❌ رقم الهاتف غير صحيح."
        )

        return

    conn = db()

    try:

        old = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            """,
            (phone,),
        ).fetchone()

        if old:

            st.session_state.student_id = (
                old["id"]
            )

            st.query_params["page"] = (
                "student"
            )

            st.query_params["student"] = (
                str(old["id"])
            )

            st.rerun()

        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()[0]

        if count >= GROUP_LIMIT:

            st.error(
                "❌ هذه المجموعة مكتملة."
            )

            return

        cursor = conn.execute(
            """
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
            """,
            (
                name,
                phone,
                parent_phone,
                grade,
                group,
                now(),
            ),
        )

        conn.commit()

        student_id = cursor.lastrowid

        st.session_state.student_id = (
            student_id
        )

        st.query_params["page"] = (
            "student"
        )

        st.query_params["student"] = (
            str(student_id)
        )

        st.rerun()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    except Exception as exc:

        conn.rollback()

        st.error(
            f"❌ حدث خطأ: {exc}"
        )

    finally:

        conn.close()


# =========================================================
# STUDENT LOGIN
# =========================================================

def student_login():

    header(
        "🎓 منصة الحضور",
        "🔐 دخول الطالب",
    )

    st.info(
        "👨‍🎓 إذا كنت مسجلاً من قبل، اكتب رقم هاتفك للدخول."
    )

    with st.form(
        "student_login_form"
    ):

        phone = st.text_input(
            "📱 رقم الهاتف"
        )

        submit = st.form_submit_button(
            "🔓 دخول",
            use_container_width=True,
        )

    if not submit:

        return

    phone = clean_phone(phone)

    if len(phone) < 8:

        st.error(
            "❌ رقم الهاتف غير صحيح."
        )

        return

    student = get_student_by_phone(
        phone
    )

    if not student:

        st.error(
            "❌ لا يوجد حساب بهذا الرقم."
        )

        return

    st.session_state.student_id = (
        student["id"]
    )

    st.query_params["page"] = (
        "student"
    )

    st.query_params["student"] = (
        str(student["id"])
    )

    st.rerun()


# =========================================================
# STUDENT HISTORY
# =========================================================

def get_student_attendance(
    student_id,
):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT
                l.lesson_name,
                l.grade,
                l.group_name,
                l.created_at,
                l.ended_at,
                a.marked_at

            FROM lesson_students ls

            JOIN lessons l
            ON l.id = ls.lesson_id

            LEFT JOIN attendance a
            ON a.lesson_id = l.id
            AND a.student_id = ls.student_id

            WHERE ls.student_id = ?
            AND l.active = 0

            ORDER BY l.id DESC
            """,
            (student_id,),
        ).fetchall()

    finally:

        conn.close()


def student_stats(
    student_id,
):

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM lesson_students ls

            JOIN lessons l
            ON l.id = ls.lesson_id

            WHERE ls.student_id = ?
            AND l.active = 0
            """,
            (student_id,),
        ).fetchone()[0]

        present = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance a

            JOIN lessons l
            ON l.id = a.lesson_id

            WHERE a.student_id = ?
            AND l.active = 0
            """,
            (student_id,),
        ).fetchone()[0]

        absent = total - present

        percentage = (
            present / total * 100
            if total
            else 0
        )

        return (
            total,
            present,
            absent,
            percentage,
        )

    finally:

        conn.close()


# =========================================================
# STUDENT PROFILE
# =========================================================

def student_profile(
    student,
):

    st.subheader(
        "👤 بيانات الطالب"
    )

    c1, c2 = st.columns(2)

    with c1:

        st.write(
            f"**👨‍🎓 الاسم:** "
            f"{student['name']}"
        )

        st.write(
            f"**🎓 الصف:** "
            f"{student['grade']}"
        )

    with c2:

        st.write(
            f"**👥 المجموعة:** "
            f"{student['group_name']}"
        )

        st.write(
            f"**📱 الهاتف:** "
            f"{student['phone']}"
        )

    st.divider()

    (
        total,
        present,
        absent,
        percentage,
    ) = student_stats(
        student["id"]
    )

    st.subheader(
        "📊 إحصائيات الحضور"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "📚 الحصص",
        total,
    )

    c2.metric(
        "✅ الحضور",
        present,
    )

    c3.metric(
        "❌ الغياب",
        absent,
    )

    c4.metric(
        "📈 النسبة",
        f"{percentage:.1f}%",
    )


# =========================================================
# STUDENT HISTORY PAGE
# =========================================================

def student_history(
    student,
):

    st.subheader(
        "📋 سجل الحضور والغياب"
    )

    rows = get_student_attendance(
        student["id"]
    )

    if not rows:

        st.info(
            "📭 لا توجد حصص منتهية حتى الآن."
        )

        return

    table = []

    for row in rows:

        table.append(
            {
                "الحصة":
                    row["lesson_name"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "تاريخ الحصة":
                    row["created_at"],

                "الحالة":
                    (
                        "✅ حاضر"
                        if row["marked_at"]
                        else "❌ غائب"
                    ),

                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENT ATTENDANCE
# =========================================================

def student_attendance_page(
    student,
):

    st.subheader(
        "📷 تسجيل الحضور"
    )

    st.info(
        "📱 وجّه الكاميرا إلى QR الموجود عند المدرس."
    )

    photo = st.camera_input(
        "📷 امسح QR الحصة",
        key="student_camera",
    )

    if photo:

        raw = decode_qr(
            photo.getvalue()
        )

        if not raw:

            st.error(
                "❌ لم يتم قراءة QR. جرّب تقريب الكاميرا وتحسين الإضاءة."
            )

        else:

            token = extract_token(
                raw
            )

            lesson = get_lesson_by_token(
                token
            )

            if not lesson:

                st.error(
                    "❌ الحصة غير موجودة أو انتهت."
                )

            else:

                st.info(
                    f"""
📚 الحصة: {lesson['lesson_name']}

🎓 الصف: {lesson['grade']}

👥 المجموعة: {lesson['group_name']}
                    """
                )

                ok, message = mark_attendance(
                    token,
                    student["id"],
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

    st.divider()

    st.subheader(
        "🔗 تسجيل الحضور بالرابط"
    )

    manual = st.text_input(
        "🔗 الصق رابط الحصة هنا",
        key="manual_lesson_link",
    )

    if st.button(
        "✅ تسجيل الحضور بالرابط",
        use_container_width=True,
        key="manual_attendance_button",
    ):

        token = extract_token(
            manual
        )

        if not token:

            st.error(
                "❌ الرابط غير صحيح."
            )

        else:

            ok, message = mark_attendance(
                token,
                student["id"],
            )

            if ok:

                st.success(
                    message
                )

            else:

                st.error(
                    message
                )


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    sid = get_student_id()

    if sid is None:

        login_tab, register_tab = (
            st.tabs(
                [
                    "🔐 دخول الطالب",
                    "📝 تسجيل لأول مرة",
                ]
            )
        )

        with login_tab:

            student_login()

        with register_tab:

            student_register()

        return

    student = get_student(
        sid
    )

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

        return

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    st.success(
        f"""
👨‍🎓 {student['name']}

🎓 {student['grade']}

👥 {student['group_name']}
        """
    )

    tab1, tab2, tab3 = st.tabs(
        [
            "📷 تسجيل الحضور",
            "👤 حسابي",
            "📋 سجل الحضور",
        ]
    )

    with tab1:

        student_attendance_page(
            student
        )

    with tab2:

        student_profile(
            student
        )

    with tab3:

        student_history(
            student
        )

    if st.button(
        "🚪 تسجيل خروج الطالب",
        use_container_width=True,
        key="student_logout",
    ):

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    password = st.text_input(
        "🔐 كلمة مرور المدرس",
        type="password",
        key="teacher_password",
    )

    if st.button(
        "👨‍🏫 دخول",
        use_container_width=True,
        key="teacher_login_button",
    ):

        if password == TEACHER_PASSWORD:

            st.session_state.teacher = True

            st.rerun()

        else:

            st.error(
                "❌ كلمة المرور غير صحيحة."
            )


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 اختر الصف",
        GRADES,
        key="lesson_grade",
    )

    cols = st.columns(3)

    for i, group in enumerate(GROUPS):

        cols[i].metric(
            group,
            f"{group_count(grade, group)}/{GROUP_LIMIT}",
        )

    group = st.selectbox(
        "👥 اختر المجموعة",
        GROUPS,
        key="lesson_group",
    )

    count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 عدد طلاب {group}: "
        f"{count}/{GROUP_LIMIT}"
    )

    name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
        key="start_lesson",
    ):

        if count == 0:

            st.error(
                "❌ لا يوجد طلاب في هذه المجموعة."
            )

            return

        conn = db()

        try:

            conn.execute(
                """
                UPDATE lessons
                SET active = 0,
                    ended_at = ?
                WHERE active = 1
                AND grade = ?
                AND group_name = ?
                """,
                (
                    now(),
                    grade,
                    group,
                ),
            )

            token = secrets.token_urlsafe(
                32
            )

            cursor = conn.execute(
                """
                INSERT INTO lessons
                (
                    lesson_name,
                    grade,
                    group_name,
                    token,
                    created_at,
                    active
                )
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    name.strip()
                    or "الحصة الحالية",
                    grade,
                    group,
                    token,
                    now(),
                ),
            )

            lesson_id = cursor.lastrowid

            rows = conn.execute(
                """
                SELECT id
                FROM students
                WHERE grade = ?
                AND group_name = ?
                """,
                (
                    grade,
                    group,
                ),
            ).fetchall()

            conn.executemany(
                """
                INSERT OR IGNORE INTO
                lesson_students
                (
                    lesson_id,
                    student_id
                )
                VALUES (?, ?)
                """,
                [
                    (
                        lesson_id,
                        row["id"],
                    )
                    for row in rows
                ],
            )

            conn.commit()

            st.success(
                "🎉 تم بدء الحصة بنجاح."
            )

            st.rerun()

        except Exception as exc:

            conn.rollback()

            st.error(
                f"❌ حدث خطأ: {exc}"
            )

        finally:

            conn.close()


# =========================================================
# CURRENT LESSONS
# =========================================================

def current_lessons():

    st.subheader(
        "📊 الحصص الحالية"
    )

    lessons = get_active_lessons()

    if not lessons:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    labels = [
        f"#{x['id']} | "
        f"{x['grade']} | "
        f"{x['group_name']} | "
        f"{x['lesson_name']}"
        for x in lessons
    ]

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="current_lesson_select",
    )

    lesson = lessons[
        labels.index(selected)
    ]

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson["id"],),
        ).fetchone()[0]

        present = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE lesson_id = ?
            """,
            (lesson["id"],),
        ).fetchone()[0]

        rows = conn.execute(
            """
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
            """,
            (lesson["id"],),
        ).fetchall()

    finally:

        conn.close()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 الطلاب",
        total,
    )

    c2.metric(
        "✅ حضر",
        present,
    )

    c3.metric(
        "⏳ لم يسجل",
        total - present,
    )

    st.write(
        f"🎓 **الصف:** {lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** {lesson['group_name']}"
    )

    st.write(
        f"📚 **الحصة:** {lesson['lesson_name']}"
    )

    st.write(
        f"🕐 **بدأت:** {lesson['created_at']}"
    )

    # QR

    link = lesson_url(
        lesson["token"]
    )

    qr = qrcode.QRCode(
        error_correction=(
            qrcode.constants
            .ERROR_CORRECT_H
        ),
        box_size=12,
        border=5,
    )

    qr.add_data(link)

    qr.make(
        fit=True
    )

    buffer = io.BytesIO()

    qr.make_image().save(
        buffer,
        format="PNG",
    )

    st.subheader(
        "📷 QR الحضور"
    )

    st.image(
        buffer.getvalue(),
        width=400,
        caption="📷 QR الحضور",
    )

    st.subheader(
        "🔗 رابط الحصة"
    )

    st.code(
        link,
        language="text",
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الحالة":
                    (
                        "✅ حاضر"
                        if row["marked_at"]
                        else "⏳ لم يسجل"
                    ),

                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "🔄 تحديث الحضور",
            use_container_width=True,
            key=f"refresh_{lesson['id']}",
        ):

            st.rerun()

    with col2:

        if st.button(
            "⛔ إنهاء الحصة وحفظ الغياب",
            use_container_width=True,
            key=f"end_{lesson['id']}",
        ):

            conn = db()

            try:

                conn.execute(
                    """
                    UPDATE lessons
                    SET active = 0,
                        ended_at = ?
                    WHERE id = ?
                    """,
                    (
                        now(),
                        lesson["id"],
                    ),
                )

                conn.commit()

            finally:

                conn.close()

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports():

    st.subheader(
        "📋 التقارير"
    )

    conn = db()

    try:

        lessons = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 0
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()

    if not lessons:

        st.info(
            "📭 لا توجد حصص منتهية."
        )

        return

    labels = [
        f"#{x['id']} | "
        f"{x['grade']} | "
        f"{x['group_name']} | "
        f"{x['lesson_name']} | "
        f"{x['created_at']}"
        for x in lessons
    ]

    selected = st.selectbox(
        "اختر الحصة",
        labels,
        key="report_lesson",
    )

    lesson = lessons[
        labels.index(selected)
    ]

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                s.name,
                s.phone,
                s.grade,
                s.group_name,
                a.marked_at

            FROM lesson_students ls

            JOIN students s
            ON s.id = ls.student_id

            LEFT JOIN attendance a
            ON a.lesson_id = ls.lesson_id
            AND a.student_id = ls.student_id

            WHERE ls.lesson_id = ?

            ORDER BY s.name
            """,
            (lesson["id"],),
        ).fetchall()

    finally:

        conn.close()

    total = len(rows)

    present = sum(
        1
        for row in rows
        if row["marked_at"]
    )

    absent = total - present

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total,
    )

    c2.metric(
        "✅ الحضور",
        present,
    )

    c3.metric(
        "❌ الغياب",
        absent,
    )

    table = []

    for row in rows:

        table.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "الحالة":
                    (
                        "✅ حاضر"
                        if row["marked_at"]
                        else "❌ غائب"
                    ),

                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STATISTICS
# =========================================================

def statistics():

    st.subheader(
        "📈 إحصائيات الطلاب"
    )

    table = []

    for grade in GRADES:

        for group in GROUPS:

            count = group_count(
                grade,
                group,
            )

            table.append(
                {
                    "الصف":
                        grade,

                    "المجموعة":
                        group,

                    "الطلاب":
                        count,

                    "السعة":
                        GROUP_LIMIT,

                    "المتبقي":
                        GROUP_LIMIT - count,
                }
            )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# STUDENTS
# =========================================================

def students():

    st.subheader(
        "👨‍🎓 الطلاب المسجلون"
    )

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                id,
                name,
                phone,
                parent_phone,
                grade,
                group_name,
                created_at

            FROM students

            ORDER BY
                grade,
                group_name,
                name
            """
        ).fetchall()

    finally:

        conn.close()

    st.metric(
        "👨‍🎓 إجمالي الطلاب",
        len(rows),
    )

    search = st.text_input(
        "🔎 ابحث بالاسم أو رقم الهاتف",
        key="student_search",
    )

    search = search.strip()

    filtered = [
        row
        for row in rows
        if (
            not search
            or search.lower()
            in row["name"].lower()
            or search
            in row["phone"]
        )
    ]

    st.caption(
        f"عرض {len(filtered)} "
        f"من {len(rows)} طالب"
    )

    table = []

    for row in filtered:

        table.append(
            {
                "ID":
                    row["id"],

                "الاسم":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "ولي الأمر":
                    row["parent_phone"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "تاريخ التسجيل":
                    row["created_at"],
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# DASHBOARD
# =========================================================

def dashboard():

    conn = db()

    try:

        total_students = conn.execute(
            """
            SELECT COUNT(*)
            FROM students
            """
        ).fetchone()[0]

        total_lessons = conn.execute(
            """
            SELECT COUNT(*)
            FROM lessons
            """
        ).fetchone()[0]

        active_lessons = conn.execute(
            """
            SELECT COUNT(*)
            FROM lessons
            WHERE active = 1
            """
        ).fetchone()[0]

        ended_lessons = conn.execute(
            """
            SELECT COUNT(*)
            FROM lessons
            WHERE active = 0
            """
        ).fetchone()[0]

        total_attendance = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            """
        ).fetchone()[0]

        ended_students = conn.execute(
            """
            SELECT COUNT(*)
            FROM lesson_students ls

            JOIN lessons l
            ON l.id = ls.lesson_id

            WHERE l.active = 0
            """
        ).fetchone()[0]

    finally:

        conn.close()

    total_absent = max(
        0,
        ended_students - total_attendance,
    )

    st.subheader(
        "📊 لوحة التحكم الرئيسية"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total_students,
    )

    c2.metric(
        "📚 إجمالي الحصص",
        total_lessons,
    )

    c3.metric(
        "🟢 حصص مفتوحة",
        active_lessons,
    )

    c4.metric(
        "⛔ حصص منتهية",
        ended_lessons,
    )

    c1, c2 = st.columns(2)

    c1.metric(
        "✅ إجمالي مرات الحضور",
        total_attendance,
    )

    c2.metric(
        "❌ إجمالي الغياب",
        total_absent,
    )

    st.divider()

    st.subheader(
        "📚 توزيع الطلاب"
    )

    table = []

    for grade in GRADES:

        for group in GROUPS:

            count = group_count(
                grade,
                group,
            )

            if count:

                table.append(
                    {
                        "الصف":
                            grade,

                        "المجموعة":
                            group,

                        "عدد الطلاب":
                            count,

                        "المتبقي":
                            GROUP_LIMIT - count,
                    }
                )

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "📭 لم يتم تسجيل طلاب حتى الآن."
        )


# =========================================================
# TEACHER DASHBOARD
# =========================================================

def teacher_dashboard():

    if not st.session_state.get(
        "teacher",
        False,
    ):

        teacher_login()

        return

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    if st.button(
        "🚪 تسجيل خروج المدرس",
        key="teacher_logout",
    ):

        st.session_state.teacher = False

        st.rerun()

    tabs = st.tabs(
        [
            "📊 الرئيسية",
            "➕ إنشاء حصة",
            "📊 الحصص الحالية",
            "📋 التقارير",
            "📈 الإحصائيات",
            "👨‍🎓 الطلاب",
        ]
    )

    with tabs[0]:

        dashboard()

    with tabs[1]:

        create_lesson()

    with tabs[2]:

        current_lessons()

    with tabs[3]:

        reports()

    with tabs[4]:

        statistics()

    with tabs[5]:

        students()

    st.divider()

    st.subheader(
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text",
    )

    st.info(
        """
📱 ابعت الرابط للطلاب.

الطالب يسجل مرة واحدة،
وبعدها يدخل بحسابه ويمسح QR أي حصة
خاصة بصفه ومجموعته.
        """
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    page = st.query_params.get(
        "page",
        "teacher",
    )

    if page == "student":

        student_page()

    else:

        teacher_dashboard()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
