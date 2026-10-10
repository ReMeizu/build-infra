/* SPDX-License-Identifier: Apache-2.0 */
/* Pure parser; reads no files and changes no environment. A-only admission. */
#ifndef MEIZU_LEGACY_CMDLINE_H
#define MEIZU_LEGACY_CMDLINE_H
#include <stddef.h>
#include <string.h>

static int meizu_legacy_hardware(const char *cmdline, char *out, size_t capacity)
{
    const char key[] = "androidboot.hardware=";
    const char slot[] = "androidboot.slot_suffix=";
    unsigned found = 0;
    if (!cmdline || !out || capacity < 2) return -1;
    out[0] = '\0';
    while (*cmdline) {
        const char *begin;
        size_t length;
        while (*cmdline == ' ' || *cmdline == '\t' || *cmdline == '\n') ++cmdline;
        if (!*cmdline) break;
        begin = cmdline;
        while (*cmdline && *cmdline != ' ' && *cmdline != '\t' && *cmdline != '\n') ++cmdline;
        length = (size_t)(cmdline - begin);
        if (length >= sizeof slot - 1 && !memcmp(begin, slot, sizeof slot - 1)) return -1;
        if (length >= sizeof key - 1 && !memcmp(begin, key, sizeof key - 1)) {
            size_t value_length = length - (sizeof key - 1);
            if (++found != 1 || !value_length || value_length >= capacity) return -1;
            begin += sizeof key - 1;
            for (size_t i = 0; i < value_length; ++i) {
                unsigned char c = (unsigned char)begin[i];
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) return -1;
            }
            memcpy(out, begin, value_length);
            out[value_length] = '\0';
        }
    }
    return found == 1 ? 0 : -1;
}
#endif
