<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>منصة الحضور والغياب</title>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Arial; }
  body { background: linear-gradient(135deg,#1e3c72,#2a5298); min-height:100vh; color:#fff; padding:20px; }
  .container { max-width:1100px; margin:auto; background:rgba(255,255,255,0.08); backdrop-filter:blur(10px); border-radius:20px; padding:30px; box-shadow:0 8px 32px rgba(0,0,0,0.3); }
  h1 { text-align:center; margin-bottom:20px; font-size:2rem; }
  h2 { margin:15px 0; color:#ffd700; }
  .btn { background:#ffd700; color:#222; border:none; padding:12px 24px; border-radius:10px; cursor:pointer; font-weight:bold; font-size:1rem; margin:5px; transition:.2s; }
  .btn:hover { background:#ffec8b; transform:translateY(-2px); }
  .btn-red { background:#e74c3c; color:#fff; }
  .btn-green { background:#27ae60; color:#fff; }
  .btn-blue { background:#3498db; color:#fff; }
  input, select { width:100%; padding:12px; border-radius:10px; border:none; margin:8px 0; font-size:1rem; background:rgba(255,255,255,0.9); color:#222; }
  .card { background:rgba(255,255,255,0.12); padding:20px; border-radius:15px; margin:15px 0; }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:15px; margin:15px 0; }
  .stat { background:rgba(255,255,255,0.15); padding:20px; border-radius:12px; text-align:center; }
  .stat .num { font-size:2.2rem; font-weight:bold; color:#ffd700; }
  .stat .lbl { font-size:.95rem; margin-top:5px; }
  table { width:100%; border-collapse:collapse; margin-top:10px; background:rgba(255,255,255,0.9); color:#222; border-radius:10px; overflow:hidden; }
  th, td { padding:10px; text-align:center; border-bottom:1px solid #ddd; }
  th { background:#2a5298; color:#fff; }
  .present { color:#27ae60; font-weight:bold; }
  .absent { color:#e74c3c; font-weight:bold; }
  .hidden { display:none !important; }
  #qrcode { display:flex; justify-content:center; margin:15px 0; }
  .role-btn { display:block; width:100%; padding:25px; font-size:1.3rem; margin:10px 0; }
  .alert { padding:12px; border-radius:10px; margin:10px 0; text-align:center; font-weight:bold; }
  .alert-success { background:#27ae60; }
  .alert-error { background:#e74c3c; }
  .alert-info { background:#3498db; }
  .student-item { display:flex; justify-content:space-between; align-items:center; padding:10px; background:rgba(255,255,255,0.1); border-radius:8px; margin:5px 0; flex-wrap:wrap; gap:10px; }
  .checkbox-item { display:flex; align-items:center; gap:10px; padding:8px; background:rgba(255,255,255,0.1); border-radius:8px; margin:5px 0; }
  .checkbox-item input { width:auto; margin:0; }
  .top-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:10px; }
  .badge { display:inline-block; padding:4px 10px; border-radius:20px; font-size:.85rem; background:#ffd700; color:#222; }
  .day-card { background:rgba(255,255,255,0.1); padding:15px; border-radius:12px; margin:10px 0; border-right:4px solid #ffd700; cursor:pointer; transition:.2s; }
  .day-card:hover { background:rgba(255,255,255,0.2); }
  .day-card.today { border-right-color:#27ae60; background:rgba(39,174,96,0.2); }
  .day-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }
  .day-stats { display:flex; gap:15px; margin-top:10px; flex-wrap:wrap; }
  .day-stat { background:rgba(0,0,0,0.2); padding:8px 15px; border-radius:8px; font-size:.9rem; }
  .tabs { display:flex; gap:5px; margin-bottom:15px; flex-wrap:wrap; }
  .tab { padding:10px 20px; background:rgba(255,255,255,0.1); border-radius:10px; cursor:pointer; transition:.2s; }
  .tab.active { background:#ffd700; color:#222; font-weight:bold; }
  .tab:hover { background:rgba(255,255,255,0.2); }
  .tab.active:hover { background:#ffec8b; }
</style>
</head>
<body>

<div class="container">

  <!-- ========== شاشة البداية ========== -->
  <div id="screen-home">
    <h1>🎓 منصة الحضور والغياب الذكية</h1>
    <p style="text-align:center; margin-bottom:20px;">اختر نوع الدخول</p>
    <button class="btn role-btn" onclick="showScreen('student-login')">👨‍ دخول الطالب</button>
    <button class="btn role-btn btn-blue" onclick="showScreen('teacher-login')">👨‍🏫 دخول المدرس</button>
  </div>

  <!-- ========== تسجيل دخول الطالب ========== -->
  <div id="screen-student-login" class="hidden">
    <div class="top-bar">
      <h2>👨‍ بوابة الطالب</h2>
      <button class="btn btn-red" onclick="showScreen('home')">رجوع</button>
    </div>

    <div id="student-register-form">
      <div class="card">
        <h2>📝 تسجيل طالب جديد (أول مرة)</h2>
        <input id="s-name" placeholder="الاسم الكامل" />
        <input id="s-number" placeholder="رقم الطالب / القومي" />
        <input id="s-class" placeholder="الفصل (مثال: 3 إعدادي أ)" />
        <button class="btn btn-green" onclick="registerStudent()">تسجيل وإنشاء QR</button>
      </div>

      <div class="card">
        <h2> طالب مسجل مسبقاً</h2>
        <input id="s-login-number" placeholder="أدخل رقم الطالب" />
        <button class="btn btn-blue" onclick="loginStudent()">دخول</button>
      </div>
      <div id="student-msg"></div>
    </div>

    <div id="student-dashboard" class="hidden">
      <div class="card">
        <h2 id="s-welcome"></h2>
        <p>📱 امسح الـ QR التالي عند دخول الحصة:</p>
        <div id="qrcode"></div>
        <p style="text-align:center; font-size:.9rem; opacity:.8;">رقمك: <span id="s-num-display"></span></p>
      </div>
      <button class="btn btn-red" onclick="logoutStudent()">تسجيل خروج</button>
    </div>
  </div>

  <!-- ========== تسجيل دخول المدرس ========== -->
  <div id="screen-teacher-login" class="hidden">
    <div class="top-bar">
      <h2>👨🏫 بوابة المدرس</h2>
      <button class="btn btn-red" onclick="showScreen('home')">رجوع</button>
    </div>
    <div class="card">
      <h2>🔐 دخول المدرس</h2>
      <input id="t-pass" type="password" placeholder="كلمة المرور (الافتراضية: 1234)" />
      <button class="btn btn-green" onclick="loginTeacher()">دخول</button>
      <div id="teacher-msg"></div>
    </div>
  </div>

  <!-- ========== لوحة المدرس ========== -->
  <div id="screen-teacher-dashboard" class="hidden">
    <div class="top-bar">
      <h2>👨‍🏫 لوحة تحكم المدرس</h2>
      <button class="btn btn-red" onclick="logoutTeacher()">خروج</button>
    </div>

    <!-- التبويبات -->
    <div class="tabs">
      <div class="tab active" onclick="switchTab('today')">📅 اليوم الحالي</div>
      <div class="tab" onclick="switchTab('history')">📚 سجل الأيام</div>
      <div class="tab" onclick="switchTab('students')">👥 الطلاب</div>
    </div>

    <!-- ========== تبويب اليوم الحالي ========== -->
    <div id="tab-today">
      <!-- إحصائيات اليوم -->
      <div class="stats">
        <div class="stat"><div class="num" id="st-total">0</div><div class="lbl">إجمالي الطلاب المسجلين</div></div>
        <div class="stat"><div class="num" id="st-present">0</div><div class="lbl">حاضرون اليوم</div></div>
        <div class="stat"><div class="num" id="st-absent">0</div><div class="lbl">غائبون اليوم</div></div>
        <div class="stat"><div class="num" id="st-lessons">0</div><div class="lbl">حصص اليوم</div></div>
      </div>

      <button class="btn btn-red" style="width:100%; padding:15px; font-size:1.1rem;" onclick="endDay()">🏁 إنهاء اليوم وحفظ الملخص</button>

      <!-- إنشاء حصة -->
      <div class="card">
        <h2>📚 إنشاء حصة جديدة</h2>
        <input id="lesson-name" placeholder="اسم الحصة (مثال: رياضيات - الأحد 10 ص)" />
        <button class="btn btn-green" onclick="createLesson()"> إنشاء حصة</button>
        <div id="lesson-builder"></div>
      </div>

      <!-- الحصص النشطة اليوم -->
      <div class="card">
        <h2>🎯 حصص اليوم</h2>
        <div id="today-lessons-list"></div>
      </div>

      <!-- الحصة المفتوحة حالياً -->
      <div class="card" id="active-lesson-card" style="display:none;">
        <h2> الحصة المفتوحة: <span id="active-lesson-name" class="badge"></span></h2>

        <div class="stats">
          <div class="stat"><div class="num" id="al-enrolled">0</div><div class="lbl">مسجلون في الحصة</div></div>
          <div class="stat"><div class="num" id="al-present">0</div><div class="lbl">حاضرون</div></div>
          <div class="stat"><div class="num" id="al-absent">0</div><div class="lbl">غائبون</div></div>
          <div class="stat"><div class="num" id="al-here">0</div><div class="lbl">موجودون الآن</div></div>
        </div>

        <h3 style="margin:15px 0 10px;"> مسح QR للحضور</h3>
        <div id="qr-reader" style="width:100%;"></div>
        <button class="btn btn-blue" id="start-scan-btn" onclick="startScan()">▶️ بدء المسح</button>
        <button class="btn btn-red hidden" id="stop-scan-btn" onclick="stopScan()">⏹️ إيقاف</button>
        <div id="scan-msg"></div>

        <h3 style="margin:20px 0 10px;"> قائمة الطلاب في الحصة</h3>
        <table>
          <thead><tr><th>الاسم</th><th>الرقم</th><th>الفصل</th><th>الحالة</th><th>وقت الحضور</th></tr></thead>
          <tbody id="students-table"></tbody>
        </table>

        <div style="margin-top:15px;">
          <button class="btn btn-red" onclick="closeLesson()">🏁 إنهاء الحصة</button>
        </div>
      </div>
    </div>

    <!-- ========== تبويب سجل الأيام ========== -->
    <div id="tab-history" class="hidden">
      <div class="card">
        <h2>📚 سجل الأيام السابقة</h2>
        <p style="opacity:.8; margin-bottom:15px;">اضغط على أي يوم لعرض تفاصيله</p>
        <div id="days-list"></div>
      </div>

      <!-- تفاصيل يوم محدد -->
      <div class="card hidden" id="day-details">
        <div class="top-bar">
          <h2 id="day-details-title">📅 تفاصيل اليوم</h2>
          <button class="btn btn-red" onclick="closeDayDetails()">إغلاق</button>
        </div>
        <div class="stats" id="day-details-stats"></div>
        <h3> الحصص في هذا اليوم:</h3>
        <div id="day-details-lessons"></div>
      </div>
    </div>

    <!-- ========== تبويب الطلاب ========== -->
    <div id="tab-students" class="hidden">
      <div class="card">
        <h2>👥 جميع الطلاب المسجلين</h2>
        <table>
          <thead><tr><th>الاسم</th><th>الرقم</th><th>الفصل</th><th>إجراءات</th></tr></thead>
          <tbody id="all-students-table"></tbody>
        </table>
      </div>
    </div>

  </div>

</div>

<script>
/* ==================== التخزين ==================== */
const DB = {
  get students() { return JSON.parse(localStorage.getItem('students') || '[]'); },
  set students(v) { localStorage.setItem('students', JSON.stringify(v)); },
  get lessons()  { return JSON.parse(localStorage.getItem('lessons')  || '[]'); },
  set lessons(v) { localStorage.setItem('lessons', JSON.stringify(v)); },
  get days()     { return JSON.parse(localStorage.getItem('days')     || '[]'); },
  set days(v)    { localStorage.setItem('days', JSON.stringify(v)); },
  get session()  { return JSON.parse(localStorage.getItem('session')  || '{}'); },
  set session(v) { localStorage.setItem('session', JSON.stringify(v)); }
};

let currentStudent = null;
let activeLessonId = null;
let qrScanner = null;
let currentTab = 'today';

/* ==================== تواريخ ==================== */
function todayKey() {
  const d = new Date();
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
function formatDate(key) {
  const d = new Date(key);
  const days = ['الأحد','الإثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
  return `${days[d.getDay()]} ${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
}
function isToday(key) { return key === todayKey(); }

/* ==================== التبويبات ==================== */
function switchTab(name) {
  currentTab = name;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  event.target.classList.add('active');
  ['today','history','students'].forEach(t=>{
    document.getElementById('tab-'+t).classList.add('hidden');
  });
  document.getElementById('tab-'+name).classList.remove('hidden');
  if (name==='today') renderTodayTab();
  if (name==='history') renderHistoryTab();
  if (name==='students') renderStudentsTab();
}

/* ==================== التنقل ==================== */
function showScreen(name) {
  ['home','student-login','teacher-login','teacher-dashboard'].forEach(s=>{
    document.getElementById('screen-'+s).classList.add('hidden');
  });
  document.getElementById('screen-'+name).classList.remove('hidden');
}

/* ==================== الطالب ==================== */
function registerStudent() {
  const name   = document.getElementById('s-name').value.trim();
  const number = document.getElementById('s-number').value.trim();
  const cls    = document.getElementById('s-class').value.trim();
  const msg    = document.getElementById('student-msg');

  if (!name || !number || !cls) { msg.innerHTML='<div class="alert alert-error">أكمل كل البيانات</div>'; return; }

  const students = DB.students;
  if (students.find(s=>s.number===number)) {
    msg.innerHTML='<div class="alert alert-error">هذا الرقم مسجل مسبقاً</div>'; return; }

  const student = { id:'STU-'+Date.now(), name, number, cls, createdAt:new Date().toISOString() };
  students.push(student);
  DB.students = students;

  msg.innerHTML='<div class="alert alert-success">✅ تم التسجيل بنجاح</div>';
  setTimeout(()=>enterStudentDashboard(student), 800);
}

function loginStudent() {
  const number = document.getElementById('s-login-number').value.trim();
  const msg = document.getElementById('student-msg');
  const student = DB.students.find(s=>s.number===number);
  if (!student) { msg.innerHTML='<div class="alert alert-error">رقم غير موجود</div>'; return; }
  enterStudentDashboard(student);
}

function enterStudentDashboard(student) {
  currentStudent = student;
  DB.session = { role:'student', id:student.id };
  document.getElementById('student-register-form').classList.add('hidden');
  document.getElementById('student-dashboard').classList.remove('hidden');
  document.getElementById('s-welcome').textContent = 'مرحباً '+student.name+' 👋';
  document.getElementById('s-num-display').textContent = student.number;

  const qrDiv = document.getElementById('qrcode');
  qrDiv.innerHTML = '';
  new QRCode(qrDiv, {
    text: student.id,
    width: 220, height: 220,
    colorDark:'#000', colorLight:'#fff'
  });
}

function logoutStudent() {
  DB.session = {};
  currentStudent = null;
  document.getElementById('student-register-form').classList.remove('hidden');
  document.getElementById('student-dashboard').classList.add('hidden');
  showScreen('home');
}

/* ==================== المدرس ==================== */
function loginTeacher() {
  const pass = document.getElementById('t-pass').value;
  const msg = document.getElementById('teacher-msg');
  if (pass === '1234') {
    DB.session = { role:'teacher' };
    showScreen('teacher-dashboard');
    renderTodayTab();
  } else {
    msg.innerHTML='<div class="alert alert-error">كلمة مرور خاطئة</div>';
  }
}

function logoutTeacher() {
  if (qrScanner) stopScan();
  DB.session = {};
  showScreen('home');
}

/* ==================== إدارة اليوم ==================== */
function ensureTodayDay() {
  const days = DB.days;
  const key = todayKey();
  let day = days.find(d=>d.date===key);
  if (!day) {
    day = { id:'DAY-'+Date.now(), date:key, createdAt:new Date().toISOString(), ended:false };
    days.push(day);
    DB.days = days;
  }
  return day;
}

function endDay() {
  if (!confirm('هل تريد إنهاء اليوم وحفظ الملخص؟ سيتم إغلاق كل الحصص النشطة.')) return;

  const key = todayKey();
  const days = DB.days;
  const day = days.find(d=>d.date===key);
  if (day) {
    day.ended = true;
    day.endedAt = new Date().toISOString();
    const lessons = DB.lessons.filter(l=>l.date===key);
    let totalPresent = 0, totalEnrolled = 0;
    lessons.forEach(l=>{
      totalPresent += Object.keys(l.attendance).length;
      totalEnrolled += l.enrolled.length;
    });
    day.summary = {
      lessonsCount: lessons.length,
      totalPresent,
      totalEnrolled,
      totalAbsent: totalEnrolled - totalPresent
    };
    DB.days = days;
  }

  const lessons = DB.lessons;
  lessons.forEach(l=>{ if (l.date===key) l.active=false; });
  DB.lessons = lessons;

  if (qrScanner) stopScan();
  activeLessonId = null;
  alert('✅ تم إنهاء اليوم وحفظ الملخص');
  renderTodayTab();
}

/* ==================== إنشاء حصة ==================== */
function createLesson() {
  const name = document.getElementById('lesson-name').value.trim();
  if (!name) { alert('اكتب اسم الحصة'); return; }

  const students = DB.students;
  if (students.length === 0) { alert('لا يوجد طلاب مسجلين بعد'); return; }

  let html = '<div class="card" style="margin-top:15px;"><h3>اختر طلاب الحصة:</h3>';
  html += '<label class="checkbox-item"><input type="checkbox" id="sel-all" onchange="toggleAll(this)"> <b>تحديد الكل</b></label>';
  students.forEach(s=>{
    html += `<label class="checkbox-item"><input type="checkbox" class="stu-check" value="${s.id}"> ${s.name} - ${s.cls}</label>`;
  });
  html += '<br><button class="btn btn-green" onclick="confirmLesson()">تأكيد إنشاء الحصة</button>';
  html += '<button class="btn btn-red" onclick="cancelLesson()">إلغاء</button></div>';

  document.getElementById('lesson-builder').innerHTML = html;
}

function cancelLesson() {
  document.getElementById('lesson-builder').innerHTML = '';
}

function toggleAll(master) {
  document.querySelectorAll('.stu-check').forEach(c=>c.checked=master.checked);
}

function confirmLesson() {
  const name = document.getElementById('lesson-name').value.trim();
  const selected = Array.from(document.querySelectorAll('.stu-check:checked')).map(c=>c.value);
  if (selected.length === 0) { alert('اختر طالب واحد على الأقل'); return; }

  const dayKey = todayKey();
  ensureTodayDay();

  const lesson = {
    id:'LES-'+Date.now(),
    name,
    date: dayKey,
    enrolled: selected,
    attendance: {},
    active: true,
    createdAt: new Date().toISOString()
  };

  const lessons = DB.lessons;
  lessons.forEach(l=>{ if (l.date===dayKey) l.active=false; });
  lessons.push(lesson);
  DB.lessons = lessons;

  activeLessonId = lesson.id;
  document.getElementById('lesson-name').value = '';
  document.getElementById('lesson-builder').innerHTML = '';
  renderTodayTab();
}

/* ==================== تبويب اليوم الحالي ==================== */
function renderTodayTab() {
  const students = DB.students;
  const key = todayKey();
  const lessons = DB.lessons.filter(l=>l.date===key);

  let totalPresent = 0;
  let totalEnrolled = 0;
  lessons.forEach(l=>{
    totalPresent += Object.keys(l.attendance).length;
    totalEnrolled += l.enrolled.length;
  });

  document.getElementById('st-total').textContent = students.length;
  document.getElementById('st-present').textContent = totalPresent;
  document.getElementById('st-absent').textContent = totalEnrolled - totalPresent;
  document.getElementById('st-lessons').textContent = lessons.length;

  const list = document.getElementById('today-lessons-list');
  if (lessons.length === 0) {
    list.innerHTML = '<p style="opacity:.7;">لا توجد حصص اليوم بعد</p>';
  } else {
    list.innerHTML = '';
    lessons.slice().reverse().forEach(l=>{
      const p = Object.keys(l.attendance).length;
      const badge = l.active ? '<span class="badge"> نشطة</span>' : '<span class="badge" style="background:#888;">️ منتهية</span>';
      list.innerHTML += `
        <div class="student-item">
          <div><b>${l.name}</b> ${badge}<br><small>حضور: ${p}/${l.enrolled.length}</small></div>
          <div>
            ${!l.active ? `<button class="btn btn-blue" onclick="activateLesson('${l.id}')">تفعيل</button>` : ''}
            <button class="btn btn-red" onclick="deleteLesson('${l.id}')">حذف</button>
          </div>
        </div>`;
    });
  }

  const activeCard = document.getElementById('active-lesson-card');
  const current = lessons.find(l=>l.active);
  if (current) {
    activeLessonId = current.id;
    activeCard.style.display = 'block';
    document.getElementById('active-lesson-name').textContent = current.name;

    const enrolled = current.enrolled.length;
    const present  = Object.keys(current.attendance).length;
    document.getElementById('al-enrolled').textContent = enrolled;
    document.getElementById('al-present').textContent  = present;
    document.getElementById('al-absent').textContent   = enrolled - present;
    document.getElementById('al-here').textContent     = present;

    const tbody = document.getElementById('students-table');
    tbody.innerHTML = '';
    current.enrolled.forEach(sid=>{
      const s = students.find(x=>x.id===sid);
      if (!s) return;
      const att = current.attendance[sid];
      const status = att ? `<span class="present">✅ حاضر</span>` : `<span class="absent">❌ غائب</span>`;
      const time = att ? new Date(att.time).toLocaleTimeString('ar-EG') : '—';
      tbody.innerHTML += `<tr><td>${s.name}</td><td>${s.number}</td><td>${s.cls}</td><td>${status}</td><td>${time}</td></tr>`;
    });
  } else {
    activeCard.style.display = 'none';
    activeLessonId = null;
  }
}

function activateLesson(id) {
  const lessons = DB.lessons;
  const target = lessons.find(l=>l.id===id);
  if (!target) return;
  lessons.forEach(l=>{ if (l.date===target.date) l.active=false; });
  target.active = true;
  DB.lessons = lessons;
  renderTodayTab();
}

function deleteLesson(id) {
  if (!confirm('حذف الحصة؟')) return;
  DB.lessons = DB.lessons.filter(l=>l.id!==id);
  if (activeLessonId === id) activeLessonId = null;
  renderTodayTab();
}

function closeLesson() {
  if (!confirm('إنهاء الحصة الحالية؟')) return;
  const lessons = DB.lessons;
  lessons.forEach(l=>{ if (l.id===activeLessonId) l.active=false; });
  DB.lessons = lessons;
  if (qrScanner) stopScan();
  activeLessonId = null;
  renderTodayTab();
}

/* ==================== تبويب سجل الأيام ==================== */
function renderHistoryTab() {
  const days = DB.days.slice().reverse();
  const list = document.getElementById('days-list');

  if (days.length === 0) {
    list.innerHTML = '<p style="opacity:.7;">لا توجد أيام مسجلة بعد</p>';
    return;
  }

  list.innerHTML = '';
  days.forEach(d=>{
    const lessons = DB.lessons.filter(l=>l.date===d.date);
    let totalPresent = 0, totalEnrolled = 0;
    lessons.forEach(l=>{
      totalPresent += Object.keys(l.attendance).length;
      totalEnrolled += l.enrolled.length;
    });

    let summary = d.summary;
    if (!summary) {
      summary = {
        lessonsCount: lessons.length,
        totalPresent,
        totalEnrolled,
        totalAbsent: totalEnrolled - totalPresent
      };
    }

    const todayBadge = isToday(d.date) ? '<span class="badge">📅 اليوم</span>' : '';
    const endedBadge = d.ended ? '<span class="badge" style="background:#27ae60;">✅ منتهي</span>' : '<span class="badge" style="background:#e67e22;"> جاري</span>';

    list.innerHTML += `
      <div class="day-card ${isToday(d.date)?'today':''}" onclick="showDayDetails('${d.date}')">
        <div class="day-header">
          <div>
            <b style="font-size:1.2rem;">${formatDate(d.date)}</b> ${todayBadge} ${endedBadge}
          </div>
          <div style="opacity:.8;">${lessons.length} حصة</div>
        </div>
        <div class="day-stats">
          <div class="day-stat">📚 ${summary.lessonsCount} حصة</div>
          <div class="day-stat">✅ ${summary.totalPresent} حاضر</div>
          <div class="day-stat">❌ ${summary.totalAbsent} غائب</div>
          <div class="day-stat"> ${summary.totalEnrolled} إجمالي</div>
        </div>
      </div>`;
  });
}

function showDayDetails(dateKey) {
  document.getElementById('day-details').classList.remove('hidden');
  document.getElementById('day-details-title').textContent = '📅 ' + formatDate(dateKey);

  const lessons = DB.lessons.filter(l=>l.date===dateKey);
  const students = DB.students;

  let totalPresent = 0, totalEnrolled = 0;
  lessons.forEach(l=>{
    totalPresent += Object.keys(l.attendance).length;
    totalEnrolled += l.enrolled.length;
  });

  document.getElementById('day-details-stats').innerHTML = `
    <div class="stat"><div class="num">${lessons.length}</div><div class="lbl">حصص</div></div>
    <div class="stat"><div class="num">${totalPresent}</div><div class="lbl">إجمالي الحضور</div></div>
    <div class="stat"><div class="num">${totalEnrolled - totalPresent}</div><div class="lbl">إجمالي الغياب</div></div>
    <div class="stat"><div class="num">${totalEnrolled}</div><div class="lbl">إجمالي المسجلين</div></div>
  `;

  const lessonsDiv = document.getElementById('day-details-lessons');
  if (lessons.length === 0) {
    lessonsDiv.innerHTML = '<p style="opacity:.7;">لا توجد حصص في هذا اليوم</p>';
    return;
  }

  lessonsDiv.innerHTML = '';
  lessons.forEach(l=>{
    const p = Object.keys(l.attendance).length;
    const e = l.enrolled.length;
    let rows = '';
    l.enrolled.forEach(sid=>{
      const s = students.find(x=>x.id===sid);
      if (!s) return;
      const att = l.attendance[sid];
      const status = att ? `<span class="present">✅ حاضر</span>` : `<span class="absent">❌ غائب</span>`;
      const time = att ? new Date(att.time).toLocaleTimeString('ar-EG') : '—';
      rows += `<tr><td>${s.name}</td><td>${s.number}</td><td>${s.cls}</td><td>${status}</td><td>${time}</td></tr>`;
    });

    lessonsDiv.innerHTML += `
      <div class="card" style="margin-top:15px;">
        <h3>📖 ${l.name}</h3>
        <p>الحضور: ${p}/${e}</p>
        <table>
          <thead><tr><th>الاسم</th><th>الرقم</th><th>الفصل</th><th>الحالة</th><th>الوقت</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  });
}

function closeDayDetails() {
  document.getElementById('day-details').classList.add('hidden');
}

/* ==================== تبويب الطلاب ==================== */
function renderStudentsTab() {
  const students = DB.students;
  const allT = document.getElementById('all-students-table');
  allT.innerHTML = '';
  if (students.length === 0) {
    allT.innerHTML = '<tr><td colspan="4">لا يوجد طلاب مسجلين</td></tr>';
  } else {
    students.forEach(s=>{
      allT.innerHTML += `<tr>
        <td>${s.name}</td><td>${s.number}</td><td>${s.cls}</td>
        <td><button class="btn btn-red" onclick="deleteStudent('${s.id}')">حذف</button></td>
      </tr>`;
    });
  }
}

function deleteStudent(id) {
  if (!confirm('حذف الطالب؟')) return;
  DB.students = DB.students.filter(s=>s.id!==id);
  renderStudentsTab();
}

/* ==================== مسح QR ==================== */
function startScan() {
  if (!activeLessonId) { alert('لا توجد حصة نشطة'); return; }
  document.getElementById('start-scan-btn').classList.add('hidden');
  document.getElementById('stop-scan-btn').classList.remove('hidden');

  qrScanner = new Html5Qrcode("qr-reader");
  qrScanner.start(
    { facingMode: "environment" },
    { fps: 10, qrbox: { width: 250, height: 250 } },
    onScanSuccess,
    ()=>{}
  ).catch(err=>{
    document.getElementById('scan-msg').innerHTML = `<div class="alert alert-error">تعذر تشغيل الكاميرا: ${err}</div>`;
  });
}

function stopScan() {
  if (qrScanner) {
    qrScanner.stop().then(()=>{
      qrScanner.clear();
      qrScanner = null;
    }).catch(()=>{});
  }
  document.getElementById('start-scan-btn').classList.remove('hidden');
  document.getElementById('stop-scan-btn').classList.add('hidden');
}

function onScanSuccess(decodedText) {
  const lessons = DB.lessons;
  const lesson = lessons.find(l=>l.id===activeLessonId);
  if (!lesson) return;

  const student = DB.students.find(s=>s.id===decodedText);
  if (!student) { flashMsg('❌ QR غير معروف', 'error'); return; }
  if (!lesson.enrolled.includes(student.id)) { flashMsg('⚠️ الطالب غير مسجل في هذه الحصة', 'error'); return; }
  if (lesson.attendance[student.id]) { flashMsg('ℹ️ '+student.name+' سجل حضوره مسبقاً', 'info'); return; }

  lesson.attendance[student.id] = { time: new Date().toISOString() };
  DB.lessons = lessons;

  speak('حضر ' + student.name);
  flashMsg('✅ تم تسجيل حضور: '+student.name, 'success');
  renderTodayTab();
}

function flashMsg(text, type) {
  const el = document.getElementById('scan-msg');
  el.innerHTML = `<div class="alert alert-${type}">${text}</div>`;
  setTimeout(()=>{ el.innerHTML=''; }, 3000);
}

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ar-SA';
  u.rate = 1;
  u.pitch = 1;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

/* ==================== استعادة الجلسة ==================== */
(function init(){
  const s = DB.session;
  if (s.role === 'student') {
    const st = DB.students.find(x=>x.id===s.id);
    if (st) { showScreen('student-login'); enterStudentDashboard(st); return; }
  }
  if (s.role === 'teacher') {
    showScreen('teacher-dashboard');
    renderTodayTab();
    return;
  }
  showScreen('home');
})();
</script>
</body>
</html>
