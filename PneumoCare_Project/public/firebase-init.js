// public/firebase-init.js
// Firebase v9 modular (ES module) - exports auth, db, storage
import { initializeApp } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-firestore.js";
import { getStorage } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-storage.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-auth.js";

// <-- Replace the config below with the project config from your Firebase Console if different -->
const firebaseConfig = {
  apiKey: "Enter Your API Key Here",
  authDomain: "Enter Your Auth Domain Here",
  projectId: "Enter Your Project ID Here",
  storageBucket: "Enter Your Storage Bucket Here",
  messagingSenderId: "Enter Your Messaging Sender ID Here",
  appId: "Enter Your App ID Here"
};


// Initialize
const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const auth = getAuth(app);

// Note: export for use in other modules
