package dev.t2can.unlock;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * 「蓝牙控制（不连热点）」面板：连上 P4-CAN-BLE 后直接下发命令。
 *
 * 只放固件白名单里的端点（见 ble_control.h）。设备当前状态不做猜测，
 * 需要时点「刷新状态」实际读一次。
 */
final class BleControlPanel {
    private final Activity activity;
    private final BleControlClient client;
    private Dialog dialog;
    private TextView statusTitle, statusDetail, result;
    private Button connectButton;

    private static final int COLOR_BG = 0xFFF3F3F1;
    private static final int COLOR_CARD = 0xFFFFFFFF;
    private static final int COLOR_TEXT = 0xFF171717;
    private static final int COLOR_MUTED = 0xFF6B6B6B;

    BleControlPanel(Activity activity) {
        this.activity = activity;
        this.client = new BleControlClient(activity, new BleControlClient.Listener() {
            @Override public void onState(final String state, final String detail) {
                activity.runOnUiThread(() -> {
                    if (statusTitle == null) return;
                    statusTitle.setText(state);
                    statusDetail.setText(detail);
                    if (connectButton != null) {
                        connectButton.setText(client.isConnected() ? "断开蓝牙" : "连接蓝牙");
                    }
                });
            }
            @Override public void onResult(final int id, final int code, final String body) {
                activity.runOnUiThread(() -> {
                    if (result == null) return;
                    String text = body == null ? "" : body.trim();
                    if (text.length() > 700) text = text.substring(0, 700) + "…";
                    result.setText("命令 #" + id + " · HTTP " + code + "\n" + text);
                });
            }
        });
    }

    void show() {
        if (dialog != null && dialog.isShowing()) return;
        LinearLayout page = new LinearLayout(activity);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(20), dp(18), dp(20), dp(16));
        page.setBackgroundColor(COLOR_BG);

        TextView title = new TextView(activity);
        title.setText("蓝牙控制");
        title.setTextSize(20);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setTextColor(COLOR_TEXT);
        page.addView(title);

        TextView subtitle = new TextView(activity);
        subtitle.setText("手机不连 P4-CAN 热点也能控制；先确认板子上已打开「设置 → 无线 → 蓝牙控制通道」。");
        subtitle.setTextSize(12);
        subtitle.setTextColor(COLOR_MUTED);
        subtitle.setPadding(0, dp(6), 0, dp(12));
        page.addView(subtitle);

        LinearLayout statusCard = card();
        statusTitle = new TextView(activity);
        statusTitle.setText("未连接");
        statusTitle.setTextSize(16);
        statusTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        statusTitle.setTextColor(COLOR_TEXT);
        statusCard.addView(statusTitle);

        statusDetail = new TextView(activity);
        statusDetail.setText("点下面「连接蓝牙」开始扫描 P4-CAN-BLE。");
        statusDetail.setTextSize(12);
        statusDetail.setTextColor(COLOR_MUTED);
        statusDetail.setPadding(0, dp(4), 0, 0);
        statusCard.addView(statusDetail);
        page.addView(statusCard);

        connectButton = button("连接蓝牙", true);
        connectButton.setOnClickListener(v -> {
            if (client.isConnected()) {
                client.disconnect();
            } else {
                client.scan();
            }
        });
        page.addView(connectButton, lp(0, dp(10), 0));

        addSection(page, "状态");
        Button refresh = button("刷新状态", false);
        refresh.setOnClickListener(v -> client.request("GET", "/api/features/status"));
        page.addView(refresh, lp(0, dp(8), 0));

        addSection(page, "握持提示抑制");
        addPair(page,
                "打开握持提示抑制", () -> client.request("POST", "/api/nag/update?enabled=1"),
                "关闭握持提示抑制", () -> client.request("POST", "/api/nag/update?enabled=0"));

        addSection(page, "红绿灯与停车标志控制（TLSSC）");
        addPair(page,
                "打开 TLSSC", () -> client.request("POST", "/api/summon/tlssc-enable"),
                "关闭 TLSSC", () -> client.request("POST", "/api/summon/tlssc-disable"));

        addSection(page, "自动转向灯");
        addPair(page,
                "打开自动转向灯", () -> client.request("POST", "/api/blinkA/enable"),
                "关闭自动转向灯", () -> client.request("POST", "/api/blinkA/disable"));

        addSection(page, "连续 AP");
        addPair(page,
                "打开连续 AP", () -> client.request("POST", "/api/continuous-ap/config?enabled=1"),
                "关闭连续 AP", () -> client.request("POST", "/api/continuous-ap/config?enabled=0"));

        addSection(page, "返回内容");
        ScrollView scroll = new ScrollView(activity);
        result = new TextView(activity);
        result.setText("（还没有下发命令）");
        result.setTextSize(11);
        result.setTypeface(Typeface.MONOSPACE);
        result.setTextColor(COLOR_TEXT);
        result.setBackgroundColor(COLOR_CARD);
        result.setPadding(dp(12), dp(10), dp(12), dp(10));
        scroll.addView(result);
        page.addView(scroll, lp(0, dp(140), 0));

        Button close = button("关闭", false);
        close.setOnClickListener(v -> dismiss());
        page.addView(close, lp(0, dp(10), dp(6)));

        ScrollView rootScroll = new ScrollView(activity);
        rootScroll.addView(page);
        dialog = new Dialog(activity);
        dialog.setContentView(rootScroll);
        dialog.setOnDismissListener(d -> { client.disconnect(); dialog = null; });
        dialog.show();
    }

    void dismiss() {
        if (dialog != null) dialog.dismiss();
    }

    private void addSection(LinearLayout page, String text) {
        TextView label = new TextView(activity);
        label.setText(text);
        label.setTextSize(12);
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        label.setTextColor(COLOR_MUTED);
        label.setPadding(0, dp(14), 0, dp(6));
        page.addView(label);
    }

    private void addPair(LinearLayout page, String onText, Runnable onAction, String offText, Runnable offAction) {
        LinearLayout row = new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        Button on = button(onText, false);
        on.setOnClickListener(v -> onAction.run());
        Button off = button(offText, false);
        off.setOnClickListener(v -> offAction.run());
        LinearLayout.LayoutParams left = new LinearLayout.LayoutParams(0, dp(46), 1f);
        left.rightMargin = dp(6);
        LinearLayout.LayoutParams right = new LinearLayout.LayoutParams(0, dp(46), 1f);
        right.leftMargin = dp(6);
        row.addView(on, left);
        row.addView(off, right);
        page.addView(row);
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(activity);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundColor(COLOR_CARD);
        card.setPadding(dp(14), dp(12), dp(14), dp(12));
        card.setLayoutParams(lp(0, 0, dp(12)));
        return card;
    }

    private Button button(String text, boolean primary) {
        Button b = new Button(activity);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(14);
        b.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        b.setGravity(Gravity.CENTER);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setElevation(0);
        b.setStateListAnimator(null);
        b.setBackgroundTintList(null);
        b.setTextColor(primary ? Color.WHITE : COLOR_TEXT);
        b.setBackgroundColor(primary ? COLOR_TEXT : COLOR_CARD);
        return b;
    }

    private LinearLayout.LayoutParams lp(int left, int top, int bottom) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.leftMargin = left;
        p.topMargin = top;
        p.bottomMargin = bottom;
        return p;
    }

    private int dp(int n) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, n,
                activity.getResources().getDisplayMetrics()));
    }
}
