import {initialState} from './domain.js';
const KEY='amiga_workspace_demo_v1';let db,memory=new Map();export let fileWarning='';
export function loadState(){try{const value=JSON.parse(localStorage.getItem(KEY));if(value?.schema===1)return value;}catch{}return initialState();}
export function persist(state){try{localStorage.setItem(KEY,JSON.stringify(state));state.storageWarning='';}catch{state.storageWarning='Storage browser penuh/tidak tersedia. Perubahan tetap di memori sesi ini; ekspor cadangan metadata sebelum refresh.';}}
export async function openFiles(){try{db=await new Promise((resolve,reject)=>{const req=indexedDB.open('amiga_workspace_demo_files',1);req.onupgradeneeded=()=>req.result.createObjectStore('files');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}catch{fileWarning='Penyimpanan PDF tidak tersedia. PDF hanya bertahan di sesi ini.';}}
export async function storeFile(bytes,key=crypto.randomUUID()) {
  memory.set(key,bytes);
  if(db)try{await new Promise((resolve,reject)=>{const tx=db.transaction('files','readwrite');tx.objectStore('files').put(bytes,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}catch{fileWarning='Storage PDF penuh. PDF baru hanya tersedia sampai halaman ditutup.';}
  return key;
}
export async function readFile(key){if(memory.has(key))return memory.get(key);if(db)return new Promise((resolve,reject)=>{const req=db.transaction('files').objectStore('files').get(key);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});return null;}
export async function clearFiles(){memory.clear();if(db)await new Promise((resolve,reject)=>{const tx=db.transaction('files','readwrite');tx.objectStore('files').clear();tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}
