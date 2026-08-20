import sqlite3
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import urlencode, urlsplit, urlunsplit

import streamlit as st
import pandas as pd
import qrcode
import cv2
import numpy as np


# ============================================================
# إعداد التطبيق
# ============================================================

st.set_page_config(
    page_title="منصة الحضور",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_PATH = "attendance_platform.db"

DB_LOCK = threading.RLock()

GRADES = [
    "الصف الأول الإعدادي",
    "الصف الثاني الإعدادي",
    "الصف الثالث الإعدادي",
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي",
]

GROUPS = [
    "المجموعة 1",
    "المجموعة 2",
    "المجموعة 3",
]

MAX_PER_GROUP = 70


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    html, body, [class*="css"] {
        direction: rtl;
    }

    .main-title {
        font-size: 48px;
        font-weight: 800;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 5px;
    }

    .sub-title {
        font-size: 25px;
        text-align: center;
        margin-bottom: 25px;
    }

    .box {
        padding: 20px;
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,.15);
        background: rgba(255,255,255,.04);
        margin-bottom: 15px;
    }

    .big-number {
        font-size: 40px;
        font-weight: 800;
        text-align: center;
    }

    div.stButton > button {
        width: 100%;
        min-height: 48px;
        border-radius: 12px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATABASE
# ============================================================

def get_conn():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")

    return conn


def init_db():

    with DB_LOCK:

        conn = get_conn()

        try:

            conn.executescript(
                """

                CREATE TABLE IF NOT EXISTS students (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    student_code TEXT NOT NULL UNIQUE,

                    name TEXT NOT NULL,

                    phone TEXT NOT NULL,

                    guardian_phone TEXT NOT NULL,

                    grade TEXT NOT NULL,

                    group_name TEXT NOT NULL,

                    created_at TEXT NOT NULL

                );


                CREATE TABLE IF NOT EXISTS lessons (

                    id TEXT PRIMARY KEY,

                    name TEXT NOT NULL,

                    grade TEXT NOT NULL,

                    group_name TEXT NOT NULL,

                    lesson_date TEXT NOT NULL,

                    start_time TEXT NOT NULL,

                    end_time TEXT,

                    active INTEGER NOT NULL DEFAULT 1,

                    created_at TEXT NOT NULL,

                    ended_at TEXT

                );


                CREATE TABLE IF NOT EXISTS attendance (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    lesson_id TEXT NOT NULL,

                    student_id INTEGER NOT NULL,

                    status TEXT NOT NULL DEFAULT 'present',

                    scanned_at TEXT NOT NULL,

                    UNIQUE(lesson_id, student_id),

                    FOREIGN KEY(lesson_id)
                        REFERENCES lessons(id)
                        ON DELETE CASCADE,

                    FOREIGN KEY(student_id)
                        REFERENCES students(id)
                        ON DELETE CASCADE

                );


                CREATE INDEX IF NOT EXISTS
                idx_students_grade_group
                ON students(grade, group_name);


                CREATE INDEX IF NOT EXISTS
                idx_lessons_active
                ON lessons(active);


                CREATE INDEX IF NOT EXISTS
                idx_lessons_grade_group
                ON lessons(grade, group_name);


                CREATE INDEX IF NOT EXISTS
                idx_attendance_lesson
                ON attendance(lesson_id);

                """
            )

            conn.commit()

        finally:

            conn.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def execute(sql, params=(), retries=5):

    last_error = None

    for attempt in range(retries):

        with DB_LOCK:

            conn = get_conn()

            try:

                cur = conn.execute(sql, params)

                conn.commit()

                return cur

            except sqlite3.OperationalError as e:

                conn.rollback()

                last_error = e

            finally:

                conn.close()

        time.sleep(0.3 * (attempt + 1))

    raise last_error


def fetchone(sql, params=(), retries=5):

    last_error = None

    for attempt in range(retries):

        with DB_LOCK:

            conn = get_conn()

            try:

                return conn.execute(
                    sql,
                    params
                ).fetchone()

            except sqlite3.OperationalError as e:

                last_error = e

            finally:

                conn.close()

        time.sleep(0.3 * (attempt + 1))

    raise last_error


def fetchall(sql, params=(), retries=5):

    last_error = None

    for attempt in range(retries):

        with DB_LOCK:

            conn = get_conn()

            try:

                return conn.execute(
                    sql,
                    params
                ).fetchall()

            except sqlite3.OperationalError as e:

                last_error = e

            finally:

                conn.close()

        time.sleep(0.3 * (attempt + 1))

    raise last_error


# ============================================================
# TIME / URL
# ============================================================

def now_str():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def today_str():

    return datetime.now().strftime(
        "%Y-%m-%d"
    )


def time_str():

    return datetime.now().strftime(
        "%H:%M:%S"
    )


def get_base_url():

    try:

        url = st.context.url

        if url:

            parts = urlsplit(url)

            return urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    parts.path,
                    "",
                    ""
                )
            )

    except Exception:

        pass

    return "http://localhost:8501"


