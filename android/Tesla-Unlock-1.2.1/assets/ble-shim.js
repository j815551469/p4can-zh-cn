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

  if (!window.TuBle) {
    try {
      var warn = document.createElement('div');
      warn.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;' +
        'background:#7f1d1d;color:#fff;font:12px/1.4 system-ui;padding:8px 10px';
      warn.textContent = '蓝牙桥未注入：页面没有拿到 TuBle 接口';
      document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(warn); });
    } catch (e) { }
  }

  var original = window.fetch ? window.fetch.bind(window) : null;

  window.fetch = function (input, init) {
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    var match = url.match(/\/api\/[^\s"']*/);
    if (!match || !original) {
      return original ? original(input, init) : Promise.reject(new Error('fetch 不可用'));
    }
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var path = match[0];

    // 页面启动时会并发几十个请求；固件队列有限，被回 429/504 时重试几次，
    // 否则 profile/status 失败会让整页误判成“首次启动”。
    function attempt(left) {
      return new Promise(function (resolve, reject) {
        var id = -1;
        try { id = window.TuBle.request(method, path); } catch (e) { return reject(e); }
        if (id < 0) return reject(new Error('蓝牙未就绪'));
        pending.set(id, function (response) {
          if ((response.status === 429 || response.status === 504) && left > 1) {
            setTimeout(function () { resolve(attempt(left - 1)); }, 250);
            return;
          }
          if ((response.status === 429 || response.status === 504)) {
            showBleError(path, response.status);
            resolve(response);
            return;
          }
          // 200 也要验一下：BLE 分片万一丢片，JSON 会被截断，页面会误判成“没档案”。
          if (response.status === 200 && left > 1) {
            response.clone().text().then(function (text) {
              try { JSON.parse(text); resolve(response); }
              catch (e) {
                showBleError(path, 'JSON 截断，已重试');
                setTimeout(function () { resolve(attempt(left - 1)); }, 200);
              }
            });
            return;
          }
          resolve(response);
        });
        setTimeout(function () {
          if (pending.has(id)) {
            pending.delete(id);
            if (left > 1) {
              setTimeout(function () { resolve(attempt(left - 1)); }, 250);
            } else {
              showBleError(path, 'timeout');
              resolve(new Response('{"ok":false,"error":"ble-timeout"}', { status: 504 }));
            }
          }
        }, 12000);
      });
    }

    function showBleError(path, why) {
      try {
        var el = document.getElementById('__ble_error_banner');
        if (!el) {
          el = document.createElement('div');
          el.id = '__ble_error_banner';
          el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;' +
            'background:#7f1d1d;color:#fff;font:12px/1.4 system-ui;padding:8px 10px;' +
            'max-height:40%;overflow:auto;white-space:pre-wrap';
          document.body.appendChild(el);
        }
        el.textContent = '蓝牙请求失败：' + path + '（' + why + '）';
      } catch (e) { }
    }

    return attempt(3);
  };

  window.__p4BleMode = true;
})();
