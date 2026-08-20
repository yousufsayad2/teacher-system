import streamlit as st
import qrcode
from PIL import Image
import io
import json
from datetime import datetime
import pyzbar.pyzbar as zbar
from PIL import Image
import cv2
import numpy as np

# ==================== التخزين ====================
if 'students' not in st.session_state:
    st.session_state.students = []
if 'lessons' not in st.session_state:
    st.session_state.lessons = []
if 'days' not in st.session_state:
    st.session_state.days = []
if 'current_student' not in st.session_state:
    st.session_state.current_student = None
if 'active_lesson' not in st.session_state:
    st.session_state.active_lesson = None

# ==================== الصفحة الرئيسية ====================
st.set_page_config(page_title="منصة الحضور والغياب", layout="wide")

st.markdown("""
<style>
    .main {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        min-height: 100vh;
    }
    .stButton>button {
        width: 100%;
        background: #ffd700;
        color: #222;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎓 منصة الحضور والغياب الذكية")

# اختيار نوع المستخدم
choice = st.radio("اختر نوع الدخول:", ["👨🎓 طالب", "‍🏫 مدرس"])

# ==================== بوابة الطالب ====================
if choice == "👨‍🎓 طالب":
    st.header("بوابة الطالب")
    
    tab1, tab2 = st.tabs(["📝 تسجيل جديد", " دخول طالب مسجل"])
    
    with tab1:
        st.subheader("تسجيل طالب جديد")
        s_name = st.text_input("الاسم الكامل", key="reg_name")
        s_number = st.text_input("رقم الطالب", key="reg_number")
        s_class = st.text_input("الفصل", key="reg_class")
        
        if st.button("تسجيل وإنشاء QR"):
            if s_name and s_number and s_class:
                # التحقق من عدم التكرار
                if any(s['number'] == s_number for s in st.session_state.students):
                    st.error("هذا الرقم مسجل مسبقاً!")
                else:
                    student = {
                        'id': f"STU-{len(st.session_state.students)}",
                        'name': s_name,
                        'number': s_number,
                        'class': s_class
                    }
                    st.session_state.students.append(student)
                    st.session_state.current_student = student
                    st.success("✅ تم التسجيل بنجاح!")
                    
                    # توليد QR Code
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(json.dumps(student))
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    
                    st.image(img.get_image(), caption="QR Code الخاص بك", width=300)
                    
                    # حفظ الصورة
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    st.download_button(
                        label="📥 تحميل QR Code",
                        data=buf.getvalue(),
                        file_name=f"qr_{s_number}.png",
                        mime="image/png"
                    )
            else:
                st.error("أكمل كل البيانات!")
    
    with tab2:
        st.subheader("دخول طالب مسجل")
        login_number = st.text_input("أدخل رقم الطالب", key="login_number")
        
        if st.button("دخول"):
            student = next((s for s in st.session_state.students if s['number'] == login_number), None)
            if student:
                st.session_state.current_student = student
                st.success(f"مرحباً {student['name']} ")
                
                # عرض QR
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(json.dumps(student))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                st.image(img.get_image(), width=300)
            else:
                st.error("رقم غير موجود!")

# ==================== بوابة المدرس ====================
elif choice == "👨🏫 مدرس":
    st.header("بوابة المدرس")
    
    password = st.text_input("كلمة المرور", type="password", value="1234")
    
    if password == "1234":
        st.success("تم الدخول بنجاح!")
        
        tab1, tab2, tab3 = st.tabs(["📅 اليوم الحالي", " سجل الأيام", "👥 الطلاب"])
        
        with tab1:
            st.subheader("إحصائيات اليوم")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("إجمالي الطلاب", len(st.session_state.students))
            col2.metric("حصص اليوم", len([l for l in st.session_state.lessons if l.get('today')]))
            
            st.subheader("📚 إنشاء حصة جديدة")
            lesson_name = st.text_input("اسم الحصة")
            
            if st.session_state.students:
                selected_students = st.multiselect(
                    "اختر الطلاب",
                    options=[s['name'] for s in st.session_state.students],
                    format_func=lambda x: x
                )
                
                if st.button("إنشاء حصة"):
                    if lesson_name and selected_students:
                        lesson = {
                            'id': f"LES-{len(st.session_state.lessons)}",
                            'name': lesson_name,
                            'today': True,
                            'enrolled': selected_students,
                            'attendance': [],
                            'active': True
                        }
                        st.session_state.lessons.append(lesson)
                        st.session_state.active_lesson = lesson
                        st.success("✅ تم إنشاء الحصة!")
                        st.rerun()
            else:
                st.warning("لا يوجد طلاب مسجلين بعد")
            
            # الحصة النشطة
            if st.session_state.active_lesson:
                st.subheader(f"🎯 الحصة النشطة: {st.session_state.active_lesson['name']}")
                
                st.write("📷 مسح QR للحضور (استخدم الكاميرا)")
                
                # هنا ممكن تضيف كاميرا لقراءة QR
                # لكن للتبسيط، هنستخدم اختيار يدوي
                present_student = st.selectbox(
                    "اختر طالب للحضور",
                    options=st.session_state.active_lesson['enrolled']
                )
                
                if st.button("تسجيل حضور"):
                    if present_student not in st.session_state.active_lesson['attendance']:
                        st.session_state.active_lesson['attendance'].append(present_student)
                        st.success(f"✅ تم تسجيل حضور: {present_student}")
                        st.balloons()
                    else:
                        st.info("الطالب حاضر بالفعل")
                
                # عرض القائمة
                st.write("### 📋 قائمة الطلاب:")
                for student_name in st.session_state.active_lesson['enrolled']:
                    status = "✅ حاضر" if student_name in st.session_state.active_lesson['attendance'] else "❌ غائب"
                    st.write(f"{student_name}: {status}")
        
        with tab2:
            st.subheader("سجل الأيام")
            if st.session_state.days:
                for day in st.session_state.days:
                    st.write(f"📅 {day.get('date', 'Unknown')}: {day.get('summary', '')}")
            else:
                st.write("لا توجد أيام مسجلة بعد")
        
        with tab3:
            st.subheader("جميع الطلاب")
            if st.session_state.students:
                for s in st.session_state.students:
                    st.write(f"👤 {s['name']} - {s['number']} - {s['class']}")
            else:
                st.write("لا يوجد طلاب مسجلين")
    else:
        st.error("كلمة مرور خاطئة!")
