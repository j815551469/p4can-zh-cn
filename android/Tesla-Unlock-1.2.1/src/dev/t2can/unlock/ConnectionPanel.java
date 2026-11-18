package dev.t2can.unlock;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import android.text.InputType;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import android.widget.Toast;
import java.util.List;
import java.util.UUID;

/** Native controls only; dashboard documents and credentials never cross a JS bridge. */
final class ConnectionPanel {
    interface Actions {
        void connect(boolean automatic);
        void disconnect();
        void profileChanged();
        String diagnostics();
    }
    private final Activity activity;
    private final ProfileRepository profiles;
    private final Actions actions;
    ConnectionPanel(Activity activity, ProfileRepository profiles, Actions actions) {
        this.activity=activity; this.profiles=profiles; this.actions=actions;
    }
    void show() {
        new AlertDialog.Builder(activity).setTitle("T2CAN 连接")
            .setItems(new String[]{"连接", "设备", "手动连接", "断开连接", "复制诊断信息", "Wi-Fi 设置", "应用权限"}, (d,which) -> {
                switch(which) {
                    case 0: actions.connect(true); break;
                    case 1: devices(); break;
                    case 2: manual(); break;
                    case 3: actions.disconnect(); break;
                    case 4:
                        ((ClipboardManager)activity.getSystemService(Activity.CLIPBOARD_SERVICE))
                            .setPrimaryClip(ClipData.newPlainText("T2CAN 诊断信息",actions.diagnostics()));
                        toast("诊断信息已复制（不含凭据）。"); break;
                    case 5: wifi(); break;
                    case 6: activity.startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:"+activity.getPackageName()))); break;
                }
            }).setNegativeButton("关闭",null).show();
    }
    void wifi() { activity.startActivity(new Intent(Settings.ACTION_WIFI_SETTINGS)); }
    void manual() {
        new AlertDialog.Builder(activity).setTitle("手动连接")
            .setMessage("请先在安卓系统设置里连上 T2CAN，然后回来点「检查连接」。此模式下其他应用仍走系统默认网络，蜂窝网络不保证可用。")
            .setPositiveButton("检查连接",(d,w)->actions.connect(false))
            .setNeutralButton("Wi-Fi 设置",(d,w)->wifi()).setNegativeButton("取消",null).show();
    }
    void devices() {
        List<DeviceProfile> list=profiles.all(); String[] labels=new String[list.size()+1];
        for(int i=0;i<list.size();i++) labels[i]=list.get(i).name+(list.get(i).id.equals(profiles.selected().id)?"（当前）":"");
        labels[list.size()]="添加设备";
        new AlertDialog.Builder(activity).setTitle("设备").setItems(labels,(d,w)->{
            if(w==list.size()) { edit(null); return; }
            DeviceProfile profile=list.get(w);
            new AlertDialog.Builder(activity).setTitle(profile.name).setItems(new String[]{"选择", "编辑", "删除"},(dialog,choice)->{
                try {
                    if(choice==0) { actions.disconnect(); profiles.select(profile.id); actions.profileChanged(); }
                    else if(choice==1) edit(profile);
                    else new AlertDialog.Builder(activity).setTitle("删除设备？")
                        .setMessage("只会删除本应用保存的连接配置。")
                        .setPositiveButton("删除",(x,y)->{
                            try { actions.disconnect(); profiles.delete(profile.id); actions.profileChanged(); }
                            catch(Exception error) { storageError(); }
                        }).setNegativeButton("取消",null).show();
                } catch(Exception error) { storageError(); }
            }).setNegativeButton("取消",null).show();
        }).setNegativeButton("关闭",null).show();
    }
    private EditText field(LinearLayout form,String label,String value,boolean password) {
        TextView title=new TextView(activity);title.setText(label);form.addView(title);
        EditText input=new EditText(activity);input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | (password ? InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS));
        input.setText(value); form.addView(input,new LinearLayout.LayoutParams(-1,-2));return input;
    }
    void edit(DeviceProfile old) {
        LinearLayout form=new LinearLayout(activity);form.setOrientation(LinearLayout.VERTICAL);
        int pad=Math.round(20*activity.getResources().getDisplayMetrics().density);form.setPadding(pad,pad,pad,pad);
        EditText name=field(form,"设备名称",old==null?"T2CAN":old.name,false);
        EditText ssid=field(form,"Wi-Fi 名称（SSID，需完全一致）",old==null?"":old.ssid,false);
        TextView securityLabel=new TextView(activity);securityLabel.setText("Wi-Fi 安全");form.addView(securityLabel);
        Spinner security=new Spinner(activity);String[] types={"OPEN","WPA2","WPA3"};
        security.setAdapter(new ArrayAdapter<String>(activity,android.R.layout.simple_spinner_dropdown_item,types));
        security.setSelection(old==null?1:java.util.Arrays.asList(types).indexOf(old.security));form.addView(security);
        EditText password=field(form,"Wi-Fi 密码",old==null?"":old.password,true);
        EditText url=field(form,"Dashboard address",old==null?UrlPolicy.HOME:old.url,false);
        TextView hint=new TextView(activity);hint.setText("请按设备实际参数填写。仅 192.168.4.1 允许 HTTP；其他私有 IPv4 地址必须用带受信证书的 HTTPS。手动模式才可以留空 SSID。");form.addView(hint);
        TextView error=new TextView(activity);form.addView(error);
        ScrollView scroll=new ScrollView(activity);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle(old==null?"添加设备":"编辑设备")
            .setView(scroll).setPositiveButton("保存",null).setNegativeButton("取消",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String home=url.getText().toString().trim(); if(!home.endsWith("/")) home+="/";
            DeviceProfile profile=new DeviceProfile(old==null?UUID.randomUUID().toString():old.id,
                name.getText().toString().trim(),ssid.getText().toString(),types[security.getSelectedItemPosition()],password.getText().toString(),home);
            String problem=profile.validationError(!profile.ssid.isEmpty());
            if(problem!=null) { error.setText(problem);return; }
            try { actions.disconnect();profiles.save(profile);profiles.select(profile.id);actions.profileChanged();dialog.dismiss(); }
            catch(Exception failed) { error.setText("无法安全保存配置，已保留原有配置。"); }
        }));dialog.show();
        // Do not offer credentials to keyboard learning or autofill services.
        password.setImportantForAutofill(android.view.View.IMPORTANT_FOR_AUTOFILL_NO);
    }
    private void toast(String s) { Toast.makeText(activity,s,Toast.LENGTH_LONG).show(); }
    private void storageError() { toast("无法更新加密的配置，原有数据已保留。"); }
}
