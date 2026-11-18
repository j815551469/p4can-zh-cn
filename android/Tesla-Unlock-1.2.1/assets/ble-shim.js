/*
 * BLE 模式注入脚本：把页面里的 /api/* 请求改走蓝牙。
 * 由 MainActivity 在返回 ble-dashboard.html 时注入到 <head> 最前面，
 * 因此会先于页面自身脚本执行。
 *
 * 稳定性策略：
 *   - 429 / 504 自动重试（固件队列满时会这样回）
 *   - 200 但 JSON 被截断（分片丢失）也重试
 *   - 全部失败时沿用该 path 上一次成功的内容，避免页面把“没读到”当成
 *     “没档案 / 开关是关的”而回落到首次启动界面
 */
(function () {
  var pending = new Map();
  var cache = new Map();          // path -> 最近一次成功的响应体
  var ATTEMPTS = 4;

  function showBleError(path, why) {
    try {
      var el = document.getElementById('__ble_error_banner');
      if (!el) {
        el = document.createElement('div');
        el.id = '__ble_error_banner';
        el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;' +
          'background:#7f1d1d;color:#fff;font:12px/1.4 system-ui;padding:8px 10px;' +
          'max-height:30%;overflow:auto;white-space:pre-wrap';
        document.body.appendChild(el);
      }
      el.textContent = '蓝牙请求失败：' + path + '（' + why + '）';
    } catch (e) { }
  }

  // 原生侧收到完整回包后调用：__tuBleResult(id, status, body)
  window.__tuBleResult = function (id, status, body) {
    var settle = pending.get(id);
    if (!settle) return;
    pending.delete(id);
    var text = (typeof body === 'string') ? body : '';
    if (status === 200) {
      try { JSON.parse(text); cache.set(settle.path, text); }
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
        try { id = TuBle.request(method, path); } catch (e) {
          resolve(fallback(path, '桥接异常'));
          return;
        }
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
            if (status === 200 && entry.invalid) {
              retryOrFallback(left, path, 'JSON 截断', resolve);
              return;
            }
            if (status === 429 || status === 504) {
              retryOrFallback(left, path, status, resolve);
              return;
            }
            // 403 之类是策略拒绝，不重试
            showBleError(path, status);
            resolve(new Response(text || '{"ok":false}', {
              status: status || 500, headers: { 'Content-Type': 'application/json' }
            }));
          }
        };
        pending.set(id, entry);
      });
    }

    function retryOrFallback(left, path, why, resolve) {
      if (left > 1) {
        setTimeout(function () { resolve(attempt(left - 1)); }, 250);
        return;
      }
      resolve(fallback(path, why));
    }

    // 全失败：有缓存就用缓存（页面继续显示上次的真实状态），否则返回错误。
    function fallback(path, why) {
      if (cache.has(path)) {
        showBleError(path, why + '，沿用上次数据');
        return new Response(cache.get(path), {
          status: 200, headers: { 'Content-Type': 'application/json' }
        });
      }
      showBleError(path, why);
      return new Response('{"ok":false,"error":"ble-unavailable"}', {
        status: 504, headers: { 'Content-Type': 'application/json' }
      });
    }

    return attempt(ATTEMPTS);
  };

  window.__p4BleMode = true;
})();
