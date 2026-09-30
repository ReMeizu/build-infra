# Add variables that we wish to make available to soong here.
EXPORT_TO_SOONG := \
    KERNEL_ARCH \
    KERNEL_CROSS_COMPILE \
    KERNEL_MAKE_FLAGS \
    TARGET_KERNEL_CONFIG \
    TARGET_KERNEL_SOURCE

# Setup SOONG_CONFIG_* vars to export the vars listed above.
# Documentation here:
# https://github.com/LineageOS/android_build_soong/commit/8328367c44085b948c003116c0ed74a047237a69

SOONG_CONFIG_NAMESPACES += lineageVarsPlugin

SOONG_CONFIG_lineageVarsPlugin :=

define addVar
  SOONG_CONFIG_lineageVarsPlugin += $(1)
  SOONG_CONFIG_lineageVarsPlugin_$(1) := $$(subst ",\",$$($1))
endef

$(foreach v,$(EXPORT_TO_SOONG),$(eval $(call addVar,$(v))))

# Keep the boot-kernel policy separate from UAPI header generation.
ifeq ($(strip $(TARGET_KERNEL_SOURCE)),)
ifneq ($(strip $(TARGET_KERNEL_HEADERS_SOURCE)),)
SOONG_CONFIG_lineageVarsPlugin_TARGET_KERNEL_SOURCE := $(TARGET_KERNEL_HEADERS_SOURCE)
endif
endif
