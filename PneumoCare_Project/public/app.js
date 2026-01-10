
// public/app.js
import { db, storage, auth } from "./firebase-init.js";
import { createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-auth.js";
import { collection, addDoc, doc, setDoc, getDocs, getDoc, query, orderBy, limit, where } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-firestore.js";
import { ref, uploadBytes, getDownloadURL } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-storage.js";

// ----------------- CONFIG -----------------
const MODEL_API_URL = "http://127.0.0.1:5000/predict";  // Make sure Flask server is running on port 5000
// ------------------------------------------

/* ------- UTILS ------- */
function generatePatientID() {
  const year = new Date().getFullYear();
  const rand = Math.floor(10000 + Math.random() * 90000); // 5 digits
  return `PNC-${year}-${rand}`;
}

function el(q) { return document.querySelector(q); }
function els(q) { return document.querySelectorAll(q); }

function clearForm() {
  el('#firstName').value = '';
  el('#lastName').value = '';
  el('#phone').value = '';
  el('#bloodGroup').value = '';
  el('#city').value = '';
  el('#age').value = '';
  el('#notes').value = '';
  el('#patientIdDisplay').textContent = '';
  el('#xrFile').value = '';
  el('#resultCard').innerHTML = '';
  selectedPatientId = null;
}

/* ------- UPDATE NAVIGATION BASED ON AUTH STATE ------- */
function updateNavigation(isLoggedIn) {
  // Update header navigation
  const navLinks = document.querySelectorAll('.nav-links');
  navLinks.forEach(nav => {
    const loginLink = nav.querySelector('a[href="login.html"], #navLogin');
    const registerLink = nav.querySelector('a[href="register.html"], #navRegister');
    
    if (loginLink) {
      if (isLoggedIn) {
        loginLink.href = 'contact.html';
        loginLink.textContent = 'Contact';
      } else {
        loginLink.href = 'login.html';
        loginLink.textContent = 'Login';
      }
    }
    
    if (registerLink) {
      if (isLoggedIn) {
        registerLink.href = 'about.html';
        registerLink.textContent = 'About Us';
      } else {
        registerLink.href = 'register.html';
        registerLink.textContent = 'Register';
      }
    }
  });
  
  // Update crystal navigation
  const crystalLogin = document.querySelector('#crystalLogin');
  const crystalRegister = document.querySelector('#crystalRegister');
  
  if (crystalLogin) {
    if (isLoggedIn) {
      crystalLogin.href = 'contact.html';
      crystalLogin.title = 'Contact';
      crystalLogin.textContent = '📧';
    } else {
      crystalLogin.href = 'login.html';
      crystalLogin.title = 'Login';
      crystalLogin.textContent = '🔐';
    }
  }
  
  if (crystalRegister) {
    if (isLoggedIn) {
      crystalRegister.href = 'about.html';
      crystalRegister.title = 'About';
      crystalRegister.textContent = 'ℹ️';
    } else {
      crystalRegister.href = 'register.html';
      crystalRegister.title = 'Register';
      crystalRegister.textContent = '📝';
    }
  }
}

// Check auth state and update navigation
auth.onAuthStateChanged((user) => {
  updateNavigation(!!user);
  // Initialize dashboard if on dashboard page
  if (document.body.contains(document.querySelector('#welcomeBadge'))) {
    initDashboard();
  }
});

/* ------- THEME & SPLASH ------- */
const splash = el('#splash');
const appRoot = el('#app');
const enterBtn = el('#enterBtn');
if (enterBtn) enterBtn.addEventListener('click', () => {
  if (splash) splash.classList.add('hidden');
  if (appRoot) appRoot.classList.remove('hidden');
});

// Load saved theme on page load
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);

// Update theme toggle button icon
function updateThemeIcon() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const themeButtons = document.querySelectorAll('#themeToggle, #themeToggleSide');
  themeButtons.forEach(btn => {
    btn.textContent = currentTheme === 'dark' ? '☀️' : '🌙';
  });
}
updateThemeIcon();

// Theme toggle functionality
const themeToggleButtons = document.querySelectorAll('#themeToggle, #themeToggleSide');
themeToggleButtons.forEach(b => b.addEventListener('click', () => {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  const newTheme = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  updateThemeIcon();
}));

