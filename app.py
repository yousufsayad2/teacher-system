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

    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn


def init_db():

    conn = db()

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
        return st.context.url
    except Exception:
        return ""


def student_url():

    current = page_url()

    if current:

        parsed = urlparse(current)

        return (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}?page=student"
        )

    return "?page=student"


def make_lesson_url(token):

    current = page_url()

    if current:

        parsed = urlparse(current)

        return (
            f"{parsed.scheme}://"
            f"{parsed.netloc}"
            f"{parsed.path}"
            f"?page=student&lesson={token}"
        )

    return f"?page=student&lesson={token}"


def clean_phone(phone):
    return re.sub(r"\D", "", phone or "")


# =========================================================
# GROUPS
# =========================================================

def group_count(grade, group_name):

    conn = db()

    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM students
        WHERE grade = ?
        AND group_name = ?
        """,
        (grade, group_name),
    ).fetchone()

    conn.close()

    return row["total"]


def group_full(grade, group_name):

    return group_count(
        grade,
        group_name
    ) >= GROUP_LIMIT


# =========================================================
# ACTIVE LESSON
# =========================================================

def active_lesson():

    conn = db()

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


# =========================================================
# LESSON STATS
# =========================================================

def lesson_stats(lesson_id):

    conn = db()

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

    absent = total - present

    conn.close()

    return total, present, absent


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

        # لا نسمح بأكثر من حصة مفتوحة
        conn.execute(
            """
            UPDATE lessons
            SET active = 0,
                ended_at = ?
            WHERE active = 1
            """,
            (now(),),
        )

        token = secrets.token_urlsafe(32)

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

        for student in students:

            conn.execute(
                """
                INSERT OR IGNORE INTO lesson_students
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

        return True, lesson_id

    except Exception as e:

        conn.rollback()

        return False, str(e)

    finally:

        conn.close()


# =========================================================
# END LESSON
# =========================================================

def end_lesson(lesson_id):

    conn = db()

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
    conn.close()


# =========================================================
# QR TOKEN EXTRACTOR
# =========================================================

def extract_token(value):

    if not value:
        return None

    value = value.strip()

    # لو الـQR يحتوي Token فقط
    if (
        "://" not in value
        and "page=" not in value
        and "lesson=" not in value
    ):
        return value

    # لو الـQR يحتوي رابط كامل
    try:

        parsed = urlparse(value)

        query = parse_qs(
            parsed.query
        )

        token = query.get(
            "lesson"
        )

        if token:

            return unquote(
                token[0]
            ).strip()

    except Exception:
        pass

    # محاولة إضافية
    match = re.search(
        r"(?:lesson=)([^&\s]+)",
        value
    )

    if match:
        return unquote(
            match.group(1)
        ).strip()

    return None


# =========================================================
# QR SCANNER
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

        # المحاولة الأولى
        value, points, _ = (
            detector.detectAndDecode(image)
        )

        if value:
            return value.strip()

        # محاولة grayscale
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY,
        )

        value, points, _ = (
            detector.detectAndDecode(gray)
        )

        if value:
            return value.strip()

        # محاولة تكبير الصورة
        h, w = gray.shape[:2]

        scale = 2

        resized = cv2.resize(
            gray,
            (w * scale, h * scale),
            interpolation=cv2.INTER_CUBIC,
        )

        value, points, _ = (
            detector.detectAndDecode(resized)
        )

        if value:
            return value.strip()

        # محاولة Multi QR
        try:

            values, points, _ = (
                detector.detectAndDecodeMulti(
                    image
                )
            )

            if values:

                for item in values:

                    if item:
                        return item.strip()

        except Exception:
            pass

        return None

    except Exception:
        return None


# =========================================================
# ATTENDANCE
# =========================================================

