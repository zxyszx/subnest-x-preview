/* Keep upstream routes and component code intact. Only replace the updater entry. */
(() => {
  if (location.pathname.startsWith('/__preview/')) return;
  let panel;
  let runningVersion;
  let versionRequest;
  const modalStyle=document.createElement('style');
  modalStyle.textContent=`
    dialog[data-subnest-update] {background:var(--background,#fff);border:1px solid var(--border,#ddd);border-radius:var(--radius-lg,8px);box-shadow:0 10px 15px -3px #0000001a,0 4px 6px -4px #0000001a;}
    dialog[data-subnest-update]::backdrop {background:rgb(0 0 0 / 50%);}
    dialog[data-subnest-update]:focus {outline:none;}
    dialog[data-subnest-update] [data-slot="dialog-close"] {position:absolute;inset-inline-end:16px;top:16px;z-index:2;display:flex;align-items:center;justify-content:center;width:24px;height:24px;padding:0;border:0;border-radius:var(--radius-xs,6px);background:transparent;color:inherit;opacity:.7;cursor:pointer;box-shadow:0 4px 6px -1px #0000001a,0 2px 4px -2px #0000001a;transition:opacity .15s,box-shadow .15s;}
    dialog[data-subnest-update] [data-slot="dialog-close"]:hover {opacity:1;box-shadow:0 10px 15px -3px #0000001a,0 4px 6px -4px #0000001a;}
    dialog[data-subnest-update] [data-slot="dialog-close"]:focus-visible {outline:2px solid var(--ring,#8b5cf6);outline-offset:2px;}
    dialog[data-subnest-update] [data-slot="dialog-close"] svg {width:24px;height:24px;pointer-events:none;}
    @media(pointer:coarse) {dialog[data-subnest-update] [data-slot="dialog-close"]::after {content:"";position:absolute;inset:-10px;}}
    @media(prefers-reduced-motion:reduce) {dialog[data-subnest-update] [data-slot="dialog-close"] {transition:none;}}
  `;
  document.head.append(modalStyle);
  const loadVersion = () => versionRequest ||= fetch('/__preview/version', {cache:'no-store'}).then(r => { if (!r.ok) throw Error('version'); return r.json(); }).then(state => { runningVersion=state.running; updateOwnVersion(); }).catch(() => { versionRequest=null; });
  const open = opener => {
    if (panel) return;
    panel = document.createElement('dialog');
    panel.setAttribute('aria-label', '检查更新');
    panel.setAttribute('data-slot','dialog-content');
    panel.setAttribute('data-subnest-update','');
    panel.tabIndex=-1;
    panel.style.cssText = 'position:fixed;inset:0;margin:auto;padding:0;display:block;max-width:calc(100vw - 2rem);width:448px;height:min(660px,90dvh);max-height:90dvh;transform:none;color:var(--foreground,#111);overflow:hidden;';
    const close = document.createElement('button');
    close.type='button';close.setAttribute('aria-label','关闭检查更新');close.setAttribute('data-slot','dialog-close');
    close.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
    const frame = document.createElement('iframe');
    frame.title = '版本更新'; frame.src = '/__preview/update';
    frame.addEventListener('load', () => {
      const doc=frame.contentDocument;
      if(!doc)return;
      // Use the installed theme and fonts, including its original font-face URLs.
      for(const link of document.querySelectorAll('link[rel=stylesheet]')) {
        const copy=link.cloneNode(); copy.href=link.href; doc.head.prepend(copy);
      }
      const rootStyle=getComputedStyle(document.documentElement);
      doc.documentElement.className=document.documentElement.className;
      doc.documentElement.lang=document.documentElement.lang||'zh-CN';
      for(const name of rootStyle) if(name.startsWith('--')) doc.documentElement.style.setProperty(name,rootStyle.getPropertyValue(name));
      doc.documentElement.style.fontFamily=getComputedStyle(document.body).fontFamily;
      doc.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();panel?.close();}});
      const fit=()=>{if(!panel)return;const style=getComputedStyle(panel);const border=parseFloat(style.borderTopWidth)+parseFloat(style.borderBottomWidth);panel.style.height=Math.min(doc.body.getBoundingClientRect().height+border+2,window.innerHeight*.9)+'px';};
      const sizing=new ResizeObserver(fit);sizing.observe(doc.body);panel.addEventListener('close',()=>sizing.disconnect(),{once:true});fit();
    });
    frame.style.cssText = 'display:block;width:100%;height:100%;border:0;background:transparent;';
    close.onclick = () => panel.close();
    const oldOverflow=document.documentElement.style.overflow;
    let outsideDown=false;
    const outside=event=>{const r=panel.getBoundingClientRect();return event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom;};
    panel.addEventListener('pointerdown',event=>{outsideDown=outside(event);});
    panel.addEventListener('pointerup',event=>{if(outsideDown&&outside(event))panel.close();outsideDown=false;});
    panel.addEventListener('close', () => { panel.remove(); panel = null;document.documentElement.style.overflow=oldOverflow;if(opener?.isConnected)opener.focus({preventScroll:true}); });
    panel.append(close,frame); document.body.append(panel); panel.showModal();
    document.documentElement.style.overflow='hidden';
    panel.focus({preventScroll:true});
  };
  const label = node => {
    if (!node || !node.closest) return null;
    const item = node.closest('[role="menuitem"],button');
    if (!item) return null;
    const text = item.textContent.trim();
    return /^(检查更新|Check for updates|Check Update|预览更新)$/i.test(text) ? item : null;
  };
  document.addEventListener('click', event => {
    if (!label(event.target)) return;
    const menu=event.target.closest('[role="menu"]');
    const opener=document.getElementById(menu?.getAttribute('aria-labelledby'))||document.activeElement;
    event.preventDefault(); event.stopImmediatePropagation();
    // Dismiss the original account menu through its normal keyboard handler.
    event.target.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));
    open(opener);
  },true);
  const rename = () => {
    document.querySelectorAll('[role="menuitem"]').forEach(item => {
      if (!/^(检查更新|Check for updates|Check Update|预览更新)$/i.test(item.textContent.trim())) return;
      const walker = document.createTreeWalker(item,NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        if (/^(检查更新|Check for updates|Check Update|预览更新)$/i.test(walker.currentNode.textContent.trim())) {
          if(walker.currentNode.textContent !== '检查更新') walker.currentNode.textContent = '检查更新'; break;
        }
      }
    });
  };
  const updateOwnVersion = () => {
    if (!runningVersion) return;
    document.querySelectorAll('[role="menuitem"]').forEach(item => {
      if (!/版本|Version/i.test(item.textContent)) return;
      const walker=document.createTreeWalker(item,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()) {
        const node=walker.currentNode;
        if (/v?\d+\.\d+\.\d+/.test(node.textContent)) {
          // Upstream may render the v prefix in a separate text node.
          const next=node.textContent.replace(/\d+\.\d+\.\d+/, runningVersion);
          if(next!==node.textContent) node.textContent=next;
        }
      }
    });
  };
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || !panel || event.source !== panel.querySelector('iframe')?.contentWindow || event.data?.type !== 'subnest-update-complete') return;
    versionRequest=null;loadVersion();
  });
  loadVersion();
  new MutationObserver(() => {rename();updateOwnVersion();}).observe(document.documentElement,{childList:true,subtree:true});
  rename();
})();
