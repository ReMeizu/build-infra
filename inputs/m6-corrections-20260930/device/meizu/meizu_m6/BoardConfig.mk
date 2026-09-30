LOCAL_PATH := device/meizu/meizu_m6
TARGET_MEIZU_MT675X_DEVICE := meizu_m6

# Inherit from the proprietary version
-include vendor/meizu/meizu_m6/BoardConfigVendor.mk

include device/meizu/m3_meizu_m6-common/BoardConfigCommon.mk

# Build Station: MTK's Oreo libril wrapper requires MTK telephony/ril.h
# extensions before the AOSP hardware/ril include directory is searched.
TARGET_SPECIFIC_HEADER_PATH := vendor/mediatek/include $(COMMON_PATH)/include


# system.prop
TARGET_SYSTEM_PROP := $(LOCAL_PATH)/system.prop

# Radio
ADD_RADIO_FILES := true
TARGET_RELEASETOOLS_EXTENSIONS := $(LOCAL_PATH)
# Build Station: use the MTK Oreo HIDL RIL wrapper for stock MTK modem blobs.
BOARD_PROVIDES_RILD := true
BOARD_PROVIDES_LIBRIL := true

# Bluetooth
BOARD_BLUETOOTH_BDROID_BUILDCFG_INCLUDE_DIR := $(LOCAL_PATH)/bluetooth

# Build Station: target device identity override
TARGET_OTA_ASSERT_DEVICE := meizu_m6
BOARD_NAME := meizu_m6
TARGET_SYSTEM_PROP := device/meizu/meizu_m6/system.prop
# Build Station: gatekeeper HAL service is absent during M6 Oreo bring-up.
# Use gatekeeperd's software fallback instead of blocking forever on HIDL.
BOARD_USE_SOFT_GATEKEEPER := true
# Build Station: pure64 app runtime boot-unblock. Keep the inherited arm
# second-arch native build path for stock vendor daemons/HAL wrappers, but do
# not publish 32-bit app ABIs or start zygote_secondary while app_process32
# still aborts and kills zygote64.
M6_PURE_ARM64 ?= true
ifeq ($(M6_PURE_ARM64),true)
TARGET_CPU_ABI_LIST_64_BIT := $(TARGET_CPU_ABI)
TARGET_CPU_ABI_LIST_32_BIT :=
TARGET_CPU_ABI_LIST := $(TARGET_CPU_ABI_LIST_64_BIT)
TARGET_SUPPORTS_32_BIT_APPS := false
TARGET_SUPPORTS_64_BIT_APPS := true
else
TARGET_SUPPORTS_32_BIT_APPS := true
TARGET_SUPPORTS_64_BIT_APPS := true
endif
# Stock MTK audio.primary is unstable in the 64-bit HIDL service path. Keep
# the audio HAL service on the 32-bit vendor bridge while the app runtime stays
# zygote64-only.
AUDIOSERVER_MULTILIB := 32
# Build Station: pure64 camera bring-up. AOSP Oreo cameraserver is 32-bit-only
# here, so publish CameraService from the already-64-bit mediaserver instead.
TARGET_HAS_LEGACY_CAMERA_HAL1 := true
# Build Station: stock MTK camera blobs reference legacy graphics symbols, and
# stock vendor ICU must coexist with Oreo system libs that need ICU 58 symbols.
TARGET_LD_SHIM_LIBS += \
    /system/vendor/lib/libmpe.sensorlistener.so|/system/vendor/lib/libmtkshim_sensor.so \
    /system/vendor/lib/hw/hwcomposer.mt6755.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib64/hw/hwcomposer.mt6755.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/lib/libandroid_runtime.so|/system/lib/libicuuc.so \
    /system/lib/libmedia.so|/system/lib/libicuuc.so \
    /system/lib/libmedia.so|/system/lib/libicui18n.so \
    /system/lib/libsqlite.so|/system/lib/libicuuc.so \
    /system/lib/libsqlite.so|/system/lib/libicui18n.so \
    /system/vendor/lib/libicui18n.so|/system/vendor/lib/libicuuc.so \
    /system/vendor/lib/libxml2.so|/system/vendor/lib/libicuuc.so \
    /system/vendor/lib/libcam_utils.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libcam.device1.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libcam_platform.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libcam.camadapter.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/hw/camera.mt6750.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libcam.client.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libcam.camnode.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libeffecthal.base.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libjni_lomoeffect.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libvfb_render.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libMtkOmxVenc.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libmtk_mmutils.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libshowlogo.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libgui_ext.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib/libui_ext.so|/system/vendor/lib/libmtkshim_gui.so \
    /system/vendor/lib64/libcam_utils.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libcam.device1.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libcam_platform.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libcam.camadapter.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/hw/camera.mt6750.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libcam.client.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libcam.camnode.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libeffecthal.base.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libjni_lomoeffect.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libvfb_render.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libmtk_mmutils.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libgui_ext.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/vendor/lib64/libui_ext.so|/system/vendor/lib64/libmtkshim_gui.so \
    /system/lib64/libandroid_runtime.so|/system/lib64/libicuuc.so \
    /system/lib64/libmedia.so|/system/lib64/libicuuc.so \
    /system/lib64/libmedia.so|/system/lib64/libicui18n.so \
    /system/lib64/libsqlite.so|/system/lib64/libicuuc.so \
    /system/lib64/libsqlite.so|/system/lib64/libicui18n.so \
    /system/vendor/lib64/libicui18n.so|/system/vendor/lib64/libicuuc.so \
    /system/vendor/lib64/libxml2.so|/system/vendor/lib64/libicuuc.so
