package dev.t2can.unlock;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.WebMessage;
import android.webkit.WebMessagePort;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Bounded, serialized blob transfer; no storage permission or JavaScript interface. */
final class FileExporter {
    static final int SAVE_REQUEST = 102;
    private static final long MAX_BYTES = 128L * 1024 * 1024;
    private final Activity activity;
    private final WebMessagePort port;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private volatile boolean closed;
    private File pending;
    private OutputStream output;
    private long expected, written;
    private String name;
    private boolean choosing;

    FileExporter(Activity activity, WebMessagePort port) {
        this.activity = activity;
        this.port = port;
        port.setWebMessageCallback(new WebMessagePort.WebMessageCallback() {
            @Override public void onMessage(WebMessagePort source, WebMessage message) {
                if (closed) return;
                final String data = message.getData();
                io.execute(() -> receive(data));
            }
        });
    }

    private void receive(String data) {
        if (closed) return;
        try {
            if (data == null || data.length() > 70000) throw new Exception("文件消息无效");
            JSONObject message = new JSONObject(data);
            switch (message.getString("type")) {
                case "begin":
                    if (pending != null || choosing) throw new Exception("已有保存任务在进行");
                    expected = message.getLong("size");
                    if (expected < 0 || expected > MAX_BYTES) throw new Exception("文件超过 128 MiB 上限");
                    name = UrlPolicy.fileName(message.optString("name"));
                    pending = File.createTempFile("log-", ".part", activity.getCacheDir());
                    output = new FileOutputStream(pending);
                    written = 0;
                    reply(null);
                    break;
                case "chunk":
                    if (output == null || choosing) throw new Exception("当前没有进行中的文件传输");
                    byte[] bytes = Base64.decode(message.getString("data"), Base64.NO_WRAP);
                    if (bytes.length > 49152 || written + bytes.length > expected)
                        throw new Exception("文件长度不一致");
                    output.write(bytes);
                    written += bytes.length;
                    reply(null);
                    break;
                case "end":
                    if (output == null || written != expected) throw new Exception("文件传输未完成");
                    output.close();
                    output = null;
                    choosing = true;
                    main.post(() -> {
                        if (closed) return;
                        try {
                            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                                    .addCategory(Intent.CATEGORY_OPENABLE)
                                    .setType(name.endsWith(".csv") ? "text/csv" : "application/octet-stream")
                                    .putExtra(Intent.EXTRA_TITLE, name);
                            activity.startActivityForResult(intent, SAVE_REQUEST);
                        } catch (Exception error) {
                            io.execute(() -> { cleanup(); reply("没有可用的文件管理器"); });
                        }
                    });
                    break;
                case "abort": cleanup(); break;
                default: throw new Exception("未知的文件消息");
            }
        } catch (Exception error) {
            cleanup();
            reply(error.getMessage());
        }
    }

    void onDestination(Uri uri) {
        if (closed) return;
        io.execute(() -> {
            if (closed || !choosing || pending == null) return;
            try {
                if (uri == null) { reply("Save cancelled"); return; }
                try (FileInputStream input = new FileInputStream(pending);
                     OutputStream destination = activity.getContentResolver().openOutputStream(uri, "wt")) {
                    if (destination == null) throw new Exception("无法打开目标文件");
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = input.read(buffer)) != -1) destination.write(buffer, 0, count);
                }
                reply(null);
            } catch (Exception error) { reply("写入目标文件失败：" + error.getMessage()); }
            finally { cleanup(); }
        });
    }

    private void reply(String error) {
        try {
            JSONObject result = new JSONObject().put("ok", error == null);
            if (error != null) result.put("error", error);
            main.post(() -> { if (!closed) port.postMessage(new WebMessage(result.toString())); });
        } catch (Exception ignored) { }
    }

    private void cleanup() {
        try { if (output != null) output.close(); } catch (Exception ignored) { }
        output = null;
        if (pending != null) pending.delete();
        pending = null;
        choosing = false;
    }

    void close() {
        closed = true;
        port.close();
        io.execute(this::cleanup);
        io.shutdown();
    }
}
