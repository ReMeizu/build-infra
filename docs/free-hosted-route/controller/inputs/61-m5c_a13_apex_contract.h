/* SPDX-License-Identifier: Apache-2.0
 * Actual M5c Android13 flattened-APEX names/source paths; no fabricated metadata.
 * Producer APEX_CONTRACT.json SHA256: f60d0a1174b15e02176672f674315b1b6586bff20e48bb0d6ca110fbb767bbc3
 */
#ifndef M5C_ANDROID13_APEX_CONTRACT_H
#define M5C_ANDROID13_APEX_CONTRACT_H
struct m5c_a13_apex_path { const char *source; const char *destination; };
static const struct m5c_a13_apex_path m5c_a13_apex_paths[] = {
    { "/system/apex/com.android.adbd", "/apex/com.android.adbd" },
    { "/system/apex/com.android.adservices", "/apex/com.android.adservices" },
    { "/system/apex/com.android.appsearch", "/apex/com.android.appsearch" },
    { "/system/apex/com.android.art", "/apex/com.android.art" },
    { "/system/apex/com.android.btservices", "/apex/com.android.btservices" },
    { "/system/apex/com.android.cellbroadcast", "/apex/com.android.cellbroadcast" },
    { "/system/apex/com.android.conscrypt", "/apex/com.android.conscrypt" },
    { "/system/apex/com.android.extservices", "/apex/com.android.extservices" },
    { "/system/apex/com.android.i18n", "/apex/com.android.i18n" },
    { "/system/apex/com.android.ipsec", "/apex/com.android.ipsec" },
    { "/system/apex/com.android.media.swcodec", "/apex/com.android.media.swcodec" },
    { "/system/apex/com.android.media", "/apex/com.android.media" },
    { "/system/apex/com.android.mediaprovider", "/apex/com.android.mediaprovider" },
    { "/system/apex/com.android.neuralnetworks", "/apex/com.android.neuralnetworks" },
    { "/system/apex/com.android.ondevicepersonalization", "/apex/com.android.ondevicepersonalization" },
    { "/system/apex/com.android.os.statsd", "/apex/com.android.os.statsd" },
    { "/system/apex/com.android.permission", "/apex/com.android.permission" },
    { "/system/apex/com.android.resolv", "/apex/com.android.resolv" },
    { "/system/apex/com.android.runtime", "/apex/com.android.runtime" },
    { "/system/apex/com.android.scheduling", "/apex/com.android.scheduling" },
    { "/system/apex/com.android.sdkext", "/apex/com.android.sdkext" },
    { "/system/apex/com.android.tethering", "/apex/com.android.tethering" },
    { "/system/apex/com.android.tzdata", "/apex/com.android.tzdata" },
    { "/system/apex/com.android.uwb", "/apex/com.android.uwb" },
    { "/system/apex/com.android.vndk.current", "/apex/com.android.vndk.v33" },
    { "/system/apex/com.android.wifi", "/apex/com.android.wifi" },
};
#define M5C_A13_APEX_COUNT (sizeof(m5c_a13_apex_paths) / sizeof(m5c_a13_apex_paths[0]))
#endif