/* ------- AUTH: Register + Login (index.html) ------- */
const registerForm = el('#registerForm');
const loginForm = el('#loginForm');
const pidLoginBtn = el('#loginByPID');
const pidLoginBox = el('#pidLoginBox');
const pidLoginBtnConfirm = el('#pidLoginBtn');

if (registerForm) {
  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const first = el('#regFirst').value.trim();
    const last = el('#regLast').value.trim();
    const phone = el('#regPhone').value.trim();
    const city = el('#regCity').value.trim();
    const email = el('#regEmail').value.trim();
    const password = el('#regPassword').value;

    try {
      const userCred = await createUserWithEmailAndPassword(auth, email, password);
      const uid = userCred.user.uid;
      // store profile in Firestore users collection
      const patientID = generatePatientID();
      await setDoc(doc(db, 'users', uid), {
        uid, patientID, firstName: first, lastName: last, phone, city, createdAt: new Date().toISOString()
      });
      // Auto-login and redirect to dashboard
      el('#regMsg').textContent = `Registration successful! Redirecting to dashboard...`;
      el('#regMsg').style.color = 'var(--success)';
      setTimeout(() => {
        // Removed page reload per user request
      }, 1000);
    } catch (err) {
      el('#regMsg').textContent = 'Error: ' + err.message;
      el('#regMsg').style.color = 'var(--error)';
    }
  });
}

if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = el('#loginEmail').value.trim();
    const password = el('#loginPassword').value;
    try {
      const uc = await signInWithEmailAndPassword(auth, email, password);
      // success -> redirect to dashboard.html
      // Removed page reload per user request
    } catch (err) {
      el('#loginMsg').textContent = 'Login failed: ' + err.message;
    }
  });
}

if (pidLoginBtn) {
  pidLoginBtn.addEventListener('click', () => {
    pidLoginBox.classList.toggle('hidden');
  });
}
if (pidLoginBtnConfirm) {
  pidLoginBtnConfirm.addEventListener('click', async () => {
    const pid = el('#pidInput').value.trim();
    if (!pid) return alert('Enter patient ID');
    // find user with that patientID
    const q = query(collection(db, 'users'), where('patientID', '==', pid));
    const snap = await getDocs(q);
    if (snap.empty) return alert('Patient ID not found');
    // We do a simple redirect to dashboard and store a session identifier in localStorage
    if (snap.empty) return alert("Invalid Patient ID");
    const uid = snap.docs[0].id;
    localStorage.setItem('anon_uid', uid);
    // Removed page reload per user request
  });
}

