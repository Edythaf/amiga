import {getDocument,GlobalWorkerOptions} from '../../vendor/pdfjs/pdf.mjs';
import {workspaceDialog} from './workspace-interactions.js';
GlobalWorkerOptions.workerSrc=new URL('../../vendor/pdfjs/pdf.worker.mjs',import.meta.url).href;
const instances=new WeakMap();
export async function previewPDF(bytes,container,{expanded=false}={}) {
  instances.get(container)?.();let generation=0,currentTask,stopped=false,zoom=1;
  const source=bytes.slice();
  const stop=()=>{stopped=true;generation++;currentTask?.destroy().catch(()=>{});};instances.set(container,stop);
  container.replaceChildren();
  const toolbar=document.createElement('div');toolbar.className='pdf-toolbar';
  const pages=document.createElement('div');pages.className='pdf-pages';
  const label=document.createElement('span');label.setAttribute('aria-live','polite');
  function button(text,title,action){const b=document.createElement('button');b.type='button';b.textContent=text;b.setAttribute('aria-label',title);b.onclick=action;toolbar.append(b);return b;}
  const less=button('−','Perkecil PDF',()=>{zoom=Math.max(.5,zoom-.25);render();});
  const more=button('+','Perbesar PDF',()=>{zoom=Math.min(3,zoom+.25);render();});
  button('Pas lebar','Sesuaikan PDF ke lebar panel',()=>{zoom=1;render();});toolbar.append(label);
  if(!expanded)button('Perluas PDF','Buka PDF dalam tampilan besar',()=>{
    const {body}=workspaceDialog('Pratinjau PDF',{wide:true,onClose:()=>instances.get(target)?.()});
    const target=document.createElement('div');target.className='pdf-view pdf-expanded';body.append(target);previewPDF(source,target,{expanded:true});
  });
  container.append(toolbar,pages);
  async function render(){
    const token=++generation;currentTask?.destroy().catch(()=>{});pages.replaceChildren();
    less.disabled=zoom<=.5;more.disabled=zoom>=3;label.textContent=Math.round(zoom*100)+'%';
    const hint=document.createElement('p');hint.className='subtle';hint.textContent='Memuat halaman PDF…';pages.append(hint);
    let task;
    try{
      // LoadingTask owns worker teardown in PDF.js 6; the document proxy has no destroy().
      task=getDocument({data:source.slice(),isEvalSupported:false,useSystemFonts:true});currentTask=task;
      const pdf=await task.promise;
      if(stopped||token!==generation||!container.isConnected)return;
      pages.replaceChildren();
      for(let pageNo=1;pageNo<=pdf.numPages;pageNo++){
        if(stopped||token!==generation||!container.isConnected)break;
        const page=await pdf.getPage(pageNo),base=page.getViewport({scale:1});
        const scale=Math.min(2,Math.max(.25,(container.clientWidth-32)/base.width))*zoom,viewport=page.getViewport({scale});
        // Bound bitmap memory across all pages while retaining the requested CSS zoom.
        const density=Math.min(1.5,Math.sqrt(12000000/(pdf.numPages*viewport.width*viewport.height)));
        const canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width*density);canvas.height=Math.ceil(viewport.height*density);canvas.style.width=`${viewport.width}px`;canvas.style.height=`${viewport.height}px`;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',`Halaman PDF ${pageNo} dari ${pdf.numPages}`);pages.append(canvas);
        await page.render({canvasContext:canvas.getContext('2d'),viewport,transform:[density,0,0,density,0,0]}).promise;
        const caption=document.createElement('p');caption.className='subtle';caption.textContent=`Halaman ${pageNo} / ${pdf.numPages}`;pages.append(caption);
      }
    }catch(error){if(!stopped&&token===generation&&container.isConnected){hint.textContent=`PDF tidak dapat dirender: ${error.message}.`;pages.replaceChildren(hint);}}
    finally{if(task)await task.destroy().catch(()=>{});if(currentTask===task)currentTask=null;}
  }
  await render();
}