def register_attendance(
    token,
    student_id,
):

    token = extract_token(token)

    if not token:

        return False, "❌ كود QR غير صحيح."

    conn = db()

    lesson = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE token = ?
        AND active = 1
        """,
        (token,),
    ).fetchone()

    if not lesson:

        conn.close()

        return False, (
            "❌ هذا الـQR غير صالح "
            "أو أن الحصة انتهت."
        )

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,),
    ).fetchone()

    if not student:

        conn.close()

        return False, (
            "❌ الطالب غير موجود."
        )

    # التأكد أن الطالب في نفس الصف والمجموعة
    if (
        student["grade"]
        != lesson["grade"]
        or
        student["group_name"]
        != lesson["group_name"]
    ):

        conn.close()

        return False, (
            "❌ أنت لست ضمن مجموعة هذه الحصة."
        )

    # التأكد أنه مسجل في قائمة الحصة
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

        conn.close()

        return False, (
            "❌ الطالب غير مسجل في هذه الحصة."
        )

    # منع تكرار الحضور
    already = conn.execute(
        """
        SELECT 1
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

        conn.close()

        return True, (
            "✅ حضورك مسجل بالفعل."
        )

    try:

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

        return True, (
            "🎉 تم تسجيل حضورك بنجاح."
        )

    except sqlite3.IntegrityError:

        conn.rollback()

        return True, (
            "✅ حضورك مسجل بالفعل."
        )

    except Exception as e:

        conn.rollback()

        return False, (
            f"❌ حدث خطأ: {e}"
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
        "📝 تسجيل الطالب في المنصة",
    )

    st.info(
        """
        👋 التسجيل يتم مرة واحدة فقط.

        بعد التسجيل لن تحتاج إلى كتابة بياناتك مرة أخرى.
        في كل حصة ستستخدم QR الخاص بالحصة.
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

        st.write(
            "👥 اختر المجموعة"
        )

        group = st.selectbox(
            "المجموعة",
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
    phone = clean_phone(phone)
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

    if group_count(
        grade,
        group,
    ) >= GROUP_LIMIT:

        st.error(
            "❌ المجموعة وصلت إلى 70 طالب."
        )

        return

    conn = db()

    try:

        existing = conn.execute(
            """
            SELECT *
            FROM students
            WHERE phone = ?
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
                "✅ الطالب مسجل بالفعل."
            )

            st.rerun()

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

        st.success(
            "🎉 تم التسجيل بنجاح."
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
# STUDENT PAGE
# =========================================================

def student_page():

    header(
        "🎓 منصة الحضور",
        "👨‍🎓 واجهة الطالب",
    )

    student_id = (
        st.session_state.get(
            "student_id"
        )
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

        student_registration()

        return

    conn = db()

    student = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,),
    ).fetchone()

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

    lesson_token = st.query_params.get(
        "lesson"
    )

    lesson = None

    if lesson_token:

        token = extract_token(
            lesson_token
        )

        conn = db()

        lesson = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE token = ?
            AND active = 1
            """,
            (token,),
        ).fetchone()

        conn.close()

    if lesson is None:

        lesson = active_lesson()

    if lesson is None:

        st.info(
            "⏳ لا توجد حصة مفتوحة حالياً."
        )

        return

    # لازم الحصة تكون لنفس مجموعة الطالب
    if (
        lesson["grade"]
        != student["grade"]
        or
        lesson["group_name"]
        != student["group_name"]
    ):

        st.warning(
            "⚠️ الحصة الحالية ليست لمجموعتك."
        )

        return

    st.subheader(
        f"📚 {lesson['lesson_name']}"
    )

    st.write(
        f"🎓 الصف: {lesson['grade']}"
    )

    st.write(
        f"👥 المجموعة: {lesson['group_name']}"
    )

    st.write(
        f"🕐 بدأت: {lesson['created_at']}"
    )

    conn = db()

    already = conn.execute(
        """
        SELECT *
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            lesson["id"],
            student_id,
        ),
    ).fetchone()

    conn.close()

    if already:

        st.success(
            f"✅ تم تسجيل حضورك "
            f"في {already['marked_at']}"
        )

        return

    st.info(
        """
        📷 افتح الكاميرا من الزر الموجود بالأسفل
        وصوّر QR الموجود عند المدرس.
        """
    )

    photo = st.camera_input(
        "📷 تصوير QR",
        key=f"qr_{lesson['id']}",
    )

    if photo:

        raw_value = decode_qr(
            photo.getvalue()
        )

        if not raw_value:

            st.error(
                """
                ❌ لم يتم قراءة QR.

                قرّب الكاميرا من الكود
                وخلي الكود كامل ظاهر داخل الصورة.
                """
            )

            return

        token = extract_token(
            raw_value
        )

        if not token:

            st.error(
                "❌ هذا ليس QR الخاص بالمنصة."
            )

            return

        ok, message = register_attendance(
            token,
            student_id,
        )

        if ok:

            st.success(message)

            st.balloons()

        else:

            st.error(message)

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
# CREATE LESSON PAGE
# =========================================================

