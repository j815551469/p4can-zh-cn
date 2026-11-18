package dev.t2can.unlock;

import java.nio.charset.StandardCharsets;

/** User-supplied AP details. No credential is derived from a device name. */
public final class DeviceProfile {
    public final String id, name, ssid, security, password, url;
    public DeviceProfile(String id, String name, String ssid, String security, String password, String url) {
        this.id = id; this.name = name; this.ssid = ssid; this.security = security;
        this.password = password; this.url = url;
    }
    public static DeviceProfile legacy() {
        return new DeviceProfile("legacy", "T2CAN", "", "OPEN", "", UrlPolicy.HOME);
    }
    public String validationError(boolean automatic) {
        if (id == null || id.isEmpty() || id.length() > 128) return "配置 ID 无效。";
        if (name == null || name.trim().isEmpty() || name.length() > 80 || controls(name))
            return "请输入设备名称（1–80 个字符）。";
        if (ssid == null || controls(ssid) || ssid.getBytes(StandardCharsets.UTF_8).length > 32
                || (automatic && ssid.isEmpty())) return "请输入完整的 Wi-Fi 名称（SSID，1–32 字节 UTF-8）。";
        if (!"OPEN".equals(security) && !"WPA2".equals(security) && !"WPA3".equals(security))
            return "请选择开放、WPA2 或 WPA3 加密方式。";
        if (password == null) return "请输入 Wi-Fi 密码。";
        if ("OPEN".equals(security)) {
            if (!password.isEmpty()) return "开放网络不能填密码。";
        } else {
            if (password.length() < 8 || password.length() > 63)
                return "Wi-Fi 密码需为 8–63 个 ASCII 字符。";
            for (int i = 0; i < password.length(); i++)
                if (password.charAt(i) < 32 || password.charAt(i) > 126)
                    return "Wi-Fi 密码需为 8–63 个 ASCII 字符。";
        }
        if (!UrlPolicy.validHome(url)) return "地址只能是 192.168.4.1 的 HTTP，或私有 IPv4 地址的 HTTPS，且不能带路径、查询或锚点。";
        return null;
    }
    private static boolean controls(String value) {
        for (int i = 0; i < value.length(); i++) if (Character.isISOControl(value.charAt(i))) return true;
        return false;
    }
}