# Kernel — toggle between prebuilt (default) and in-tree source build.
# DEFAULT: M6_KERNEL_FROM_SOURCE=false  →  pins the #209 prebuilt (current
#   behaviour, safe for the shared out/ while any ROM build is in flight).
# OVERRIDE: M6_KERNEL_FROM_SOURCE=true mka bacon  →  builds kernel from source
#   using kernel/meizu/meizu_m6/kernel-3.18 (symlink to the off-tree kernel
#   source) with meizu_m6_defconfig + gcc-4.9, producing Image.gz-dtb in-tree.
#   FTRACE is already off in meizu_m6_defconfig; no extra fragment needed.
#   CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y is set in meizu_m6_defconfig. FACT.
#
# The #209 prebuilt (sha256 57a1334396cea1b7...c43b1cb8) is REJECTED as
# default only when M6_KERNEL_FROM_SOURCE=true; it remains the safe fallback.
# The 2026-06-10 prebuilt is REJECTED unconditionally: blacks the panel.
TARGET_NO_KERNEL := false

M6_KERNEL_FROM_SOURCE ?= false

ifeq ($(M6_KERNEL_FROM_SOURCE),true)
# --- In-tree source build ---
# Kernel source: kernel/meizu/meizu_m6/kernel-3.18 (symlink into LOS tree)
# Matches off-tree recipe: ARCH=arm64, gcc-4.9, meizu_m6_defconfig, Image.gz-dtb
TARGET_KERNEL_SOURCE := kernel/meizu/meizu_m6/kernel-3.18
TARGET_KERNEL_CONFIG := meizu_m6_defconfig
TARGET_KERNEL_ARCH := arm64
ifeq ($(strip $(M6_KERNEL_CROSS_COMPILE_PREFIX)),)
$(error Set M6_KERNEL_CROSS_COMPILE_PREFIX to the absolute AArch64 GCC 4.9 prefix for M6_KERNEL_FROM_SOURCE=true)
endif
ifeq ($(filter /%,$(strip $(M6_KERNEL_CROSS_COMPILE_PREFIX))),)
$(error M6_KERNEL_CROSS_COMPILE_PREFIX must be an absolute AArch64 GCC 4.9 prefix)
endif
TARGET_KERNEL_CROSS_COMPILE_PREFIX := $(strip $(M6_KERNEL_CROSS_COMPILE_PREFIX))
BOARD_KERNEL_IMAGE_NAME := Image.gz-dtb
# Clear prebuilt vars so kernel.mk takes the FULL_KERNEL_BUILD path
TARGET_PREBUILT_KERNEL :=
M6_DISPLAY_KERNEL_PREBUILT :=
else
# --- Prebuilt kernel (default, current behaviour) ---
# Build Station: source-kernel artifact, rebuilt 2026-08-03 from
# kernel-meizu_M6-N-ex6/kernel-3.18 out-rot0 (sha256 daf1d3f7...): current source
# + FTRACE off + camera diagnostics + TPS65132 bias (GPIO24/27) + the RE'd stock
# ILI9881C panel driver.
# ROTATION, corrected 2026-08-03: the old note here claimed
# CONFIG_MTK_LCM_PHYSICAL_ROTATION_HW=y "fixes upside-down logo+UI". On THIS unit
# it CAUSED it. _HW is a real hardware 180 flip in the display path (ddp_ovl.c:603
# rotate + inverted layer offset + VIRTICAL_FLIP|HORI_FLIP, primary_display.c:5165,
# mtk_disp_mgr.c:1400) that compensates a 180-mounted panel; this body's panel is
# not mounted that way. Note the string CONFIG_MTK_LCM_PHYSICAL_ROTATION="180" vs
# "0" is NOT the lever -- color20/Makefile:63-67 defines LCM_PHYSICAL_ROTATION_180
# for either the string OR _HW=y, so with _HW=y both values are identical.
# The kernel pinned here has _HW unset and ROTATION="0"; user-confirmed upright
# 2026-08-03. The LK-phase logo stays inverted (cosmetic; stock hid it with
# boot_logo_updater, declared at m3_meizu_m6-common/rootdir/init.mt6755.rc:1133).
# Previous _HW=y kernel kept as prebuilt-kernel/Image.gz-dtb.rot_hw_backup.
TARGET_KERNEL_SOURCE := kernel/meizu/meizu_m6/kernel-3.18
TARGET_KERNEL_CONFIG :=
M6_DISPLAY_KERNEL_PREBUILT := device/meizu/meizu_m6/prebuilt-kernel/Image.gz-dtb
TARGET_PREBUILT_KERNEL := $(M6_DISPLAY_KERNEL_PREBUILT)
BOARD_KERNEL_IMAGE_NAME := kernel
PRODUCT_COPY_FILES += \
    $(M6_DISPLAY_KERNEL_PREBUILT):kernel
