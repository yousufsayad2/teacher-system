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
# STREAMLIT
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
    }

    .main-title {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
    }

    .sub-title {
        text-align: center;
        font-size: 26px;
        margin-bottom: 30px;
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

    try:
        conn.execute(
            "PRAGMA journal_mode=WAL"
        )
    except Exception:
        pass

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

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_students_grade_group
            ON students(grade, group_name)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_lessons_active_grade_group
            ON lessons(active, grade, group_name)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_attendance_lesson_student
            ON attendance(lesson_id, student_id)
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


def page_url():

    try:

        return st.context.url or ""

    except Exception:

        return ""


def base_url():

    current = page_url()

    if current:

        parsed = urlparse(current)

        if parsed.scheme and parsed.netloc:

            return (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

    return ""


def student_url():

    base = base_url()

    if base:

        return (
            f"{base}?page=student"
        )

    return "?page=student"


def make_lesson_url(token):

    base = base_url()

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


def clean_phone(phone):

    return re.sub(
        r"\D",
        "",
        phone or "",
    )


def get_student(student_id):

    conn = db()

    try:

        return conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()

    finally:

        conn.close()


# =========================================================
# GROUPS
# =========================================================

def group_count(
    grade,
    group_name,
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
                group_name,
            ),
        ).fetchone()

        return row["total"]

    finally:

        conn.close()


# =========================================================
# ACTIVE LESSON
# =========================================================

def active_lesson(
    grade=None,
    group_name=None,
    token=None,
):

    conn = db()

    try:

        if token:

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

        if grade and group_name:

            return conn.execute(
                """
                SELECT *
                FROM lessons
                WHERE grade = ?
                AND group_name = ?
                AND active = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    grade,
                    group_name,
                ),
            ).fetchone()

        return conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    finally:

        conn.close()


# =========================================================
# LESSON STATS
# =========================================================

def lesson_stats(
    lesson_id,
):

    conn = db()

    try:

        total = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM lesson_students
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["total"]

        present = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchone()["total"]

        absent = max(
            0,
            total - present,
        )

        return (
            total,
            present,
            absent,
        )

    finally:

        conn.close()


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson(
    lesson_name,
    grade,
    group_name,
):

    conn = db()

    try:

        # يسمح بحصة واحدة مفتوحة
        # لنفس الصف والمجموعة.
        #
        # لكن المجموعة 1 و2 و3
        # يمكن أن يكون لكل واحدة حصة مستقلة.

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
                group_name,
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
                lesson_name,
                grade,
                group_name,
                token,
                now(),
            ),
        )

        lesson_id = cursor.lastrowid

        students = conn.execute(
            """
            SELECT id
            FROM students
            WHERE grade = ?
            AND group_name = ?
            ORDER BY id
            """,
            (
                grade,
                group_name,
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
                    student["id"],
                )
                for student in students
            ],
        )

        conn.commit()

        return (
            True,
            lesson_id,
        )

    except Exception as e:

        conn.rollback()

        return (
            False,
            str(e),
        )

    finally:

        conn.close()


# =========================================================
# END LESSON
# =========================================================

def end_lesson(
    lesson_id,
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
                lesson_id,
            ),
        )

        conn.commit()

    finally:

        conn.close()


# =========================================================
# QR TOKEN
# =========================================================

def extract_token(value):

    if not value:

        return None

    value = str(value).strip()

    value = (
        value
        .replace("\n", "")
        .replace("\r", "")
    )

    # QR يحتوي Token فقط
    if (
        "://" not in value
        and "lesson=" not in value
    ):

        return value

    # QR يحتوي رابط كامل
    try:

        parsed = urlparse(
            value
        )

        query = parse_qs(
            parsed.query
        )

        token_list = query.get(
            "lesson"
        )

        if (
            token_list
            and token_list[0]
        ):

            return unquote(
                token_list[0]
            ).strip()

    except Exception:

        pass

    # محاولة إضافية
    match = re.search(
        r"(?:[?&]|^)lesson=([^&#\s]+)",
        value,
    )

    if match:

        return unquote(
            match.group(1)
        ).strip()

    return None


# =========================================================
# QR SCANNER
# =========================================================

def decode_qr(
    image_bytes,
):

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

        images = [
            image
        ]

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        images.append(
            gray
        )

        h, w = gray.shape[:2]

        if max(
            h,
            w,
        ) < 1600:

            resized = cv2.resize(
                gray,
                (
                    w * 2,
                    h * 2,
                ),
                interpolation=cv2.INTER_CUBIC,
            )

            images.append(
                resized
            )

        # محاولات القراءة
        for img in images:

            try:

                value, points, _ = (
                    detector.detectAndDecode(
                        img
                    )
                )

                if (
                    value
                    and value.strip()
                ):

                    return value.strip()

            except Exception:

                pass

        # Multi QR
        for img in images[:2]:

            try:

                result = (
                    detector.detectAndDecodeMulti(
                        img
                    )
                )

                if len(result) == 4:

                    ok, decoded_info, points, _ = result

                    if ok and decoded_info:

                        for value in decoded_info:

                            if (
                                value
                                and value.strip()
                            ):

                                return value.strip()

            except Exception:

                pass

        return None

    except Exception:

        return None


# =========================================================
# REGISTER ATTENDANCE
# =========================================================

def register_attendance(
    token,
    student_id,
):

    token = extract_token(
        token
    )

    if not token:

        return (
            False,
            "❌ كود QR غير صحيح.",
        )

    conn = db()

    try:

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

        if not lesson:

            return (
                False,
                "❌ هذا الـQR غير صالح "
                "أو أن الحصة انتهت.",
            )

        student = conn.execute(
            """
            SELECT *
            FROM students
            WHERE id = ?
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()

        if not student:

            return (
                False,
                "❌ بيانات الطالب غير موجودة.",
            )

        # التأكد من الصف والمجموعة
        if (
            student["grade"]
            != lesson["grade"]
            or
            student["group_name"]
            != lesson["group_name"]
        ):

            return (
                False,
                "❌ هذا الـQR خاص بصف "
                "أو مجموعة مختلفة.",
            )

        # تسجيل الطالب في الحصة
        registered = conn.execute(
            """
            SELECT 1
            FROM lesson_students
            WHERE lesson_id = ?
            AND student_id = ?
            """,
            (
                lesson["id"],
                student_id,
            ),
        ).fetchone()

        if not registered:

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

        # هل حضر بالفعل؟
        already = conn.execute(
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

        if already:

            return (
                True,
                "✅ حضورك مسجل بالفعل "
                f"الساعة {already['marked_at']}.",
            )

        # تسجيل الحضور
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
                now(),
            ),
        )

        conn.commit()

        return (
            True,
            "🎉 تم تسجيل حضورك بنجاح.",
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
            f"❌ حدث خطأ أثناء تسجيل الحضور: {e}",
        )

    finally:

        conn.close()


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
# STUDENT REGISTRATION
# =========================================================

def student_registration():

    header(
        "🎓 منصة الحضور",
        "📝 تسجيل الطالب",
    )

    st.info(
        """
        👋 سجل بياناتك مرة واحدة فقط.

        بعد التسجيل:
        • افتح رابط الحصة الذي يرسله المدرس.
        • صوّر QR الخاص بالحصة.
        • سيظهر حضورك عند المدرس فوراً.
        """
    )

    with st.form(
        "student_register_form",
        clear_on_submit=False,
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
            f"👨‍🎓 {group}: "
            f"{count}/{GROUP_LIMIT} طالب"
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب",
            use_container_width=True,
        )

    if not submitted:

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
            "❌ رقم هاتف الطالب غير صحيح."
        )

        return

    conn = db()

    try:

        existing = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
            LIMIT 1
            """,
            (phone,),
        ).fetchone()

        if existing:

            st.session_state.student_id = (
                existing["id"]
            )

            st.query_params["page"] = (
                "student"
            )

            st.query_params["student"] = (
                str(existing["id"])
            )

            st.success(
                "✅ رقم الهاتف مسجل بالفعل، "
                "تم فتح حساب الطالب."
            )

            st.rerun()

        current_count = conn.execute(
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

        if current_count >= GROUP_LIMIT:

            st.error(
                "❌ المجموعة وصلت إلى "
                "70 طالب."
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

        student_id = (
            cursor.lastrowid
        )

        st.session_state.student_id = (
            student_id
        )

        st.query_params["page"] = (
            "student"
        )

        st.query_params["student"] = (
            str(student_id)
        )

        st.success(
            "🎉 تم تسجيل الطالب بنجاح."
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
            f"❌ حدث خطأ: {e}"
        )

    finally:

        conn.close()


# =========================================================
# GET STUDENT ID
# =========================================================

def resolve_student_id():

    student_id = (
        st.session_state.get(
            "student_id"
        )
    )

    if student_id:

        try:

            return int(
                student_id
            )

        except Exception:

            pass

    value = st.query_params.get(
        "student"
    )

    if value:

        try:

            student_id = int(
                value
            )

            st.session_state.student_id = (
                student_id
            )

            return student_id

        except Exception:

            pass

    return None


# =========================================================
# STUDENT PAGE
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    student_id = (
        resolve_student_id()
    )

    if student_id is None:

        student_registration()

        return

    student = get_student(
        student_id
    )

    if not student:

        st.session_state.pop(
            "student_id",
            None,
        )

        st.query_params.clear()

        st.rerun()

    st.success(
        f"👨‍🎓 {student['name']}  |  "
        f"🎓 {student['grade']}  |  "
        f"👥 {student['group_name']}"
    )

    requested_token = (
        st.query_params.get(
            "lesson"
        )
    )

    token = None

    if requested_token:

        token = extract_token(
            requested_token
        )

    lesson = None

    # إذا كان رابط الحصة يحتوي token
    if token:

        lesson = active_lesson(
            token=token
        )

    # إذا لم يوجد token
    # ابحث عن حصة مفتوحة لمجموعة الطالب
    if lesson is None:

        lesson = active_lesson(
            grade=student["grade"],
            group_name=student["group_name"],
        )

    if lesson is None:

        st.info(
            """
            ⏳ لا توجد حصة مفتوحة لمجموعتك حالياً.

            📱 عندما يبدأ المدرس الحصة،
            افتح رابط الحصة الذي سيرسله لك.
            """
        )

        return

    # التأكد أن الحصة للطالب
    if (
        lesson["grade"]
        != student["grade"]
        or
        lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            f"""
            ⚠️ هذه الحصة تخص:

            {lesson['grade']}
            -
            {lesson['group_name']}

            بينما أنت مسجل في:

            {student['grade']}
            -
            {student['group_name']}
            """
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 **الصف:** "
        f"{lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** "
        f"{lesson['group_name']}"
    )

    st.write(
        f"🕐 **بدأت:** "
        f"{lesson['created_at']}"
    )

    # =====================================================
    # CHECK ATTENDANCE
    # =====================================================

    conn = db()

    try:

        already = conn.execute(
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

    finally:

        conn.close()

    # لو حضر بالفعل
    if already:

        st.success(
            f"""
            ✅ حضورك مسجل بالفعل.

            🕐 وقت تسجيل الحضور:
            {already['marked_at']}
            """
        )

        st.info(
            """
            يمكنك الخروج من الصفحة والعودة مرة أخرى،
            وسيظل حضورك محفوظاً.
            """
        )

        return

    # =====================================================
    # CAMERA
    # =====================================================

    st.info(
        """
        📷 صوّر QR الموجود عند المدرس.

        ✔ قرّب الكاميرا من الكود.
        ✔ خلي QR كامل ظاهر.
        ✔ تأكد من وجود إضاءة جيدة.
        """
    )

    photo = st.camera_input(
        "📷 افتح الكاميرا وصوّر QR",
        key=(
            f"qr_camera_"
            f"{lesson['id']}_"
            f"{student_id}"
        ),
    )

    if photo:

        raw_value = decode_qr(
            photo.getvalue()
        )

        if not raw_value:

            st.error(
                """
                ❌ لم أستطع قراءة QR.

                جرّب:
                1. تقريب الكاميرا.
                2. إظهار الكود بالكامل.
                3. زيادة الإضاءة.
                4. عدم اهتزاز الهاتف.
                """
            )

            return

        scanned_token = extract_token(
            raw_value
        )

        if not scanned_token:

            st.error(
                """
                ❌ الكود المقروء ليس
                QR الخاص بمنصة الحضور.
                """
            )

            return

        ok, message = (
            register_attendance(
                scanned_token,
                student_id,
            )
        )

        if ok:

            st.success(
                message
            )

            st.balloons()

            st.rerun()

        else:

            st.error(
                message
            )

    # =====================================================
    # MANUAL FALLBACK
    # =====================================================

    with st.expander(
        "🆘 الكاميرا لا تقرأ QR؟"
    ):

        st.write(
            """
            لو كاميرا الهاتف مش قادرة تقرأ الكود،
            اطلب من المدرس إرسال رابط الحصة لك،
            والصقه هنا.
            """
        )

        manual = st.text_input(
            "🔑 رابط الحصة أو كود QR",
            key=(
                f"manual_qr_"
                f"{lesson['id']}_"
                f"{student_id}"
            ),
        )

        if st.button(
            "✅ تسجيل الحضور بالكود",
            key=(
                f"manual_btn_"
                f"{lesson['id']}_"
                f"{student_id}"
            ),
            use_container_width=True,
        ):

            ok, message = (
                register_attendance(
                    manual,
                    student_id,
                )
            )

            if ok:

                st.success(
                    message
                )

                st.balloons()

                st.rerun()

            else:

                st.error(
                    message
                )


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

    st.caption(
        "كلمة المرور الافتراضية: 1234"
    )


# =========================================================
# CREATE LESSON
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
        key="create_grade",
    )

    st.write(
        "👥 عدد الطلاب في المجموعات:"
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
        "👥 اختر مجموعة الحصة",
        GROUPS,
        key="create_group",
    )

    selected_count = group_count(
        grade,
        group,
    )

    st.info(
        f"""
        👨‍🎓 عدد الطلاب في {group}:
        {selected_count}/{GROUP_LIMIT}
        """
    )

    existing = active_lesson(
        grade=grade,
        group_name=group,
    )

    if existing:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة بالفعل لهذه المجموعة:

            📚 {existing['lesson_name']}

            🕐 {existing['created_at']}
            """
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية",
            key=(
                f"end_existing_"
                f"{existing['id']}"
            ),
            use_container_width=True,
        ):

            end_lesson(
                existing["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    lesson_name = st.text_input(
        "📚 اسم الحصة",
        value="الحصة الحالية",
    )

    if st.button(
        "🟢 بدء الحصة",
        use_container_width=True,
    ):

        if selected_count == 0:

            st.error(
                """
                ❌ لا يوجد طلاب في هذه المجموعة.

                سجّل الطلاب أولاً من
                رابط تسجيل الطلاب.
                """
            )

            return

        success, result = (
            create_lesson(
                lesson_name.strip()
                or "الحصة الحالية",
                grade,
                group,
            )
        )

        if not success:

            st.error(
                f"❌ {result}"
            )

            return

        st.success(
            "🎉 تم إنشاء الحصة بنجاح."
        )

        st.rerun()


# =========================================================
# CURRENT LESSONS
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصص المفتوحة"
    )

    conn = db()

    try:

        lessons = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE active = 1
            ORDER BY id DESC
            """
        ).fetchall()

    finally:

        conn.close()

    if not lessons:

        st.info(
            "⏳ لا توجد حصص مفتوحة حالياً."
        )

        return

    labels = [
        (
            f"#{x['id']} | "
            f"{x['grade']} | "
            f"{x['group_name']} | "
            f"{x['lesson_name']}"
        )
        for x in lessons
    ]

    selected_label = st.selectbox(
        "اختر الحصة",
        labels,
        key="current_lesson_select",
    )

    selected_index = labels.index(
        selected_label
    )

    lesson = lessons[
        selected_index
    ]

    total, present, absent = (
        lesson_stats(
            lesson["id"]
        )
    )

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

    st.write(
        f"🎓 **الصف:** "
        f"{lesson['grade']}"
    )

    st.write(
        f"👥 **المجموعة:** "
        f"{lesson['group_name']}"
    )

    st.write(
        f"📚 **الحصة:** "
        f"{lesson['lesson_name']}"
    )

    st.write(
        f"🕐 **وقت البداية:** "
        f"{lesson['created_at']}"
    )

    # =====================================================
    # LESSON LINK
    # =====================================================

    link = make_lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الحصة للطلاب"
    )

    st.code(
        link,
        language="text",
    )

    st.success(
        "📱 ابعت الرابط ده لطلاب المجموعة المحددة."
    )

    # =====================================================
    # QR
    # =====================================================

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

    # مهم:
    # QR يحتوي رابط الحصة الكامل
    qr.add_data(
        link
    )

    qr.make(
        fit=True
    )

    qr_image = qr.make_image()

    buffer = io.BytesIO()

    qr_image.save(
        buffer,
        format="PNG",
    )

    st.image(
        buffer.getvalue(),
        caption=(
            "📷 QR الحضور — "
            "الطالب يمسحه بالكاميرا"
        ),
        width=400,
    )

    # =====================================================
    # STUDENTS
    # =====================================================

    conn = db()

    try:

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

            ORDER BY s.name COLLATE NOCASE
            """,
            (lesson["id"],),
        ).fetchall()

    finally:

        conn.close()

    data = []

    for row in rows:

        data.append(
            {
                "الطالب":
                    row["name"],

                "الهاتف":
                    row["phone"],

                "الحالة":
                    (
                        "✅ حاضر"
                        if row["marked_at"]
                        else "❌ غائب"
                    ),

                "وقت الحضور":
                    (
                        row["marked_at"]
                        or "-"
                    ),
            }
        )

    st.subheader(
        "👨‍🎓 كشف الطلاب"
    )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "لا يوجد طلاب مسجلون في هذه الحصة."
        )

    c1, c2 = st.columns(2)

    with c1:

        if st.button(
            "🔄 تحديث الحضور",
            key=(
                f"refresh_"
                f"{lesson['id']}"
            ),
            use_container_width=True,
        ):

            st.rerun()

    with c2:

        if st.button(
            "⛔ إنهاء الحصة وحفظها",
            key=(
                f"finish_"
                f"{lesson['id']}"
            ),
            use_container_width=True,
        ):

            end_lesson(
                lesson["id"]
            )

            st.success(
                """
                ✅ تم إنهاء الحصة
                وحفظ الحضور والغياب.
                """
            )

            st.rerun()