def create_lesson_page():

    st.subheader(
        "➕ إنشاء حصة جديدة"
    )

    active = active_lesson()

    if active:

        st.warning(
            f"""
            ⚠️ توجد حصة مفتوحة حالياً:

            {active['grade']} -
            {active['group_name']} -
            {active['lesson_name']}
            """
        )

        if st.button(
            "⛔ إنهاء الحصة الحالية"
        ):

            end_lesson(
                active["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة."
            )

            st.rerun()

        return

    grade = st.selectbox(
        "🎓 الصف",
        GRADES,
    )

    st.write(
        "👥 المجموعات الثلاث لهذا الصف:"
    )

    cols = st.columns(3)

    counts = []

    for i, group in enumerate(
        GROUPS
    ):

        count = group_count(
            grade,
            group,
        )

        counts.append(count)

        cols[i].metric(
            group,
            f"{count}/{GROUP_LIMIT}"
        )

    group = st.selectbox(
        "👥 اختر مجموعة الحصة",
        GROUPS,
    )

    selected_count = group_count(
        grade,
        group,
    )

    st.info(
        f"👨‍🎓 عدد الطلاب في "
        f"{group}: "
        f"{selected_count}/{GROUP_LIMIT}"
    )

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
                "❌ لا يوجد طلاب في هذه المجموعة."
            )

            return

        success, result = create_lesson(
            lesson_name.strip()
            or "الحصة الحالية",
            grade,
            group,
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
# CURRENT LESSON
# =========================================================

def current_lesson_page():

    st.subheader(
        "📊 الحصة الحالية"
    )

    lesson = active_lesson()

    if not lesson:

        st.info(
            "⏳ لا توجد حصة مفتوحة."
        )

        return

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
    # الرابط
    # =====================================================

    link = make_lesson_url(
        lesson["token"]
    )

    st.subheader(
        "🔗 رابط الطالب للحصة"
    )

    st.code(
        link,
        language="text",
    )

    st.success(
        "📱 ابعت الرابط ده لطلاب المجموعة."
    )

    # =====================================================
    # QR
    # =====================================================

    st.subheader(
        "📷 QR الحضور"
    )

    # مهم:
    # الـQR يحتوي Token فقط
    # وليس الرابط الكامل
    # وبالتالي لن يحصل تعارض أثناء القراءة

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=5,
    )

    qr.add_data(
        lesson["token"]
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
        caption="📷 امسح هذا الكود لتسجيل الحضور",
        width=350,
    )

    # =====================================================
    # الطلاب
    # =====================================================

    conn = db()

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

    conn.close()

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

    if data:

        st.dataframe(
            data,
            use_container_width=True,
            hide_index=True,
        )

    c1, c2 = st.columns(2)

    with c1:

        if st.button(
            "🔄 تحديث الحضور",
            use_container_width=True,
        ):

            st.rerun()

    with c2:

        if st.button(
            "⛔ إنهاء الحصة وحفظها",
            use_container_width=True,
        ):

            end_lesson(
                lesson["id"]
            )

            st.success(
                """
                ✅ تم إنهاء الحصة وحفظها
                بالحضور والغياب والتاريخ والوقت.
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

    lessons = conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE active = 0
        ORDER BY id DESC
        """
    ).fetchall()

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

        options[label] = lesson["id"]

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

    conn.close()

    data = []

    for row in rows:

        data.append(
            {
                "الطالب": row["name"],
                "الهاتف": row["phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "الحالة":
                    "✅ حاضر"
                    if row["marked_at"]
                    else "❌ غائب",
                "وقت الحضور":
                    row["marked_at"]
                    or "-",
            }
        )

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

    rows = conn.execute(
        """
        SELECT
            grade,
            group_name,
            COUNT(*) AS total
        FROM students
        GROUP BY grade, group_name
        ORDER BY grade, group_name
        """
    ).fetchall()

    conn.close()

    table = []

    for grade in GRADES:

        for group in GROUPS:

            total = 0

            for row in rows:

                if (
                    row["grade"] == grade
                    and
                    row["group_name"] == group
                ):

                    total = row["total"]

            table.append(
                {
                    "الصف": grade,
                    "المجموعة": group,
                    "الطلاب": total,
                    "السعة": GROUP_LIMIT,
                    "المتبقي":
                        GROUP_LIMIT - total,
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

    conn.close()

    st.metric(
        "إجمالي الطلاب",
        len(rows),
    )

    table = []

    for row in rows:

        table.append(
            {
                "ID": row["id"],
                "الاسم": row["name"],
                "هاتف الطالب": row["phone"],
                "هاتف ولي الأمر":
                    row["parent_phone"],
                "الصف": row["grade"],
                "المجموعة": row["group_name"],
                "تاريخ التسجيل":
                    row["created_at"],
            }
        )

    if table:

        st.dataframe(
            table,
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

        st.session_state.teacher = False

        st.rerun()

    tabs = st.tabs(
        [
            "➕ إنشاء حصة",
            "📊 الحصة الحالية",
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
        "🔗 رابط تسجيل الطلاب"
    )

    st.code(
        student_url(),
        language="text",
    )

    st.info(
        """
        📱 ابعت الرابط ده للطلاب.

        الطالب يفتحه أول مرة ويسجل بياناته،
        وبعد ذلك يستخدم QR الخاص بكل حصة.
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
