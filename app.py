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
        max-width: 1100px;
        padding-top: 25px;
        padding-bottom: 50px;
    }

    .main-title {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        font-size: 25px;
        margin-bottom: 30px;
    }

    .student-card {
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #444;
        margin-bottom: 20px;
    }

    div.stButton > button {
        border-radius: 12px;
        min-height: 48px;
        font-size: 17px;
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

    conn.execute(
        "PRAGMA foreign_keys=ON"
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


# =========================================================
# STUDENT SESSION
# =========================================================

def get_student_id():

    # أولاً: Session State
    sid = st.session_state.get(
        "student_id"
    )

    if sid is not None:

        try:

            sid = int(sid)

            if get_student(sid):

                return sid

        except:

            pass

    # ثانياً: الرابط
    sid = st.query_params.get(
        "student"
    )

    if sid:

        try:

            sid = int(sid)

            student = get_student(
                sid
            )

            if student:

                st.session_state.student_id = sid
                st.session_state.student_logged_in = True

                return sid

        except:

            pass

    return None


def login_student(student_id):

    st.session_state.student_id = int(
        student_id
    )

    st.session_state.student_logged_in = True

    st.query_params["page"] = "student"

    st.query_params["student"] = str(
        student_id
    )


def logout_student():

    st.session_state.pop(
        "student_id",
        None,
    )

    st.session_state.pop(
        "student_logged_in",
        None,
    )

    st.session_state.pop(
        "attendance_message",
        None,
    )

    st.session_state.pop(
        "attendance_lesson_id",
        None,
    )

    st.query_params.clear()


# =========================================================
# URL
# =========================================================

def get_base_url():

    try:

        current = st.context.url

        if current:

            parsed = urlparse(current)

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    except:

        pass

    return ""


def student_url():

    base = get_base_url()

    if base:

        return f"{base}?page=student"

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
# HEADER
# =========================================================

def header(
    title,
    subtitle,
):

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
# GROUP COUNT
# =========================================================

def group_count(
    grade,
    group,
):

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()

        return row["total"]

    finally:

        conn.close()


# =========================================================
# LESSONS
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


def get_lesson_by_id(lesson_id):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE id = ?
            LIMIT 1
            """,
            (lesson_id,),
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

    # Token فقط
    if (
        "://" not in value
        and "lesson=" not in value
    ):

        return value

    try:

        parsed = urlparse(value)

        query = parse_qs(
            parsed.query
        )

        result = query.get(
            "lesson"
        )

        if result:

            return unquote(
                result[0]
            ).strip()

    except:

        pass

    match = re.search(
        r"(?:lesson=)([^&#\s]+)",
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

        attempts = []

        attempts.append(image)

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        attempts.append(gray)

        # تحسين التباين
        equalized = cv2.equalizeHist(
            gray
        )

        attempts.append(equalized)

        # تكبير الصورة
        h, w = gray.shape[:2]

        if h > 0 and w > 0:

            resized = cv2.resize(
                gray,
                (
                    w * 2,
                    h * 2,
                ),
                interpolation=cv2.INTER_CUBIC,
            )

            attempts.append(resized)

        # Threshold
        _, threshold = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY
            + cv2.THRESH_OTSU,
        )

        attempts.append(threshold)

        for img in attempts:

            try:

                value, points, _ = (
                    detector.detectAndDecode(
                        img
                    )
                )

                if value:

                    return value.strip()

            except:

                pass

        return None

    except:

        return None


# =========================================================
# CHECK ATTENDANCE
# =========================================================

def already_attended(
    lesson_id,
    student_id,
):

    conn = db()

    try:

        row = conn.execute(
            """
            SELECT marked_at
            FROM attendance
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson_id,
                student_id,
            ),
        ).fetchone()

        return row

    finally:

        conn.close()


# =========================================================
# MARK ATTENDANCE
# =========================================================

