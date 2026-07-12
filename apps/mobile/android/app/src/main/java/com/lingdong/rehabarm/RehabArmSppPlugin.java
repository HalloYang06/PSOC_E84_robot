package com.lingdong.rehabarm;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.os.Build;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(
    name = "RehabArmSpp",
    permissions = {
        @Permission(strings = { Manifest.permission.BLUETOOTH_CONNECT }, alias = "bluetoothConnect")
    }
)
public class RehabArmSppPlugin extends Plugin {
    private static final String DEFAULT_SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB";
    private static final int MAX_FRAME_BYTES = 4096;

    private final ExecutorService executor = Executors.newCachedThreadPool();
    private BluetoothSocket socket;
    private BluetoothDevice connectedDevice;
    private volatile boolean reading;

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = baseStatus();
        call.resolve(result);
    }

    @PluginMethod
    public void listBondedDevices(PluginCall call) {
        if (!canUseBluetooth(call)) return;
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        JSArray devices = new JSArray();
        try {
            Set<BluetoothDevice> bondedDevices = adapter.getBondedDevices();
            for (BluetoothDevice device : bondedDevices) {
                JSObject item = new JSObject();
                item.put("name", safeDeviceName(device));
                item.put("address", device.getAddress());
                devices.put(item);
            }
        } catch (SecurityException error) {
            call.reject("Bluetooth permission denied", "BLUETOOTH_PERMISSION_DENIED", error);
            return;
        }
        JSObject result = baseStatus();
        result.put("devices", devices);
        call.resolve(result);
    }

    @PluginMethod
    public void connect(PluginCall call) {
        if (!canUseBluetooth(call)) return;
        String address = call.getString("address", "");
        String name = call.getString("name", "");
        String uuidText = call.getString("uuid", DEFAULT_SPP_UUID);
        executor.submit(() -> {
            try {
                BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
                BluetoothDevice device = findBondedDevice(adapter, address, name);
                if (device == null) {
                    call.reject("Bound SPP device not found. Pair it in Android Bluetooth settings first.", "SPP_DEVICE_NOT_FOUND");
                    return;
                }
                closeSocket();
                adapter.cancelDiscovery();
                BluetoothSocket nextSocket = device.createRfcommSocketToServiceRecord(UUID.fromString(uuidText));
                nextSocket.connect();
                socket = nextSocket;
                connectedDevice = device;
                startReader(nextSocket);
                JSObject result = baseStatus();
                result.put("connected", true);
                result.put("deviceName", safeDeviceName(device));
                result.put("deviceAddress", device.getAddress());
                call.resolve(result);
            } catch (SecurityException error) {
                call.reject("Bluetooth permission denied", "BLUETOOTH_PERMISSION_DENIED", error);
            } catch (Exception error) {
                closeSocket();
                call.reject(error.getMessage() == null ? "SPP connect failed" : error.getMessage(), "SPP_CONNECT_FAILED", error);
            }
        });
    }

    @PluginMethod
    public void disconnect(PluginCall call) {
        closeSocket();
        JSObject result = baseStatus();
        result.put("connected", false);
        call.resolve(result);
    }

    @PluginMethod
    public void sendLegacyFrame(PluginCall call) {
        String wireText = call.getString("wireText", "");
        Boolean sendable = call.getBoolean("sendable", false);
        if (!Boolean.TRUE.equals(sendable)) {
            call.reject("Legacy frame is not marked sendable by backend", "SPP_FRAME_NOT_SENDABLE");
            return;
        }
        if (wireText == null || wireText.isEmpty() || !wireText.endsWith("\n")) {
            call.reject("Legacy frame must be newline-delimited", "SPP_FRAME_INVALID");
            return;
        }
        byte[] bytes = wireText.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_FRAME_BYTES) {
            call.reject("Legacy frame too large", "SPP_FRAME_TOO_LARGE");
            return;
        }
        executor.submit(() -> {
            try {
                BluetoothSocket current = socket;
                if (current == null || !current.isConnected()) {
                    call.reject("SPP socket is not connected", "SPP_NOT_CONNECTED");
                    return;
                }
                OutputStream output = current.getOutputStream();
                output.write(bytes);
                output.flush();
                JSObject result = baseStatus();
                result.put("sent", true);
                result.put("byteLength", bytes.length);
                result.put("controlBoundary", "android_spp_transport_only_m33_final_authority");
                call.resolve(result);
            } catch (Exception error) {
                call.reject(error.getMessage() == null ? "SPP send failed" : error.getMessage(), "SPP_SEND_FAILED", error);
            }
        });
    }

    @Override
    protected void handleOnDestroy() {
        closeSocket();
        executor.shutdownNow();
        super.handleOnDestroy();
    }

    private boolean canUseBluetooth(PluginCall call) {
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            call.reject("Bluetooth is not available on this device", "BLUETOOTH_UNAVAILABLE");
            return false;
        }
        if (!hasConnectPermission()) {
            call.reject("Bluetooth permission is required", "BLUETOOTH_PERMISSION_REQUIRED");
            return false;
        }
        if (!bluetoothEnabled(adapter)) {
            call.reject("Bluetooth is disabled", "BLUETOOTH_DISABLED");
            return false;
        }
        return true;
    }

    private JSObject baseStatus() {
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        JSObject result = new JSObject();
        result.put("available", adapter != null);
        result.put("enabled", adapter != null && bluetoothEnabled(adapter));
        result.put("connected", socket != null && socket.isConnected());
        result.put("uuid", DEFAULT_SPP_UUID);
        result.put("transport", "bluetooth_classic_spp_rfcomm");
        result.put("permission", hasConnectPermission() ? "granted" : "prompt_required");
        result.put("controlBoundary", "android_spp_transport_only_m33_final_authority");
        if (connectedDevice != null) {
            result.put("deviceName", safeDeviceName(connectedDevice));
            result.put("deviceAddress", connectedDevice.getAddress());
        }
        return result;
    }

    private BluetoothDevice findBondedDevice(BluetoothAdapter adapter, String address, String name) {
        Set<BluetoothDevice> bondedDevices = adapter.getBondedDevices();
        for (BluetoothDevice device : bondedDevices) {
            String deviceName = safeDeviceName(device);
            if (!address.isEmpty() && address.equalsIgnoreCase(device.getAddress())) return device;
            if (!name.isEmpty() && name.equalsIgnoreCase(deviceName)) return device;
        }
        return null;
    }

    private boolean hasConnectPermission() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S || getContext().checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean bluetoothEnabled(BluetoothAdapter adapter) {
        try {
            return adapter.isEnabled();
        } catch (SecurityException ignored) {
            return false;
        }
    }

    private String safeDeviceName(BluetoothDevice device) {
        try {
            String name = device.getName();
            return name == null ? "" : name;
        } catch (SecurityException ignored) {
            return "";
        }
    }

    private void startReader(BluetoothSocket activeSocket) {
        reading = true;
        executor.submit(() -> {
            byte[] buffer = new byte[1024];
            StringBuilder pending = new StringBuilder();
            try (BufferedInputStream input = new BufferedInputStream(activeSocket.getInputStream())) {
                while (reading && activeSocket.isConnected()) {
                    int count = input.read(buffer);
                    if (count < 0) break;
                    pending.append(new String(buffer, 0, count, StandardCharsets.UTF_8));
                    int newline;
                    while ((newline = pending.indexOf("\n")) >= 0) {
                        String line = pending.substring(0, newline + 1);
                        pending.delete(0, newline + 1);
                        JSObject event = baseStatus();
                        event.put("wireText", line);
                        notifyListeners("legacySppData", event);
                    }
                }
            } catch (IOException ignored) {
            } finally {
                reading = false;
                closeSocket();
                notifyListeners("legacySppDisconnected", baseStatus());
            }
        });
    }

    private synchronized void closeSocket() {
        reading = false;
        if (socket != null) {
            try {
                socket.close();
            } catch (IOException ignored) {}
        }
        socket = null;
        connectedDevice = null;
    }
}