/* ------- DASHBOARD (dashboard.html) ------- */
async function initDashboard() {
  // if not on dashboard page skip
  if (!document.body.contains(el('#patientList'))) return;

  // show welcome badge
  let user = auth.currentUser;
  if (!user) {
    // check anon login
    const anon = localStorage.getItem('anon_uid');
    if (anon) {
      const userDoc = await getDoc(doc(db, 'users', anon));
      if (userDoc.exists()) {
        el('#welcomeBadge').innerHTML = `<span class="badge">ID: ${userDoc.data().patientID}</span>`;
      }
    } else {
      // require auth
      // if not authenticated redirect to index
      // but we allow anon (PID) flows too
    }
  } else {
    const udoc = await getDoc(doc(db, 'users', user.uid));
    if (udoc.exists()) {
      el('#welcomeBadge').innerHTML = `<span class="badge">ID: ${udoc.data().patientID}</span>`;
    }
  }

  // bind logout
  const logoutBtn = el('#logoutBtn');
  if (logoutBtn && !logoutBtn._listener_attached) {
    logoutBtn.addEventListener('click', async () => {
      try {
        await signOut(auth);
        localStorage.removeItem('anon_uid');
        console.log('✅ Logged out successfully');
        // Redirect to home page
        window.location.href = 'index.html';
      } catch (err) { alert('Logout error: ' + err.message); }
    });
    logoutBtn._listener_attached = true;
  }

  // load patients (for signed in users show own entry, for admin-style usage show many)
  await loadPatients();

  // new patient
  const newPatientBtn = el('#newPatientBtn');
  if (newPatientBtn && !newPatientBtn._listener_attached) {
    newPatientBtn.addEventListener('click', () => {
      clearForm();
      // create display patient id immediately
      const newId = generatePatientID();
      el('#patientIdDisplay').textContent = 'New Patient ID: ' + newId;
      el('#patientIdDisplay').dataset.newid = newId;
      el('#welcomeBadge').innerHTML = `<span class="badge">ID: ${newId}</span>`;
    });
    newPatientBtn._listener_attached = true;
  }

  // save / update patient details
  const patientForm = el('#patientForm');
  if (!patientForm._listener_attached) {
    patientForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = el('#firstName').value.trim();
      const l = el('#lastName').value.trim();
      const phone = el('#phone').value.trim();
      const blood = el('#bloodGroup').value.trim();
      const city = el('#city').value.trim();
      const age = el('#age').value;
      const notes = el('#notes').value;

      // if selectedPatientId exists -> update else create
      if (selectedPatientId) {
        await setDoc(doc(db, 'patients', selectedPatientId), {
          firstName: f, lastName: l, phone, bloodGroup: blood, city, age, notes, updatedAt: new Date().toISOString()
        }, { merge: true });
        alert('Patient updated');
      } else {
        const pid = el('#patientIdDisplay').dataset.newid || generatePatientID();
        const docRef = await addDoc(collection(db, 'patients'), {
          patientID: pid, firstName: f, lastName: l, phone, bloodGroup: blood, city, age, notes, createdAt: new Date().toISOString()
        });
        selectedPatientId = docRef.id;
        el('#patientIdDisplay').textContent = 'Patient ID: ' + pid;
        el('#welcomeBadge').innerHTML = `<span class="badge">ID: ${pid}</span>`;
        alert('Patient saved: ' + pid);
        await loadPatients();
      }
    });
    patientForm._listener_attached = true;
  }

  // clear form button
  const clearFormBtn = el('#clearFormBtn');
  if (clearFormBtn && !clearFormBtn._listener_attached) {
    clearFormBtn.addEventListener('click', (e) => {
      e.preventDefault();
      clearForm();
    });
    clearFormBtn._listener_attached = true;
  }

  // upload & predict
  const uploadBtn = el('#uploadAndPredict');
  if (uploadBtn && !uploadBtn._listener_attached) {
    uploadBtn.addEventListener('click', async () => {
      if (!selectedPatientId) return alert('Select or create a patient first');
      const fileInput = el('#xrFile');
      if (!fileInput.files[0]) return alert('Select an image file first');
      const file = fileInput.files[0];

      el('#uploadStatus').textContent = 'Sending to AI model...';
      el('#uploadStatus').style.color = 'var(--muted)';
      
      console.log('=== UPLOAD & PREDICT START ===');
      console.log('Patient ID:', selectedPatientId);
      console.log('File:', file.name);
      
      try {
        // Step 1: Send file to Flask for prediction
        const form = new FormData();
        form.append('file', file);
        form.append('patient_id', selectedPatientId || 'anon');
        
        console.log('Sending file to Flask API...');
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 90000);

        const res = await fetch(MODEL_API_URL, { 
          method: 'POST', 
          body: form,
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        console.log('Response status:', res.status);
        
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({error: 'Unknown error'}));
          console.error('API Error:', errorData);
          throw new Error(errorData.error || `Error ${res.status}`);
        }
        
        const json = await res.json();
        console.log('✅ Prediction received:', json.prediction, json.confidence);
        
        // Step 2: Update UI immediately with prediction
        el('#uploadStatus').textContent = '';
        el('#uploadStatus').style.color = '';
        
        const predictionColor = json.prediction === 'Pneumonia' ? '#ff4444' : '#44aa44';
        const confidencePercent = (json.confidence * 100).toFixed(1);
        
        el('#resultCard').innerHTML = `
          <div style="padding:24px;background:rgba(255,255,255,0.1);border-radius:12px;border:2px solid ${predictionColor};backdrop-filter:blur(10px);">
            <div style="font-size:2rem;font-weight:800;margin-bottom:16px;color:${predictionColor};">
              ✓ ${json.prediction.toUpperCase()}
            </div>
            <div style="font-size:1.3rem;margin-bottom:24px;">
              <span style="color:#999;">Confidence: </span>
              <span style="font-weight:700;color:${predictionColor};">${confidencePercent}%</span>
            </div>
          </div>
        `;
        
        console.log('✅ Result displayed on page');
        
        // Step 3: Save to Firestore in background (don't block user)
        try {
          await addDoc(collection(db, 'patients', selectedPatientId, 'history'), {
            timestamp: new Date().toISOString(),
            prediction: json.prediction,
            confidence: json.confidence
          });
          console.log('✅ Saved to database');
        } catch (dbError) {
          console.warn('⚠️ Database save failed (not critical):', dbError.message);
          // Don't throw - user already has the result
        }
        
        // Reload history display
        try {
          await loadHistory(selectedPatientId);
          console.log('✅ History updated');
        } catch (historyError) {
          console.warn('⚠️ History reload failed:', historyError.message);
        }
        
      } catch (err) {
        el('#uploadStatus').textContent = '';
        el('#uploadStatus').style.color = '';
        console.error('❌ Error:', err.message);
        console.error('Error details:', err);
        
        // Provide helpful error message
        let errorMsg = err.message;
        if (err.message.includes('Failed to fetch')) {
          errorMsg = 'Cannot connect to Flask server (http://127.0.0.1:5000)\n\n' +
                     '✓ Make sure Flask is running: python app.py\n' +
                     '✓ Check http://127.0.0.1:5000/health in browser\n' +
                     '✓ If using a file://, switch to http://localhost:PORT/';
        }
        alert('❌ Error: ' + errorMsg);
      }
    });
    uploadBtn._listener_attached = true;
  }

  // download latest report
  const downloadBtn = el('#downloadReport');
  if (downloadBtn && !downloadBtn._listener_attached) {
    downloadBtn.addEventListener('click', async () => {
      if (!selectedPatientId) return alert('Select a patient first');
      // fetch patient and last history
      const pdoc = await getDoc(doc(db, 'patients', selectedPatientId));
      const psnap = pdoc.data();
      const hq = query(collection(db, 'patients', selectedPatientId, 'history'), orderBy('timestamp', 'desc'), limit(1));
      const hsnap = await getDocs(hq);
      const last = hsnap.docs[0]?.data();

    // build printable element with PneumoCare design
    const panel = document.createElement('div');
    panel.style = 'padding:0;background:#f8f9fb;color:#1a1a1c;width:900px;font-family:Inter,Arial,sans-serif;margin:0;position:relative;overflow:hidden';
    panel.innerHTML = `
      <style>
        .report-container * { margin: 0; padding: 0; box-sizing: border-box; }
        .report-header {
          background: linear-gradient(135deg, #4a9fca 0%, #3a3a42 50%, #e65a3c 100%);
          padding: 40px 48px;
          color: white;
          position: relative;
          overflow: hidden;
        }
        .report-header::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, rgba(74, 159, 202, 0.3) 0%, rgba(230, 90, 60, 0.2) 100%);
          opacity: 0.5;
        }
        .report-header-content {
          position: relative;
          z-index: 1;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .report-title {
          font-size: 42px;
          font-weight: 700;
          letter-spacing: -0.02em;
          text-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .report-date {
          font-size: 16px;
          opacity: 0.95;
          margin-top: 8px;
          font-weight: 400;
        }
        .report-logo-container {
          background: white;
          padding: 12px 20px;
          border-radius: 16px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }
        .report-logo {
          height: 56px;
          display: block;
        }
        .report-body {
          padding: 48px;
          background: white;
        }
        .report-section {
          margin-bottom: 40px;
          background: linear-gradient(145deg, #ffffff 0%, rgba(74, 159, 202, 0.03) 100%);
          padding: 32px;
          border-radius: 20px;
          box-shadow: 0 4px 16px rgba(58, 58, 66, 0.08);
          border: 1px solid rgba(74, 159, 202, 0.15);
        }
        .section-title {
          font-size: 24px;
          font-weight: 700;
          color: #3a3a42;
          margin-bottom: 24px;
          padding-bottom: 12px;
          border-bottom: 3px solid transparent;
          border-image: linear-gradient(90deg, #4a9fca 0%, #e65a3c 100%) 1;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .section-icon {
          font-size: 28px;
        }
        .info-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 20px;
          margin-top: 20px;
        }
        .info-item {
          background: rgba(74, 159, 202, 0.05);
          padding: 16px 20px;
          border-radius: 12px;
          border-left: 4px solid #4a9fca;
        }
        .info-label {
          font-size: 13px;
          color: #6b7280;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 6px;
        }
        .info-value {
          font-size: 18px;
          color: #1a1a1c;
          font-weight: 600;
        }
        .diagnosis-result {
          background: linear-gradient(135deg, rgba(74, 159, 202, 0.15) 0%, rgba(230, 90, 60, 0.1) 100%);
          padding: 28px 32px;
          border-radius: 16px;
          margin-top: 20px;
          border: 2px solid rgba(74, 159, 202, 0.3);
          text-align: center;
        }
        .diagnosis-label {
          font-size: 16px;
          color: #6b7280;
          font-weight: 600;
          margin-bottom: 12px;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        .diagnosis-value {
          font-size: 36px;
          font-weight: 700;
          background: linear-gradient(135deg, #4a9fca 0%, #e65a3c 100%);
          -webkit-background-clip: text;
          background-clip: text;
          -webkit-text-fill-color: transparent;
          margin-bottom: 12px;
        }
        .confidence-bar {
          background: rgba(74, 159, 202, 0.2);
          height: 32px;
          border-radius: 16px;
          overflow: hidden;
          margin-top: 16px;
          position: relative;
        }
        .confidence-fill {
          background: linear-gradient(90deg, #4a9fca 0%, #5ab0d8 100%);
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-weight: 700;
          font-size: 14px;
          box-shadow: inset 0 2px 4px rgba(255,255,255,0.3);
        }
        .report-footer {
          background: linear-gradient(135deg, rgba(74, 159, 202, 0.08) 0%, rgba(230, 90, 60, 0.05) 100%);
          padding: 32px 48px;
          text-align: center;
          border-top: 2px solid rgba(74, 159, 202, 0.2);
        }
        .footer-disclaimer {
          font-size: 13px;
          color: #6b7280;
          line-height: 1.6;
          margin-bottom: 16px;
        }
        .footer-branding {
          font-size: 12px;
          color: #9ca3af;
          font-weight: 600;
        }
        .decorative-wave {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 80px;
          background: linear-gradient(135deg, rgba(74, 159, 202, 0.1) 0%, rgba(230, 90, 60, 0.05) 100%);
          clip-path: polygon(0 50%, 100% 20%, 100% 100%, 0 100%);
        }
      </style>
      <div class="report-container">
        <div class="report-header">
          <div class="report-header-content">
            <div>
              <div class="report-title">PneumoCare Report</div>
              <div class="report-date">📅 ${new Date().toLocaleString('en-US', { dateStyle: 'full', timeStyle: 'short' })}</div>
            </div>
            <div class="report-logo-container">
              <img src="./assets/logo.png" class="report-logo" alt="PneumoCare" />
            </div>
          </div>
        </div>
        
        <div class="report-body">
          <div class="report-section">
            <div class="section-title">
              <span class="section-icon">👤</span>
              Patient Information
            </div>
            <div class="info-grid">
              <div class="info-item">
                <div class="info-label">Patient ID</div>
                <div class="info-value">${psnap.patientID || 'PNC-2025-56805'}</div>
              </div>
              <div class="info-item">
                <div class="info-label">Full Name</div>
                <div class="info-value">${psnap.firstName || ''} ${psnap.lastName || ''}</div>
              </div>
              <div class="info-item">
                <div class="info-label">Phone Number</div>
                <div class="info-value">${psnap.phone || 'N/A'}</div>
              </div>
              <div class="info-item">
                <div class="info-label">City</div>
                <div class="info-value">${psnap.city || 'N/A'}</div>
              </div>
              <div class="info-item">
                <div class="info-label">Age</div>
                <div class="info-value">${psnap.age || 'N/A'} years</div>
              </div>
              <div class="info-item">
                <div class="info-label">Blood Group</div>
                <div class="info-value">${psnap.bloodGroup || 'N/A'}</div>
              </div>
            </div>
          </div>
          
          <div class="report-section">
            <div class="section-title">
              <span class="section-icon">🩺</span>
              Diagnosis Results
            </div>
            <div class="diagnosis-result">
              <div class="diagnosis-label">Result</div>
              <div class="diagnosis-value">${last?.prediction || 'N/A'}</div>
              <div class="diagnosis-label">Confidence Level</div>
              <div class="confidence-bar">
                <div class="confidence-fill" style="width: ${last?.confidence ? (last.confidence * 100).toFixed(1) : 0}%">
                  ${last?.confidence ? (last.confidence * 100).toFixed(1) : 0}%
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="report-footer">
          <div class="decorative-wave"></div>
          <div class="footer-disclaimer">
            ⚠️ This report is generated for demonstration and academic purposes only.<br>
            Not intended for clinical diagnosis. Consult a licensed medical professional.
          </div>
          <div class="footer-branding">
            Generated by <strong>PneumoCare</strong> — AI-Powered Chest X-Ray Analysis System<br>
            © 2025 PneumoCare. All rights reserved.
          </div>
        </div>
      </div>
    `;
      document.body.appendChild(panel);
      const canvas = await html2canvas(panel, { scale: 2 });
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({ unit: 'px', format: [canvas.width, canvas.height] });
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, canvas.width, canvas.height);
      pdf.save(`report_${psnap.firstName || 'patient'}.pdf`);
      document.body.removeChild(panel);
    });
    downloadBtn._listener_attached = true;
  }
}