endif

# Keep default SurfaceFlinger vsync offsets until the selected HWC/kernel combination is validated.

# Nothing was loading the WiFi driver. frameworks/opt/net/wifi/libwifi_hal builds
# wifi_hal_common.cpp with -DWIFI_DRIVER_STATE_CTRL_PARAM only when the board
# defines it (libwifi_hal/Android.mk); without it wifi_change_driver_state() is a
# no-op, /dev/wmtWifi is never written, wlan0 never appears, and wpa_supplicant
# dies with "Could not read interface wlan0 flags: No such device" ->
# "Failed to connect to supplicant" -> ClientMode failed.
# FACT (device REDACTED_UNIT, 2026-08-03): writing 1 to /dev/wmtWifi by hand
# brings up wlan0 with driver mt-wifi immediately, so only the trigger was missing.
# m681 already carries this block (device/meizu/m681/BoardConfig.mk:75-77).
WIFI_DRIVER_STATE_CTRL_PARAM := /dev/wmtWifi
WIFI_DRIVER_STATE_ON := 1
WIFI_DRIVER_STATE_OFF := 0
WIFI_DRIVER_OPERSTATE_PATH := /sys/class/net/wlan0/operstate
WIFI_DRIVER_STATE_CTRL_RETRIES := 8
WIFI_DRIVER_STATE_CTRL_RETRY_DELAY_US := 1000000

# Pie Soong needs UAPI sources while the validated boot kernel remains prebuilt.
TARGET_KERNEL_HEADERS_SOURCE := kernel/meizu/meizu_m6/kernel-3.18
