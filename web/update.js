/* Keep upstream routes and component code intact. Only replace the updater entry. */
(() => {
  if (location.pathname.startsWith('/__preview/')) return;
  let panel;
  const open = () => {
    if (panel) return;
    panel = document.createElement('dialog');
    panel.setAttribute('aria-label', '检查更新');
    panel.style.cssText = 'margin:auto;padding:0;border:1px solid var(--border,#888);border-radius:12px;width:min(560px,94vw);height:min(760px,90dvh);background:var(--background,#fff);color:var(--foreground,#111);';
    const close = document.createElement('button');
    close.textContent = '关闭'; close.setAttribute('aria-label','关闭预览更新');
    close.style.cssText = 'position:absolute;right:16px;top:12px;z-index:2;cursor:pointer;background:var(--background,#fff);color:var(--foreground,#111);padding:6px 12px;border:1px solid var(--border,#aaa);border-radius:6px;';
    const frame = document.createElement('iframe');
    frame.title = '版本更新'; frame.src = '/__preview/update';
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
        if (/^(检查更新|Check for updates|Check Update)$/i.test(walker.currentNode.textContent.trim())) {
          walker.currentNode.textContent = '检查更新'; break;
        }
      }
    });
  };
  const updateOwnVersion = async () => { try { const state = await fetch('/__preview/version',{cache:'no-store'}).then(r=>r.json()); document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); document.querySelectorAll('[role=menuitem], [role=menu]').forEach(menu => { if (!menu.textContent.includes('版本')) return; const walker=document.createTreeWalker(menu,NodeFilter.SHOW_TEXT); while(walker.nextNode()){ if(/^0\.6\.0$/.test(walker.currentNode.textContent.trim())) walker.currentNode.textContent=state.running; } }); } catch {} };
  updateOwnVersion();
  new MutationObserver(rename).observe(document.documentElement,{childList:true,subtree:true});
  rename();
})();
