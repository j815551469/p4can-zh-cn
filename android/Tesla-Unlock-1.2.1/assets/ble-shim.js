/* BLE 模式注入脚本：把页面里的 /api/* 请求改走蓝牙，并在顶部显示一条状态行。 */
(function () {
  var pending = new Map();
  var cache = new Map();
  var ATTEMPTS = 4;
  var info = { profile: '?', setup: '?', nag: '?' };

  function banner() {
    var el = document.getElementById('__ble_status');
    if (!el) {
      el = document.createElement('div');
      el.id = '__ble_status';
      el.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:2147483647;' +
        'background:rgba(17,17,17,.88);color:#fff;font:11px/1.5 system-ui;' +
        'padding:4px 8px;white-space:pre-wrap';
      document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(el); });
      if (document.body) document.body.appendChild(el);
    }
    el.textContent = '蓝牙模式 · profile=' + info.profile +
      ' setupMode=' + info.setup + ' · nag=' + info.nag;
    return el;
  }

  function errorBanner(text) {
    try {
      var el = document.getElementById('__ble_error_banner');
      if (!el) {
        el = document.createElement('div');
        el.id = '__ble_error_banner';
        el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;' +
          'background:#7f1d1d;color:#fff;font:11px/1.5 system-ui;padding:6px 8px;' +
          'max-height:30%;overflow:auto;white-space:pre-wrap';
        document.body.appendChild(el);
      }
      el.textContent = text;
    } catch (e) { }
  }

  function noteResult(path, text) {
    try {
      var data = JSON.parse(text);
      if (path.indexOf('/api/profile/status') === 0) {
        info.profile = String(data.profile === undefined ? '?' : data.profile);
        info.setup = String(!!data.setupMode);
      } else if (path.indexOf('/api/nag/config') === 0) {
        info.nag = String(!!data.enabled);
      }
      banner();
    } catch (e) { }
  }

  // 无法解析的帧：App 会把原始十六进制发过来
  window.__tuBleRaw = function (hex) {
    errorBanner('收到无法解析的帧（前 48 字节）：' + hex);
  };

  window.__tuBleResult = function (id, status, body) {
    var settle = pending.get(id);
    if (!settle) return;
    pending.delete(id);
    var text = (typeof body === 'string') ? body : '';
    if (status === 200) {
      try { JSON.parse(text); cache.set(settle.path, text); noteResult(settle.path, text); }
      catch (e) { settle.invalid = true; }
    }
    settle.done(status, text);
  };

  var original = window.fetch ? window.fetch.bind(window) : null;

  window.fetch = function (input, init) {
    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
    var match = url.match(/\/api\/[^\s"']*/);
    if (!match || !original) {
      return original ? original(input, init) : Promise.reject(new Error('fetch 不可用'));
    }
    var path = match[0];
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();

    function attempt(left) {
      return new Promise(function (resolve) {
        var id = -1;
        try { id = TuBle.request(method, path); } catch (e) { resolve(fallback(path, '桥接异常')); return; }
        if (id < 0) { resolve(fallback(path, '蓝牙未就绪')); return; }

        var timer = setTimeout(function () {
          if (!pending.has(id)) return;
          pending.delete(id);
          retryOrFallback(left, path, 'timeout', resolve);
        }, 12000);

        var entry = {
          path: path,
          invalid: false,
          done: function (status, text) {
            clearTimeout(timer);
            if (status === 200 && !entry.invalid) {
              resolve(new Response(text, { status: 200, headers: { 'Content-Type': 'application/json' } }));
              return;
            }
            if (status === 200 && entry.invalid) { retryOrFallback(left, path, 'JSON 截断', resolve); return; }
            if (status === 429 || status === 504) { retryOrFallback(left, path, status, resolve); return; }
            errorBanner('蓝牙请求被拒：' + path + '（HTTP ' + status + '）');
            resolve(new Response(text || '{"ok":false}', {
              status: status || 500, headers: { 'Content-Type': 'application/json' }
            }));
          }
        };
        pending.set(id, entry);
      });
    }

    function retryOrFallback(left, path, why, resolve) {
      if (left > 1) { setTimeout(function () { resolve(attempt(left - 1)); }, 250); return; }
      resolve(fallback(path, why));
    }

    function fallback(path, why) {
      if (cache.has(path)) {
        errorBanner('蓝牙请求失败：' + path + '（' + why + '），已沿用上次数据');
        return new Response(cache.get(path), {
          status: 200, headers: { 'Content-Type': 'application/json' }
        });
      }
      errorBanner('蓝牙请求失败：' + path + '（' + why + '）');
      return new Response('{"ok":false,"error":"ble-unavailable"}', {
        status: 504, headers: { 'Content-Type': 'application/json' }
      });
    }

    return attempt(ATTEMPTS);
  };

  window.__p4BleMode = true;
  if (document.body) banner();
  else document.addEventListener('DOMContentLoaded', banner);
})();
