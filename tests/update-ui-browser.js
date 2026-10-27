// Run this function in the browser on /__preview/update against an isolated fixture.
// Network responses are replaced; this never installs or restarts a real server.
(async () => {
  const originalFetch = window.fetch, originalTimer = window.setTimeout;
  const originalNow = Date.now;
  const results = [];
  const el = id => document.getElementById(id);
  const ok = (condition, name) => { if (!condition) throw Error(name); results.push(name); };
  const json = value => new Response(JSON.stringify(value), {headers:{'Content-Type':'application/json'}});
  const old = {running:'0.2.4', installed:'0.2.4', pending:false};
  const pending = {running:'0.2.4', installed:'0.2.5', pending:true};
  const ready = {running:'0.2.5', installed:'0.2.5', pending:false};
  try {
    window.fetch = async url => url.endsWith('/version') ? json(old) : new Response('<html>proxy unavailable</html>', {status:503});
    await checkLatest();
    ok(el('message').textContent.includes('HTTP 503') && el('status-icon').hidden && el('download').hidden, 'Proxy HTML failure is explicit and never shows latest/success');

    let latestCalls = 0;
    window.fetch = async url => {if(url.endsWith('/version'))return json(pending);latestCalls++;return json({version:'0.2.5'});};
    await checkLatest();
    ok(latestCalls === 0 && !el('restart').hidden && el('inspect').disabled && el('download').hidden, 'Pending install offers restart and blocks another install');

    el('key').value = 'fixture-only';
    window.fetch = async url => url.endsWith('/version') ? json(pending) : new Response(JSON.stringify({error:'维护口令无效'}), {status:401});
    await el('restart').onclick();
    ok(el('message').textContent === '维护口令无效' && el('message').dataset.error === 'true', 'Unauthorized restart stops with the server error');

    window.setTimeout = (callback, delay, ...args) => originalTimer(callback, delay === 1500 ? 1 : delay, ...args);
    let restarting = false, polls = 0;
    window.fetch = async url => {
      if(url.endsWith('/restart')) {restarting=true;throw new TypeError('connection closed during restart');}
      return json(restarting && ++polls > 1 ? ready : pending);
    };
    await el('restart').onclick();
    ok(el('message').textContent.includes('更新成功') && el('version').textContent.includes('v0.2.5') && el('restart').hidden, 'Lost restart response recovers only after target version is confirmed');

    let clock = originalNow();
    Date.now = () => (clock += 30000);
    window.fetch = async url => url.endsWith('/restart') ? json({state:'restarting'}) : json(pending);
    await el('restart').onclick();
    ok(el('message').textContent.includes('尚未确认更新成功') && el('message').dataset.error === 'true', 'Old process surviving restart times out without false success');
    Date.now = originalNow;

    currentState = old; lock(false);
    verified(new Blob(['fixture']), {version:'0.2.5', notes:[]});
    window.fetch = async url => {if(url.endsWith('/apply'))throw new TypeError('lost response');return json(pending);};
    await el('apply').onclick();
    ok(el('message').textContent.includes('已确认文件安装完成') && !el('restart').hidden, 'Lost install response checks persisted state before offering restart');
    return {passed:results.length, results};
  } finally {
    window.fetch = originalFetch; window.setTimeout = originalTimer; Date.now = originalNow;
    el('key').value = ''; resetPackage(); await checkLatest();
  }
})
