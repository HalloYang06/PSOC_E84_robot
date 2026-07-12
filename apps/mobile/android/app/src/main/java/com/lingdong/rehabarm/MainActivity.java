package com.lingdong.rehabarm;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(RehabArmSppPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