def mark_attendance(
    token,
    student_id,
):

    token = extract_token(token)

    if not token:

        return (
            False,
            "❌ QR غير صحيح.",
        )

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

    # =====================================================
    # CHECK GRADE
    # =====================================================

    if (
        student["grade"]
        != lesson["grade"]
    ):

        return (
            False,
            f"""
❌ لا يمكنك تسجيل الحضور في هذه الحصة.

🎓 الحصة: {lesson['grade']}

🎓 أنت مسجل في: {student['grade']}
            """,
        )

    # =====================================================
    # CHECK GROUP
    # =====================================================

    if (
        student["group_name"]
        != lesson["group_name"]
    ):

        return (
            False,
            f"""
❌ هذه الحصة ليست لمجموعتك.

👥 مجموعة الحصة: {lesson['group_name']}

👥 مجموعتك: {student['group_name']}
            """,
        )

    conn = db()

    try:

        # إضافة الطالب إلى كشف الحصة
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

        # هل سجل بالفعل؟
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

            conn.commit()

            return (
                True,
                f"""
✅ حضورك مسجل بالفعل.

🕐 وقت التسجيل:
{existing['marked_at']}
                """,
            )

        # تسجيل الحضور
        attendance_time = now()

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
                attendance_time,
            ),
        )

        conn.commit()

        return (
            True,
            f"""
🎉 تم تسجيل حضورك بنجاح.

📚 الحصة: {lesson['lesson_name']}

🕐 الوقت: {attendance_time}
            """,
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return (
            True,
            "✅ حضورك مسجل بالفعل.",
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            f"❌ حدث خطأ: {e}",
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
👋 التسجيل يتم مرة واحدة فقط.

بعد التسجيل تقدر تدخل حسابك في أي وقت.
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

        count = group_count(
            grade,
            group,
        )

        st.info(
            f"👥 {group}: "
            f"{count}/{GROUP_LIMIT} طالب"
        )

        submit = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submit:
        return

    name = name.strip()

    phone = clean_phone(
        phone
    )

    parent_phone = clean_phone(
        parent_phone
    )

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

            login_student(
                old["id"]
            )

            st.success(
                "✅ الحساب موجود بالفعل، تم الدخول إليه."
            )

            st.rerun()

        count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            WHERE grade = ?
            AND group_name = ?
            """,
            (
                grade,
                group,
            ),
        ).fetchone()["total"]

        if count >= GROUP_LIMIT:

            st.error(
                "❌ المجموعة مكتملة."
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

        login_student(
            student_id
        )

        st.success(
            "🎉 تم إنشاء حسابك بنجاح."
        )

        st.rerun()

    except sqlite3.IntegrityError:

        conn.rollback()

        st.error(
            "❌ رقم الهاتف مسجل بالفعل."
        )

    except Exception as e:

        conn.rollback()

        st.error(
            f"❌ {e}"
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
        """
👨‍🎓 لو سجلت قبل كده،
اكتب رقم الهاتف للدخول إلى حسابك.
        """
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

    phone = clean_phone(
        phone
    )

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
            """
❌ لا يوجد حساب بهذا الرقم.

استخدم تسجيل طالب جديد.
            """
        )

        return

    login_student(
        student["id"]
    )

    st.success(
        "✅ تم تسجيل الدخول."
    )

    st.rerun()


# =========================================================
# STUDENT ATTENDANCE HISTORY
# =========================================================

def get_student_attendance(
    student_id
):

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                l.id AS lesson_id,
                l.lesson_name,
                l.grade,
                l.group_name,
                l.created_at,
                l.ended_at,
                l.active,
                a.marked_at

            FROM lesson_students ls

            JOIN lessons l
            ON l.id = ls.lesson_id

            LEFT JOIN attendance a
            ON a.lesson_id = l.id
            AND a.student_id = ls.student_id

            WHERE ls.student_id = ?

            ORDER BY
                l.id DESC
            """,
            (student_id,),
        ).fetchall()

        return rows

    finally:

        conn.close()


# =========================================================
# STUDENT STATS
# =========================================================

def student_stats(
    student_id
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
            if total > 0
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
    student
):

    st.subheader(
        "👤 حساب الطالب"
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

    total, present, absent, percentage = (
        student_stats(
            student["id"]
        )
    )

    st.subheader(
        "📊 إحصائيات الحضور"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "📚 الحصص المنتهية",
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
        "📈 نسبة الحضور",
        f"{percentage:.1f}%",
    )


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    student_id = get_student_id()

    # =====================================================
    # LOGIN / REGISTER
    # =====================================================

    if student_id is None:

        login_tab, register_tab = st.tabs(
            [
                "🔐 دخول الطالب",
                "📝 تسجيل لأول مرة",
            ]
        )

        with login_tab:

            student_login()

        with register_tab:

            student_register()

        return

    student = get_student(
        student_id
    )

    if not student:

        logout_student()

        st.rerun()

    # =====================================================
    # STUDENT CARD
    # =====================================================

    st.success(
        f"""
👨‍🎓 {student['name']}

🎓 {student['grade']}

👥 {student['group_name']}
        """
    )

    # =====================================================
    # DIRECT LESSON LINK
    # =====================================================

    direct_token = extract_token(
        st.query_params.get(
            "lesson"
        )
    )

    direct_lesson = None

    if direct_token:

        direct_lesson = get_lesson_by_token(
            direct_token
        )

        if direct_lesson:

            st.info(
                f"""
📚 الحصة الحالية:
{direct_lesson['lesson_name']}

🎓 الصف:
{direct_lesson['grade']}

👥 المجموعة:
{direct_lesson['group_name']}
                """
            )

    tabs = st.tabs(
        [
            "📷 تسجيل الحضور",
            "👤 حسابي",
            "📋 سجل الحضور",
        ]
    )

    # =====================================================
    # ATTENDANCE TAB
    # =====================================================

    with tabs[0]:

        st.subheader(
            "📷 تسجيل الحضور"
        )

        st.info(
            """
📱 وجّه الكاميرا إلى QR الموجود عند المدرس.

النظام سيتأكد تلقائياً من:
• الصف
• المجموعة
• الحصة
• تسجيل الحضور مرة واحدة فقط
            """
        )

        # -------------------------------------------------
        # SUCCESS MESSAGE
        # -------------------------------------------------

        saved_message = st.session_state.get(
            "attendance_message"
        )

        if saved_message:

            st.success(
                saved_message
            )

            st.balloons()

            if st.button(
                "📷 مسح QR لحصة أخرى",
                use_container_width=True,
            ):

                st.session_state.pop(
                    "attendance_message",
                    None,
                )

                st.session_state.pop(
                    "attendance_lesson_id",
                    None,
                )

                st.rerun()

            st.divider()

        # -------------------------------------------------
        # CAMERA
        # -------------------------------------------------

        photo = st.camera_input(
            "📷 امسح QR الحصة",
            key="student_camera",
        )

        if photo and not saved_message:

            raw = decode_qr(
                photo.getvalue()
            )

            if not raw:

                st.error(
                    """
❌ لم يتم قراءة QR.

حاول:
• تقريب الكاميرا
• إظهار الكود بالكامل
• زيادة الإضاءة
• عدم اهتزاز الهاتف
                    """
                )

            else:

                token = extract_token(
                    raw
                )

                if not token:

                    st.error(
                        "❌ QR غير صالح."
                    )

                else:

                    lesson = get_lesson_by_token(
                        token
                    )

                    if not lesson:

                        st.error(
                            """
❌ هذه الحصة غير موجودة
أو تم إنهاؤها.
                            """
                        )

                    else:

                        st.info(
                            f"""
📚 الحصة:
{lesson['lesson_name']}

🎓 الصف:
{lesson['grade']}

👥 المجموعة:
{lesson['group_name']}
                            """
                        )

                        # تحقق قبل الإدخال
                        old_attendance = (
                            already_attended(
                                lesson["id"],
                                student["id"],
                            )
                        )

                        if old_attendance:

                            st.session_state[
                                "attendance_message"
                            ] = (
                                f"""
✅ حضورك مسجل بالفعل.

📚 {lesson['lesson_name']}

🕐 {old_attendance['marked_at']}
                                """
                            )

                            st.rerun()

                        ok, message = (
                            mark_attendance(
                                token,
                                student["id"],
                            )
                        )

                        if ok:

                            st.session_state[
                                "attendance_message"
                            ] = message

                            st.session_state[
                                "attendance_lesson_id"
                            ] = lesson["id"]

                            st.rerun()

                        else:

                            st.error(
                                message
                            )

        st.divider()

        # =================================================
        # MANUAL LINK
        # =================================================

        st.subheader(
            "🔗 تسجيل الحضور بالرابط"
        )

        st.caption(
            "لو الكاميرا لم تقرأ QR، الصق رابط الحصة هنا."
        )

        manual = st.text_input(
            "🔗 رابط الحصة",
            key="manual_lesson_link",
        )

        if st.button(
            "✅ تسجيل الحضور بالرابط",
            use_container_width=True,
        ):

            token = extract_token(
                manual
            )

            if not token:

                st.error(
                    "❌ الرابط غير صحيح."
                )

            else:

                ok, message = (
                    mark_attendance(
                        token,
                        student["id"],
                    )
                )

                if ok:

                    st.session_state[
                        "attendance_message"
                    ] = message

                    st.rerun()

                else:

                    st.error(
                        message
                    )

        # =================================================
        # DIRECT LINK ATTENDANCE
        # =================================================

        if direct_lesson:

            st.divider()

            st.subheader(
                "⚡ الحصة المفتوحة"
            )

            if (
                direct_lesson["grade"]
                == student["grade"]
                and
                direct_lesson["group_name"]
                == student["group_name"]
            ):

                if st.button(
                    "🟢 تسجيل حضوري في هذه الحصة",
                    use_container_width=True,
                ):

                    ok, message = (
                        mark_attendance(
                            direct_lesson["token"],
                            student["id"],
                        )
                    )

                    if ok:

                        st.session_state[
                            "attendance_message"
                        ] = message

                        st.rerun()

                    else:

                        st.error(
                            message
                        )

            else:

                st.error(
                    """
❌ هذه الحصة ليست لصفك أو مجموعتك.
                    """
                )

    # =====================================================
    # PROFILE TAB
    # =====================================================

    with tabs[1]:

        student_profile(
            student
        )

    # =====================================================
    # HISTORY TAB
    # =====================================================

    with tabs[2]:

        st.subheader(
            "📋 سجل الحضور والغياب"
        )

        rows = get_student_attendance(
            student["id"]
        )

        if not rows:

            st.info(
                "📭 لا توجد حصص مسجلة حتى الآن."
            )

        else:

            table = []

            for row in rows:

                # الحصة ما زالت مفتوحة
                if row["active"] == 1:

                    if row["marked_at"]:

                        status = "🟢 حاضر - الحصة مفتوحة"

                    else:

                        status = "⏳ لم يسجل بعد"

                    attendance_time = (
                        row["marked_at"]
                        or "-"
                    )

                # الحصة انتهت
                else:

                    if row["marked_at"]:

                        status = "✅ حاضر"

                        attendance_time = (
                            row["marked_at"]
                        )

                    else:

                        status = "❌ غائب"

                        attendance_time = "-"

                table.append(
                    {
                        "الحصة":
                            row["lesson_name"],

                        "التاريخ":
                            row["created_at"],

                        "الحالة":
                            status,

                        "وقت الحضور":
                            attendance_time,
                    }
                )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    if st.button(
        "🚪 تسجيل خروج الطالب",
        use_container_width=True,
    ):

        logout_student()

        st.rerun()


# =========================================================
# TEACHER LOGIN
# =========================================================

def teacher_login():

    header(
        "🎓 منصة الحضور",
        "👨‍🏫 لوحة تحكم المدرس",
    )

    st.info(
        "🔐 أدخل كلمة مرور المدرس."
    )

    password = st.text_input(
        "🔐 كلمة المرور",
        type="password",
    )

    if st.button(
        "👨‍🏫 دخول",
        use_container_width=True,
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
        "🎓 الصف",
        GRADES,
        key="lesson_grade",
    )

    st.write(
        "👥 عدد الطلاب في مجموعات الصف"
    )

    cols = st.columns(3)

    for i, group in enumerate(
        GROUPS
    ):

        count = group_count(
            grade,
            group,
        )

        cols[i].metric(
            group,
            f"{count}/{GROUP_LIMIT}",
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
        f"👨‍🎓 عدد الطلاب: "
        f"{count}/{GROUP_LIMIT}"
    )

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
        key="new_lesson_name",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if count == 0:

            st.error(
                """
❌ لا يوجد طلاب في هذه المجموعة.

سجل الطلاب أولاً.
                """
            )

            return

        conn = db()

        try:

            # إنهاء أي حصة قديمة
            # لنفس الصف والمجموعة

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
                    lesson_name.strip()
                    or "الحصة الحالية",
                    grade,
                    group,
                    token,
                    now(),
                ),
            )

            lesson_id = cursor.lastrowid

            # إضافة كل طلاب المجموعة
            students_rows = conn.execute(
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

            for student in students_rows:

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
                        lesson_id,
                        student["id"],
                    ),
                )

            conn.commit()

            st.success(
                "🎉 تم بدء الحصة بنجاح."
            )

            st.rerun()

        except Exception as e:

            conn.rollback()

            st.error(
                f"❌ {e}"
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

    labels = []

    for lesson in lessons:

        labels.append(
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']}"
        )

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

    waiting = total - present

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
        waiting,
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

    # =====================================================
    # QR
    # =====================================================

    link = lesson_url(
        lesson["token"]
    )

    st.subheader(
        "📷 QR الحضور"
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            qrcode.constants
            .ERROR_CORRECT_H
        ),
        box_size=12,
        border=5,
    )

    qr.add_data(
        link
    )

    qr.make(
        fit=True
    )

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
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

    # =====================================================
    # STUDENT TABLE
    # =====================================================

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time_value = (
                row["marked_at"]
            )

        else:

            status = "⏳ لم يسجل"

            time_value = "-"

        table.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الحالة":
                    status,

                "وقت الحضور":
                    time_value,
            }
        )

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    if table:

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب."
        )

    # =====================================================
    # REFRESH
    # =====================================================

    if st.button(
        "🔄 تحديث الحضور",
        use_container_width=True,
        key=f"refresh_{lesson['id']}",
    ):

        st.rerun()

    # =====================================================
    # END LESSON
    # =====================================================

    st.divider()

    st.warning(
        """
⚠️ عند إنهاء الحصة سيتم اعتبار كل طالب
لم يسجل حضوراً = غائب.
        """
    )

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

        except Exception as e:

            conn.rollback()

            st.error(
                f"❌ {e}"
            )

            return

        finally:

            conn.close()

        st.success(
            """
✅ تم إنهاء الحصة.

الطلاب الذين لم يسجلوا حضورهم
أصبحوا غائبين في التقرير.
            """
        )

        st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports():

    st.subheader(
        "📋 تقارير الحضور والغياب"
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

    labels = []

    for lesson in lessons:

        labels.append(
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

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

    percentage = (
        present / total * 100
        if total
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "👨‍🎓 الطلاب",
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
        "📈 نسبة الحضور",
        f"{percentage:.1f}%",
    )

    table = []

    for row in rows:

        if row["marked_at"]:

            status = "✅ حاضر"

            time_value = (
                row["marked_at"]
            )

        else:

            status = "❌ غائب"

            time_value = "-"

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
                    status,

                "وقت الحضور":
                    time_value,
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
                        max(
                            0,
                            GROUP_LIMIT - count,
                        ),
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
        "إجمالي الطلاب",
        len(rows),
    )

    table = []

    for row in rows:

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

                "التسجيل":
                    row["created_at"],
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
            "📭 لا يوجد طلاب مسجلون."
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
        "🚪 تسجيل خروج المدرس"
    ):

        st.session_state.teacher = False

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصص الحالية",
            "📋 التقارير",
            "📈 الإحصائيات",
            "👨‍🎓 الطلاب",
        ]
    )

    with tabs[0]:

        create_lesson()

    with tabs[1]:

        current_lessons()

    with tabs[2]:

        reports()

    with tabs[3]:

        statistics()

    with tabs[4]:

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
📱 ابعت الرابط ده للطلاب.

الطالب يسجل مرة واحدة فقط،
وبعدها يدخل بحسابه في أي وقت.

📷 الكاميرا موجودة داخل حساب الطالب
لمسح QR الحصص.
        """
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

    page = st.query_params.get(
 
