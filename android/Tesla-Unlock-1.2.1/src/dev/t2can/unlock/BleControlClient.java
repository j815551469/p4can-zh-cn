package dev.t2can.unlock;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * P4-CAN 的 BLE 控制通道客户端。
 *
 * 协议（对应固件 ble_control.h）：
 *   CMD 写入一行文本  "<id> <GET|POST> <path>"
 *   RSP 通知分片      [id_lo][id_hi][seq][flags] + 数据，flags&1 = 末片
 *   拼起来是          "<id>|<status>|<body>"
 */
public final class BleControlClient {
    public interface Listener {
        void onState(String state, String detail);
        void onResult(int id, int status, String body);
    }

    static final UUID SERVICE = UUID.fromString("50433441-0000-1000-8000-00805F9B34FB");
    static final UUID CMD = UUID.fromString("50433441-0001-1000-8000-00805F9B34FB");
    static final UUID RSP = UUID.fromString("50433441-0002-1000-8000-00805F9B34FB");
    static final UUID STA = UUID.fromString("50433441-0003-1000-8000-00805F9B34FB");
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    static final String TARGET_NAME = "P4-CAN-BLE";

    private final Context context;
    private final Listener listener;
    private final Handler main = new Handler(Looper.getMainLooper());

    private BluetoothAdapter adapter;
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic cmdChar, rspChar, staChar;
    private int mtu = 23;
    private boolean scanning, connected, ready;
    private int nextId = 1;
    private final StringBuilder pending = new StringBuilder();
    private int pendingId = -1;
    private final ArrayList<byte[]> writeQueue = new ArrayList<>();
    private boolean writing;
    private boolean bondReceiverRegistered;
    private final Runnable bondTimeout = () -> { if (connected && !ready) { subscribe(); } };

    public BleControlClient(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
        BluetoothManager manager = (BluetoothManager) this.context.getSystemService(Context.BLUETOOTH_SERVICE);
        adapter = manager == null ? null : manager.getAdapter();
    }

