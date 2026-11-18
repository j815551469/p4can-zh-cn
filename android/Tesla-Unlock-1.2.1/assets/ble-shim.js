/*
 * BLE 模式注入脚本：把页面里的 /api/* 请求改走蓝牙。
 * 由 MainActivity 在返回 ble-dashboard.html 时注入到 <head> 最前面，
 * 因此会先于页面自身脚本执行。
 */
(function () {
  var pending = new Map();

  // 原生侧收到完整回包后调用：__tuBleResult(id, status, body)
  window.__tuBleResult = function (id, status, body) {
    var resolve = pending.get(id);
    if (!resolve) return;
    pending.delete(id);
    try {
      resolve(new Response(body, {
        status: status || 200,
        headers: { 'Content-Type': 'application/json' }
      }));
    } catch (e) {
      resolve(new Response(body, { status: status || 200 }));
    }
  };

  var original = window.fetch ? window.fetch.bind(window) : null;

  window.fetch = function (input, init) {
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    var match = url.match(/\/api\/[^\s"']*/);
    if (!match || !original) {
      return original ? original(input, init) : Promise.reject(new Error('fetch 不可用'));
    }
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    return new Promise(function (resolve, reject) {
      var id = -1;
      try { id = window.TuBle.request(method, match[0]); } catch (e) { return reject(e); }
      if (id < 0) return reject(new Error('蓝牙未就绪'));
      pending.set(id, resolve);
      setTimeout(function () {
        if (pending.has(id)) {
          pending.delete(id);
          resolve(new Response('{"ok":false,"error":"ble-timeout"}', { status: 504 }));
        }
      }, 15000);
    });
  };

  window.__p4BleMode = true;
})();
