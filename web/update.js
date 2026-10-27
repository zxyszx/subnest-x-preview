/* Keep upstream routes and component code intact. Only replace the updater entry. */
(() => {
  if (location.pathname.startsWith('/__preview/')) return;
  let panel;
  let runningVersion;
  let versionRequest;
  const loadVersion = () => versionRequest ||= fetch('/__preview/version', {cache:'no-store'}).then(r => { if (!r.ok) throw Error('version'); return r.json(); }).then(state => { runningVersion=state.running; updateOwnVersion(); }).catch(() => { versionRequest=null; });
  const open = () => {
    if (panel) return;
    panel = document.createElement('dialog');
    panel.setAttribute('aria-label', '检查更新');
    panel.setAttribute('data-slot','dialog-content');
    panel.style.cssText = 'position:fixed;inset:0;margin:auto;padding:0;display:block;max-width:calc(100vw - 2rem);width:448px;height:min(660px,90dvh);max-height:90dvh;transform:none;background:var(--popover,#fff);color:var(--foreground,#111);overflow:hidden;';
    const close = document.createElement('button');
    close.textContent = '×'; close.setAttribute('aria-label','关闭检查更新');
    close.style.cssText = 'position:absolute;right:16px;top:16px;z-index:2;cursor:pointer;background:transparent;color:var(--foreground,#111);padding:0;width:24px;height:24px;border:0;font-size:24px;line-height:1;color:var(--muted-foreground,currentColor);';
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
      for(const name of rootStyle) if(name.startsWith('--')) doc.documentElement.style.setProperty(name,rootStyle.getPropertyValue(name));
      doc.documentElement.style.fontFamily=getComputedStyle(document.body).fontFamily;
      const fit=()=>{if(!panel)return;const style=getComputedStyle(panel);const border=parseFloat(style.borderTopWidth)+parseFloat(style.borderBottomWidth);panel.style.height=Math.min(doc.body.getBoundingClientRect().height+border+2,window.innerHeight*.9)+'px';};
      const sizing=new ResizeObserver(fit);sizing.observe(doc.body);panel.addEventListener('close',()=>sizing.disconnect(),{once:true});fit();
    });
    frame.style.cssText = 'width:100%;height:100%;border:0;';
    close.onclick = () => panel.close();
    panel.addEventListener('close', () => { panel.remove(); panel = null; });
    panel.append(close,frame); document.body.append(panel); panel.showModal();
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
    event.preventDefault(); event.stopImmediatePropagation();
    // Dismiss the original account menu through its normal keyboard handler.
    event.target.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));
    open();
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
        if (/v?0\.6\.0/.test(node.textContent)) node.textContent=node.textContent.replace(/v?0\.6\.0/, 'v'+runningVersion);
      }
    });
  };
  loadVersion();
  new MutationObserver(() => {rename();updateOwnVersion();}).observe(document.documentElement,{childList:true,subtree:true});
  rename();
})();