    /** 按 Android 版本给出需要运行时申请的权限。 */
    public static String[] requiredPermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            return new String[]{"android.permission.BLUETOOTH_SCAN", "android.permission.BLUETOOTH_CONNECT"};
        }
        return new String[]{"android.permission.ACCESS_FINE_LOCATION"};
    }

    public static boolean hasPermissions(Context context) {
        for (String p : requiredPermissions()) {
            if (context.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) return false;
        }
        return true;
    }

    public boolean isConnected() { return connected && ready; }

    public void scan() {
        if (adapter == null || !adapter.isEnabled()) {
            state("蓝牙不可用", "请先在系统设置里打开蓝牙。");
            return;
        }
        if (scanning) return;
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) { state("扫描不可用", "设备不支持 BLE 扫描。"); return; }
        List<ScanFilter> filters = new ArrayList<>();
        filters.add(new ScanFilter.Builder().setServiceUuid(new ParcelUuid(SERVICE)).build());
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build();
        scanning = true;
        state("正在扫描", "请确认板子上已打开「蓝牙控制通道」。");
        scanner.startScan(filters, settings, scanCallback);
        main.postDelayed(() -> { if (scanning) { stopScan(); state("未发现设备", "没扫到 P4-CAN-BLE：确认开关已开、距离近一些再重试。"); } }, 12000);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            String name = null;
            try { name = device.getName(); } catch (SecurityException ignored) { }
            if (name != null && !name.isEmpty() && !TARGET_NAME.equals(name)) return;
            stopScan();
            connect(device);
        }
        @Override public void onScanFailed(int errorCode) {
            scanning = false;
            state("扫描失败", "错误码 " + errorCode + "，检查蓝牙权限或系统蓝牙开关。");
        }
    };

    private void stopScan() {
        scanning = false;
        try { if (scanner != null) scanner.stopScan(scanCallback); } catch (Exception ignored) { }
    }

    private void connect(BluetoothDevice device) {
        state("正在连接", "目标：" + (safeName(device)));
        try {
            if (Build.VERSION.SDK_INT >= 23) {
                gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
            } else {
                gatt = device.connectGatt(context, false, gattCallback);
            }
        } catch (SecurityException error) {
            state("连接失败", "缺少蓝牙权限。");
        }
    }

    private static String safeName(BluetoothDevice device) {
        try { String n = device.getName(); if (n != null && !n.isEmpty()) return n; } catch (SecurityException ignored) { }
        try { return device.getAddress(); } catch (SecurityException ignored) { return "P4-CAN-BLE"; }
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt g, int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connected = true;
                state("已连接", "正在协商 MTU 与配对…");
                try { g.requestMtu(185); } catch (SecurityException ignored) { }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connected = false;
                ready = false;
                closeQuietly();
                state("已断开", "连接已关闭，可重新连接。");
            }
        }

        @Override public void onMtuChanged(BluetoothGatt g, int newMtu, int status) {
            mtu = Math.max(23, newMtu);
            try { g.discoverServices(); } catch (SecurityException ignored) { }
        }

        @Override public void onServicesDiscovered(BluetoothGatt g, int status) {
            BluetoothGattService service = g.getService(SERVICE);
            if (service == null) { state("服务缺失", "设备上没有找到控制通道服务。"); return; }
            cmdChar = service.getCharacteristic(CMD);
            rspChar = service.getCharacteristic(RSP);
            staChar = service.getCharacteristic(STA);
            if (cmdChar == null || rspChar == null) { state("特征缺失", "控制通道特征不完整。"); return; }
            boolean bonded = false;
            try {
                bonded = g.getDevice().getBondState() == BluetoothDevice.BOND_BONDED;
            } catch (SecurityException ignored) { }
            if (bonded) {
                state("已配对", "正在订阅通知…");
                subscribe();
                return;
            }
            // 固件要求加密链路：先配对，配对完成后再订阅（否则 CCCD 写入会被拒）。
            state("正在配对", "请在系统弹窗里确认配对。");
            try {
                registerBondReceiver();
                if (!g.getDevice().createBond()) {
                    // 有些机型直接返回 false，仍然等广播/超时兜底。
                }
            } catch (SecurityException error) {
                state("权限不足", "需要蓝牙连接权限才能配对。");
                return;
            }
            main.removeCallbacks(bondTimeout);
            main.postDelayed(bondTimeout, 15000);
        }

        @Override public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor descriptor, int status) {
            if (descriptor != null && CCCD.equals(descriptor.getUuid())) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    ready = true;
                    state("已就绪", "可以通过蓝牙控制（网页已可加载）。");
                } else {
                    state("订阅失败", "通知订阅被拒（状态 " + status + "），请重新连接。");
                }
            }
        }

        @Override public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int status) {
            writing = false;
            if (status != BluetoothGatt.GATT_SUCCESS) {
                synchronized (writeQueue) { writeQueue.clear(); }
                state("写入失败", "GATT 状态 " + status + (status == 5 || status == 15 ? "（未配对或链路未加密）" : ""));
                return;
            }
            flushWriteQueue();
        }

        @Override public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c) {
            byte[] data = c.getValue();
            if (data == null || data.length < 4) return;
            int id = (data[0] & 0xFF) | ((data[1] & 0xFF) << 8);
            boolean last = (data[3] & 0x01) != 0;
            if (id != pendingId) { pendingId = id; pending.setLength(0); }
            pending.append(new String(data, 4, data.length - 4, StandardCharsets.UTF_8));
            if (!last) return;
            String message = pending.toString();
            pending.setLength(0);
            pendingId = -1;
            int status = 0;
            String body = message;
            int first = message.indexOf('|');
            int second = first < 0 ? -1 : message.indexOf('|', first + 1);
            if (first > 0 && second > first) {
                try { status = Integer.parseInt(message.substring(first + 1, second).trim()); } catch (NumberFormatException ignored) { }
                body = message.substring(second + 1);
            }
            final int fStatus = status;
            final String fBody = body;
            main.post(() -> listener.onResult(id, fStatus, fBody));
        }
    };

    private void subscribe() {
        if (gatt == null || rspChar == null) return;
        main.removeCallbacks(bondTimeout);
        try {
            gatt.setCharacteristicNotification(rspChar, true);
            BluetoothGattDescriptor descriptor = rspChar.getDescriptor(CCCD);
            if (descriptor == null) { ready = true; state("已就绪", "该设备没有通知描述符，仍可下发命令。"); return; }
            descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            if (!gatt.writeDescriptor(descriptor)) {
                state("订阅失败", "通知订阅写入被拒，请重新连接。");
            }
        } catch (SecurityException error) {
            state("权限不足", "需要蓝牙连接权限才能订阅通知。");
        }
    }

    private void registerBondReceiver() {
        if (bondReceiverRegistered) return;
        IntentFilter filter = new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        context.registerReceiver(bondReceiver, filter);
        bondReceiverRegistered = true;
    }

    private void unregisterBondReceiver() {
        if (!bondReceiverRegistered) return;
        try { context.unregisterReceiver(bondReceiver); } catch (Exception ignored) { }
        bondReceiverRegistered = false;
    }

    private final BroadcastReceiver bondReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context ctx, Intent intent) {
            if (!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(intent.getAction())) return;
            int state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE);
            if (state == BluetoothDevice.BOND_BONDED) {
                state("已配对", "正在订阅通知…");
                subscribe();
            }
        }
    };

    /** 下发一条命令；id 由调用方给，用来匹配回包。 */
    public int request(String method, String path) {
        int id = nextId++;
        if (id > 60000) nextId = 1;
        String text = id + " " + method + " " + path;
        sendText(text);
        return id;
    }

    private void sendText(String text) {
        if (!isConnected() || cmdChar == null || gatt == null) {
            state("未连接", "请先连接 P4-CAN-BLE。");
            return;
        }
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        int chunk = Math.max(20, Math.min(mtu - 3, 180));
        synchronized (writeQueue) {
            for (int off = 0; off < bytes.length; off += chunk) {
                int n = Math.min(chunk, bytes.length - off);
                byte[] part = new byte[n];
                System.arraycopy(bytes, off, part, 0, n);
                writeQueue.add(part);
            }
        }
        flushWriteQueue();
    }

    private void flushWriteQueue() {
        if (writing || gatt == null || cmdChar == null) return;
        byte[] next;
        synchronized (writeQueue) {
            if (writeQueue.isEmpty()) return;
            next = writeQueue.remove(0);
        }
        writing = true;
        try {
            cmdChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
            cmdChar.setValue(next);
            if (!gatt.writeCharacteristic(cmdChar)) { writing = false; }
        } catch (SecurityException error) {
            writing = false;
            state("写入被拒", "缺少蓝牙权限或未完成配对。");
        }
    }

    public void disconnect() {
        stopScan();
        unregisterBondReceiver();
        main.removeCallbacks(bondTimeout);
        connected = false;
        ready = false;
        closeQuietly();
        state("已断开", "连接已关闭。");
    }

    private void closeQuietly() {
        synchronized (writeQueue) { writeQueue.clear(); }
        writing = false;
        if (gatt != null) {
            try { gatt.close(); } catch (Exception ignored) { }
            gatt = null;
        }
    }

    private void state(String s, String detail) {
        main.post(() -> listener.onState(s, detail));
    }
}