/* ------- DATA LOADERS ------- */
let selectedPatientId = null;
async function loadPatients() {
  const list = el('#patientList');
  list.innerHTML = '';
  const q = query(collection(db, 'patients'), orderBy('createdAt', 'desc'), limit(50));
  const snap = await getDocs(q);
  snap.forEach(docSnap => {
    const d = docSnap.data();
    const card = document.createElement('div');
    card.className = 'patientCard';
    card.innerHTML = `<strong>${d.firstName || ''} ${d.lastName || ''}</strong><div class="muted">${d.patientID || ''}</div>`;
    card.addEventListener('click', async () => {
      selectedPatientId = docSnap.id;
      await selectPatient(docSnap.id);
    });
    list.appendChild(card);
  });
}

async function selectPatient(id) {
  selectedPatientId = id;
  const pdoc = await getDoc(doc(db, 'patients', id));
  if (!pdoc.exists()) return alert('Patient not found');
  const d = pdoc.data();
  el('#firstName').value = d.firstName || '';
  el('#lastName').value = d.lastName || '';
  el('#phone').value = d.phone || '';
  el('#bloodGroup').value = d.bloodGroup || '';
  el('#city').value = d.city || '';
  el('#age').value = d.age || '';
  el('#notes').value = d.notes || '';
  el('#patientIdDisplay').textContent = 'Patient ID: ' + (d.patientID || 'N/A');
  el('#welcomeBadge').innerHTML = `<span class="badge">ID: ${d.patientID || 'N/A'}</span>`;
  await loadHistory(id);
}

async function loadHistory(patientId) {
  const list = el('#historyList');
  list.innerHTML = '';
  const hq = query(collection(db, 'patients', patientId, 'history'), orderBy('timestamp', 'desc'), limit(30));
  const hsnap = await getDocs(hq);
  hsnap.forEach(docSnap => {
    const d = docSnap.data();
    const elDiv = document.createElement('div');
    elDiv.className = 'patientCard';
    elDiv.innerHTML = `<div>${new Date(d.timestamp || Date.now()).toLocaleString()}</div>
      <div>${d.prediction} (${(d.confidence*100).toFixed(1)}%)</div>`;
    list.appendChild(elDiv);
  });
}

/* ------- INIT ------- */
document.addEventListener('DOMContentLoaded', async () => {
  await initDashboard();
});