def make_student_link():

    return (
        get_base_url()
        + "?"
        + urlencode(
            {
                "role": "student"
            }
        )
    )


def get_role():

    try:

        role = st.query_params.get(
            "role",
            "teacher"
        )

        if isinstance(role, list):

            role = role[0]

        return role

    except Exception:

        return "teacher"


# ============================================================
# PHONE
# ============================================================

def clean_phone(value):

    return "".join(
        ch
        for ch in str(value)
        if ch.isdigit()
    )


# ============================================================
# STUDENTS
# ============================================================

def student_count(
    grade,
    group_name
):

    row = fetchone(
        """
        SELECT COUNT(*) AS c
        FROM students
        WHERE grade = ?
        AND group_name = ?
        """,
        (
            grade,
            group_name
        )
    )

    return int(row["c"])


def get_student(student_id):

    return fetchone(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    )


# ============================================================
# LESSONS
# ============================================================

def active_lessons():

    return fetchall(
        """
        SELECT *
        FROM lessons
        WHERE active = 1
        ORDER BY created_at DESC
        """
    )


def active_lesson_for(
    grade,
    group_name
):

    return fetchone(
        """
        SELECT *
        FROM lessons
        WHERE active = 1
        AND grade = ?
        AND group_name = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (
            grade,
            group_name
        )
    )


def get_lesson(lesson_id):

    return fetchone(
        """
        SELECT *
        FROM lessons
        WHERE id = ?
        """,
        (lesson_id,)
    )


# ============================================================
# QR
# ============================================================

def make_qr(payload):

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )

    qr.add_data(payload)

    qr.make(
        fit=True
    )

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGB")

    return img


def decode_qr(uploaded_file):

    if uploaded_file is None:

        return None

    try:

        data = uploaded_file.getvalue()

        img = cv2.imdecode(
            np.frombuffer(
                data,
                np.uint8
            ),
            cv2.IMREAD_COLOR
        )

        if img is None:

            return None

        detector = cv2.QRCodeDetector()

        text, points, _ = detector.detectAndDecode(
            img
        )

        if text:

            return text.strip()

        img2 = cv2.resize(
            img,
            None,
            fx=1.8,
            fy=1.8
        )

        text, points, _ = detector.detectAndDecode(
            img2
        )

        if text:

            return text.strip()

    except Exception:

        return None

    return None


# ============================================================
# LESSON STATISTICS
# ============================================================

def lesson_stats(lesson_id):

    lesson = get_lesson(
        lesson_id
    )

    if not lesson:

        return None

    total_row = fetchone(
        """
        SELECT COUNT(*) AS c
        FROM students
        WHERE grade = ?
        AND group_name = ?
        """,
        (
            lesson["grade"],
            lesson["group_name"]
        )
    )

    present_row = fetchone(
        """
        SELECT COUNT(*) AS c
        FROM attendance
        WHERE lesson_id = ?
        AND status = 'present'
        """,
        (lesson_id,)
    )

    total = int(
        total_row["c"]
    )

    present = int(
        present_row["c"]
    )

    absent = max(
        total - present,
        0
    )

    return {
        "total": total,
        "present": present,
        "absent": absent,
        "lesson": lesson
    }


# ============================================================
# END LESSON
# ============================================================

def end_lesson(lesson_id):

    execute(
        """
        UPDATE lessons
        SET
            active = 0,
            end_time = ?,
            ended_at = ?
        WHERE id = ?
        """,
        (
            time_str(),
            now_str(),
            lesson_id
        )
    )


# ============================================================
# TEACHER HEADER
# ============================================================

def teacher_header():

    st.markdown(
        '<div class="main-title">'
        '👨‍🏫 لوحة تحكم المدرس'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        'إدارة الحصص والحضور والطلاب'
        '</div>',
        unsafe_allow_html=True
    )


# ============================================================
# STUDENT LINK
# ============================================================

def show_student_link():

    st.markdown(
        "## 🔗 رابط تسجيل الطلاب"
    )

    link = make_student_link()

    st.info(
        "ابعت الرابط ده للطلاب. "
        "الطالب يستخدمه للتسجيل أول مرة فقط."
    )

    st.code(
        link,
        language="text"
    )

    st.markdown(
        f"""
        <div class="box">

        📱 <b>رابط الطالب:</b>

        <br><br>

        {link}

        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# CREATE LESSON
# ============================================================

def create_lesson_page():

    st.markdown(
        "## ➕ إنشاء حصة جديدة"
    )

    active = active_lessons()

    if active:

        st.warning(
            "⚠️ توجد حصص مفتوحة حاليًا."
        )

        for lesson in active:

            st.markdown(
                f"""
                <div class="box">

                📚 <b>{lesson["name"]}</b>

                <br>

                🎓 الصف:
                {lesson["grade"]}

                <br>

                👥 المجموعة:
                {lesson["group_name"]}

                <br>

                🕐 البداية:
                {lesson["start_time"]}

                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button(
                "🔴 إنهاء هذه الحصة",
                key=f"finish_{lesson['id']}"
            ):

                end_lesson(
                    lesson["id"]
                )

                st.success(
                    "تم إنهاء الحصة وحفظها."
                )

                st.rerun()

        st.info(
            "بعد إنهاء الحصة يمكنك إنشاء الحصة التالية."
        )

        return

    with st.form(
        "create_lesson"
    ):

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        group_name = st.selectbox(
            "👥 المجموعة",
            GROUPS
        )

        lesson_name = st.text_input(
            "📚 اسم الحصة",
            value="الحصة الحالية"
        )

        submitted = st.form_submit_button(
            "🟢 بدء الحصة"
        )

    if submitted:

        lesson_name = (
            lesson_name.strip()
            or "الحصة الحالية"
        )

        existing = active_lesson_for(
            grade,
            group_name
        )

        if existing:

            st.error(
                "يوجد حصة مفتوحة بالفعل لهذه المجموعة."
            )

            return

        lesson_id = str(
            uuid.uuid4()
        )

        execute(
            """
            INSERT INTO lessons
            (
                id,
                name,
                grade,
                group_name,
                lesson_date,
                start_time,
                active,
                created_at
            )
            VALUES
            (
                ?, ?, ?, ?, ?, ?, 1, ?
            )
            """,
            (
                lesson_id,
                lesson_name,
                grade,
                group_name,
                today_str(),
                time_str(),
                now_str()
            )
        )

        st.success(
            "✅ تم بدء الحصة."
        )

        st.rerun()


# ============================================================
# CURRENT LESSON
# ============================================================

def current_lesson_page():

    st.markdown(
        "## 📊 الحصة الحالية"
    )

    active = active_lessons()

    if not active:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        return

    for lesson in active:

        stats = lesson_stats(
            lesson["id"]
        )

        st.markdown(
            f"""
            <div class="box">

            <h2>
            📚 {lesson["name"]}
            </h2>

            🎓 الصف:
            <b>{lesson["grade"]}</b>

            <br>

            👥 المجموعة:
            <b>{lesson["group_name"]}</b>

            <br>

            📅 التاريخ:
            <b>{lesson["lesson_date"]}</b>

            <br>

            🕐 البداية:
            <b>{lesson["start_time"]}</b>

            </div>
            """,
            unsafe_allow_html=True
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "👨‍🎓 إجمالي المسجلين",
            stats["total"]
        )

        c2.metric(
            "✅ الحاضرون",
            stats["present"]
        )

        c3.metric(
            "❌ الغائبون",
            stats["absent"]
        )

        c4.metric(
            "🟢 الحضور الحالي",
            stats["present"]
        )

        st.markdown(
            "### 📷 QR الخاص بالحصة"
        )

        qr_img = make_qr(
            f"ATTENDANCE:{lesson['id']}"
        )

        st.image(
            qr_img,
            caption="الطلاب يمسحون هذا الكود للحضور"
        )

        st.info(
            "كل طالب يستطيع تسجيل حضوره مرة واحدة فقط في هذه الحصة."
        )

        if st.button(
            "🔄 تحديث الحضور",
            key=f"refresh_{lesson['id']}"
        ):

            st.rerun()

        students = fetchall(
            """
            SELECT

                s.id,
                s.student_code,
                s.name,
                s.phone,

                a.scanned_at,
                a.status

            FROM students s

            LEFT JOIN attendance a

                ON a.student_id = s.id

                AND a.lesson_id = ?

            WHERE s.grade = ?

            AND s.group_name = ?

            ORDER BY s.name
            """,
            (
                lesson["id"],
                lesson["grade"],
                lesson["group_name"]
            )
        )

        data = []

        for student in students:

            if student["status"] == "present":

                status = "✅ حاضر"

                scan_time = (
                    student["scanned_at"]
                )

            else:

                status = "❌ غائب"

                scan_time = "-"

            data.append(
                {
                    "الطالب":
                        student["name"],

                    "رقم الطالب":
                        student["student_code"],

                    "الهاتف":
                        student["phone"],

                    "الحالة":
                        status,

                    "وقت الحضور":
                        scan_time
                }
            )

        if data:

            st.markdown(
                "### 📋 حالة الطلاب"
            )

            st.dataframe(
                pd.DataFrame(data),
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "لا يوجد طلاب مسجلون في هذه المجموعة."
            )

        st.divider()

        if st.button(
            "🔴 إنهاء الحصة وحفظ الحضور والغياب",
            key=f"end_lesson_{lesson['id']}"
        ):

            end_lesson(
                lesson["id"]
            )

            st.success(
                "✅ تم إنهاء الحصة وحفظها."
            )

            st.rerun()


# ============================================================
# STUDENTS PAGE
# ============================================================

def students_page():

    st.markdown(
        "## 👨‍🎓 الطلاب المسجلون"
    )

    total = fetchone(
        """
        SELECT COUNT(*) AS c
        FROM students
        """
    )

    st.metric(
        "👨‍🎓 إجمالي طلاب المنصة",
        int(total["c"])
    )

    for grade in GRADES:

        st.markdown(
            f"### 🎓 {grade}"
        )

        cols = st.columns(3)

        for i, group_name in enumerate(
            GROUPS
        ):

            count = student_count(
                grade,
                group_name
            )

            cols[i].metric(
                group_name,
                f"{count} / {MAX_PER_GROUP}"
            )

        rows = fetchall(
            """
            SELECT
                name,
                student_code,
                phone,
                group_name,
                created_at
            FROM students
            WHERE grade = ?
            ORDER BY group_name, name
            """,
            (grade,)
        )

        if rows:

            data = []

            for row in rows:

                data.append(
                    {
                        "الطالب":
                            row["name"],

                        "رقم الطالب":
                            row["student_code"],

                        "الهاتف":
                            row["phone"],

                        "المجموعة":
                            row["group_name"],

                        "تاريخ التسجيل":
                            row["created_at"]
                    }
                )

            st.dataframe(
                pd.DataFrame(data),
                use_container_width=True,
                hide_index=True
            )


# ============================================================
# REPORTS
# ============================================================

def reports_page():

    st.markdown(
        "## 📚 سجل الحصص"
    )

    lessons = fetchall(
        """
        SELECT *
        FROM lessons
        WHERE active = 0
        ORDER BY
            lesson_date DESC,
            start_time DESC
        """
    )

    if not lessons:

        st.info(
            "لا توجد حصص محفوظة حتى الآن."
        )

        return

    for lesson in lessons:

        stats = lesson_stats(
            lesson["id"]
        )

        title = (
            f"📚 {lesson['name']} | "
            f"{lesson['grade']} | "
            f"{lesson['group_name']} | "
            f"{lesson['lesson_date']} "
            f"{lesson['start_time']}"
        )

        with st.expander(title):

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "👨‍🎓 المسجلين",
                stats["total"]
            )

            c2.metric(
                "✅ حضر",
                stats["present"]
            )

            c3.metric(
                "❌ غاب",
                stats["absent"]
            )

            c4.metric(
                "🕐 النهاية",
                lesson["end_time"] or "-"
            )

            rows = fetchall(
                """
                SELECT

                    s.name,
                    s.student_code,
                    s.phone,

                    CASE
                        WHEN a.id IS NOT NULL
                        THEN 'حاضر'
                        ELSE 'غائب'
                    END AS status,

                    COALESCE(
                        a.scanned_at,
                        '-'
                    ) AS scanned_at

                FROM students s

                LEFT JOIN attendance a

                    ON a.student_id = s.id

                    AND a.lesson_id = ?

                WHERE s.grade = ?

                AND s.group_name = ?

                ORDER BY s.name
                """,
                (
                    lesson["id"],
                    lesson["grade"],
                    lesson["group_name"]
                )
            )

            data = []

            for row in rows:

                data.append(
                    {
                        "الطالب":
                            row["name"],

                        "رقم الطالب":
                            row["student_code"],

                        "الهاتف":
                            row["phone"],

                        "الحالة":
                            (
                                "✅ حاضر"
                                if row["status"] == "حاضر"
                                else "❌ غائب"
                            ),

                        "وقت الحضور":
                            row["scanned_at"]
                    }
                )

            if data:

                st.dataframe(
                    pd.DataFrame(data),
                    use_container_width=True,
                    hide_index=True
                )


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

def dashboard_summary():

    st.markdown(
        "## 📊 ملخص المنصة"
    )

    total_students = int(
        fetchone(
            """
            SELECT COUNT(*) AS c
            FROM students
            """
        )["c"]
    )

    total_lessons = int(
        fetchone(
            """
            SELECT COUNT(*) AS c
            FROM lessons
            """
        )["c"]
    )

    active_count = int(
        fetchone(
            """
            SELECT COUNT(*) AS c
            FROM lessons
            WHERE active = 1
            """
        )["c"]
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "👨‍🎓 إجمالي الطلاب",
        total_students
    )

    c2.metric(
        "📚 إجمالي الحصص",
        total_lessons
    )

    c3.metric(
        "🟢 الحصص المفتوحة",
        active_count
    )

    st.markdown(
        "### 👥 الطلاب حسب الصف والمجموعة"
    )

    data = []

    for grade in GRADES:

        for group_name in GROUPS:

            data.append(
                {
                    "الصف":
                        grade,

                    "المجموعة":
                        group_name,

                    "عدد الطلاب":
                        student_count(
                            grade,
                            group_name
                        ),

                    "السعة":
                        MAX_PER_GROUP
                }
            )

    st.dataframe(
        pd.DataFrame(data),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# TEACHER PAGE
# ============================================================

def teacher_page():

    teacher_header()

    show_student_link()

    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📊 الملخص",
            "➕ إنشاء حصة",
            "📈 الحصة الحالية",
            "👨‍🎓 الطلاب",
            "📚 التقارير"
        ]
    )

    with tab1:

        dashboard_summary()

    with tab2:

        create_lesson_page()

    with tab3:

        current_lesson_page()

    with tab4:

        students_page()

    with tab5:

        reports_page()


# ============================================================
# STUDENT REGISTRATION
# ============================================================

def student_registration():

    st.markdown(
        '<div class="main-title">'
        '🎓 منصة الحضور'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        '📝 تسجيل الطالب في المنصة'
        '</div>',
        unsafe_allow_html=True
    )

    st.info(
        "👋 التسجيل يتم مرة واحدة فقط. "
        "بعد التسجيل سيكون لديك رابط شخصي، "
        "وفي كل حصة تستخدم QR الموجود عند المدرس."
    )

    with st.form(
        "student_registration_form"
    ):

        name = st.text_input(
            "👨‍🎓 اسم الطالب"
        )

        phone = st.text_input(
            "📱 رقم هاتف الطالب"
        )

        guardian = st.text_input(
            "👪 رقم هاتف ولي الأمر"
        )

        grade = st.selectbox(
            "🎓 الصف",
            GRADES
        )

        group_name = st.selectbox(
            "👥 المجموعة",
            GROUPS
        )

        submitted = st.form_submit_button(
            "✅ تسجيل الطالب"
        )

    if submitted:

        name = name.strip()

        phone = clean_phone(
            phone
        )

        guardian = clean_phone(
            guardian
        )

        if not name:

            st.error(
                "اكتب اسم الطالب."
            )

            return

        if len(phone) < 10:

            st.error(
                "اكتب رقم هاتف صحيح."
            )

            return

        if len(guardian) < 10:

            st.error(
                "اكتب رقم ولي الأمر صحيح."
            )

            return

        count = student_count(
            grade,
            group_name
        )

        if count >= MAX_PER_GROUP:

            st.error(
                f"❌ المجموعة ممتلئة. "
                f"الحد الأقصى {MAX_PER_GROUP} طالب."
            )

            return

        student_code = (
            datetime.now().strftime(
                "%y%m%d%H%M%S"
            )
            +
            uuid.uuid4().hex[:4].upper()
        )

        try:

            execute(
                """
                INSERT INTO students
                (
                    student_code,
                    name,
                    phone,
                    guardian_phone,
                    grade,
                    group_name,
                    created_at
                )
                VALUES
                (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_code,
                    name,
                    phone,
                    guardian,
                    grade,
                    group_name,
                    now_str()
                )
            )

            student = fetchone(
                """
                SELECT *
                FROM students
                WHERE student_code = ?
                """,
                (student_code,)
            )

            student_id = int(
                student["id"]
            )

            st.session_state[
                "student_id"
            ] = student_id

            st.session_state[
                "student_name"
            ] = student["name"]

            # رابط شخصي ثابت للطالب
            st.query_params["role"] = "student"

            st.query_params[
                "student"
            ] = str(student_id)

            personal_link = (
                get_base_url()
                + "?"
                + urlencode(
                    {
                        "role":
                            "student",

                        "student":
                            str(student_id)
                    }
                )
            )

            st.success(
                "🎉 تم تسجيل الطالب بنجاح."
            )

            st.info(
                f"رقم الطالب: {student_code}"
            )

            st.markdown(
                "### 🔗 رابط الطالب الشخصي"
            )

            st.code(
                personal_link,
                language="text"
            )

            st.success(
                "احتفظ بالرابط. "
                "لن تحتاج إلى التسجيل مرة أخرى."
            )

            st.rerun()

        except sqlite3.IntegrityError:

            st.error(
                "حدث تعارض في التسجيل. "
                "حاول مرة أخرى."
            )

        except Exception as e:

            st.error(
                f"حدث خطأ: {e}"
            )


# ============================================================
# STUDENT PAGE
# ============================================================

def student_page():

    st.markdown(
        '<div class="main-title">'
        '🎓 منصة الحضور'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        '👨‍🎓 واجهة الطالب'
        '</div>',
        unsafe_allow_html=True
    )

    student_id = (
        st.session_state.get(
            "student_id"
        )
    )

    # استرجاع الطالب من الرابط الشخصي
    if not student_id:

        try:

            q_student = (
                st.query_params.get(
                    "student"
                )
            )

            if isinstance(
                q_student,
                list
            ):

                q_student = q_student[0]

            if q_student:

                student_id = int(
                    q_student
                )

                st.session_state[
                    "student_id"
                ] = student_id

        except Exception:

            student_id = None

    if not student_id:

        student_registration()

        return

    student = get_student(
        student_id
    )

    if not student:

        st.session_state.pop(
            "student_id",
            None
        )

        st.session_state.pop(
            "student_name",
            None
        )

        st.query_params.clear()

        st.rerun()

    st.success(
        f"👨‍🎓 أهلاً يا {student['name']}"
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "🎓 الصف",
        student["grade"]
    )

    c2.metric(
        "👥 المجموعة",
        student["group_name"]
    )

    c3.metric(
        "🆔 رقم الطالب",
        student["student_code"]
    )

    active = active_lesson_for(
        student["grade"],
        student["group_name"]
    )

    if not active:

        st.info(
            "⏳ لا توجد حصة مفتوحة حاليًا."
        )

        st.write(
            "عندما يبدأ المدرس الحصة "
            "سيظهر هنا تسجيل الحضور."
        )

        return

    st.markdown(
        "## 📚 الحصة الحالية"
    )

    st.markdown(
        f"""
        <div class="box">

        <h2>
        📚 {active["name"]}
        </h2>

        🎓 الصف:
        {active["grade"]}

        <br>

        👥 المجموعة:
        {active["group_name"]}

        <br>

        📅 التاريخ:
        {active["lesson_date"]}

        <br>

        🕐 وقت البداية:
        {active["start_time"]}

        </div>
        """,
        unsafe_allow_html=True
    )

    existing = fetchone(
        """
        SELECT *
        FROM attendance
        WHERE lesson_id = ?
        AND student_id = ?
        """,
        (
            active["id"],
            student["id"]
        )
    )

    if existing:

        st.success(
            "✅ تم تسجيل حضورك بالفعل."
        )

        st.info(
            f"وقت الحضور: "
            f"{existing['scanned_at']}"
        )

        st.write(
            "لا تحتاج إلى مسح QR مرة أخرى "
            "في نفس الحصة."
        )

        return

    st.warning(
        "📷 لم يتم تسجيل حضورك في هذه الحصة."
    )

    if "scanner_open" not in st.session_state:

        st.session_state[
            "scanner_open"
        ] = False

    if not st.session_state[
        "scanner_open"
    ]:

        if st.button(
            "📷 فتح الكاميرا ومسح QR",
            key="open_camera"
        ):

            st.session_state[
                "scanner_open"
            ] = True

            st.rerun()

        return

    st.markdown(
        "### 📷 امسح QR الموجود عند المدرس"
    )

    st.caption(
        "الكاميرا لا تفتح تلقائيًا."
    )

    picture = st.camera_input(
        "صوّر QR الحصة",
        key=f"camera_{active['id']}",
        resolution="720p"
    )

    if picture is not None:

        payload = decode_qr(
            picture
        )

        if not payload:

            st.error(
                "❌ لم أستطع قراءة QR. "
                "قرّب الكاميرا وحاول مرة أخرى."
            )

            return

        expected = (
            f"ATTENDANCE:{active['id']}"
        )

        if payload != expected:

            st.error(
                "❌ هذا QR ليس خاصًا بالحصة الحالية."
            )

            return

        try:

            execute(
                """
                INSERT OR IGNORE INTO attendance
                (
                    lesson_id,
                    student_id,
                    status,
                    scanned_at
                )
                VALUES
                (
                    ?,
                    ?,
                    'present',
                    ?
                )
                """,
                (
                    active["id"],
                    student["id"],
                    now_str()
                )
            )

            saved = fetchone(
                """
                SELECT *
                FROM attendance
                WHERE lesson_id = ?
                AND student_id = ?
                """,
                (
                    active["id"],
                    student["id"]
                )
            )

            st.session_state[
                "scanner_open"
            ] = False

            if saved:

                st.success(
                    "🎉 تم تسجيل حضورك بنجاح."
                )

                st.info(
                    f"وقت الحضور: "
                    f"{saved['scanned_at']}"
                )

                st.rerun()

        except Exception as e:

            st.error(
                f"تعذر تسجيل الحضور: {e}"
            )

    if st.button(
        "❌ إغلاق الكاميرا",
        key="close_camera"
    ):

        st.session_state[
            "scanner_open"
        ] = False

        st.rerun()


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    role = get_role()

    if role == "student":

        student_page()

    else:

        teacher_page()


if __name__ == "__main__":

    main()