# =========================================================
# REPORTS
# =========================================================

def reports_page():

    st.subheader(
        "📋 سجل الحصص المحفوظة"
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
            "لا توجد حصص محفوظة."
        )

        return

    options = {}

    for lesson in lessons:

        label = (
            f"#{lesson['id']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_name']} | "
            f"{lesson['created_at']}"
        )

        options[
            label
        ] = lesson["id"]

    selected = st.selectbox(
        "اختر الحصة",
        list(options.keys()),
    )

    lesson_id = options[
        selected
    ]

    total, present, absent = (
        lesson_stats(
            lesson_id
        )
    )

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
            (lesson_id,),
        ).fetchall()

    finally:

        conn.close()

    data = []

    for row in rows:

        data.append(
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
                    (
                        row["marked_at"]
                        or "-"
                    ),
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# STATISTICS
# =========================================================

def statistics_page():

    st.subheader(
        "📈 إحصائيات الصفوف والمجموعات"
    )

    conn = db()

    try:

        rows = conn.execute(
            """
            SELECT
                grade,
                group_name,
                COUNT(*) AS total

            FROM students

            GROUP BY
                grade,
                group_name
            """
        ).fetchall()

    finally:

        conn.close()

    counts = {}

    for row in rows:

        counts[
            (
                row["grade"],
                row["group_name"],
            )
        ] = row["total"]

    table = []

    for grade in GRADES:

        for group in GROUPS:

            total = counts.get(
                (
                    grade,
                    group,
                ),
                0,
            )

            table.append(
                {
                    "الصف":
                        grade,

                    "المجموعة":
                        group,

                    "الطلاب":
                        total,

                    "السعة":
                        GROUP_LIMIT,

                    "المتبقي":
                        max(
                            0,
                            GROUP_LIMIT - total,
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

def students_page():

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

    data = []

    for row in rows:

        data.append(
            {
                "ID":
                    row["id"],

                "الاسم":
                    row["name"],

                "هاتف الطالب":
                    row["phone"],

                "هاتف ولي الأمر":
                    row["parent_phone"],

                "الصف":
                    row["grade"],

                "المجموعة":
                    row["group_name"],

                "تاريخ التسجيل":
                    row["created_at"],
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
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
        "🚪 تسجيل خروج"
    ):

        st.session_state.teacher = (
            False
        )

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصص المفتوحة",
            "📋 التقارير",
            "📈 إحصائيات",
            "👨‍🎓 الطلاب",
        ]
    )

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
        "🔗 رابط تسجيل الطلاب العام"
    )

    st.code(
        student_url(),
        language="text",
    )

    st.info(
        """
        📱 ابعت الرابط ده للطلاب.

        الطالب يسجل بياناته مرة واحدة،
        وبعد ذلك يدخل على رابط الحصة
        ويسجل حضوره باستخدام QR.
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


main()
