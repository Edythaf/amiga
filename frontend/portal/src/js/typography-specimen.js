import {themeControl,bindTheme} from './design.js';
document.querySelector('#specimen-theme').innerHTML=themeControl();
bindTheme();
document.querySelector('#sample-action').addEventListener('click',()=>{
  document.querySelector('#sample-result').hidden=false;
});
