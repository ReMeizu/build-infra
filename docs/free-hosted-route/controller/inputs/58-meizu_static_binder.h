/* SPDX-License-Identifier: Apache-2.0
 * Opt-in static binder backend for kernels with per-misc-device contexts.
 * No binderfs fallback and no context manager impersonation.
 */
#ifndef MEIZU_STATIC_BINDER_H
#define MEIZU_STATIC_BINDER_H

#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

static int meizu_binder_node(const char *name, dev_t *device)
{
    char node[80], attribute[128], text[64];
    struct stat before, opened;
    int fd = -1, attr = -1, rc = -1;
    unsigned int maj, min;
    char trailing;
    struct binder_version version = {0};

    /* Names are private constants supplied below, never external input. */
    snprintf(node, sizeof node, "/dev/%s", name);
    snprintf(attribute, sizeof attribute, "/sys/class/misc/%s/dev", name);
    if (lstat(node, &before) < 0 || !S_ISCHR(before.st_mode)) {
        logmsg("static-binder: %s missing or not a canonical char device", node);
        return -1;
    }
    fd = open(node, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) goto out;
    if (fstat(fd, &opened) < 0 || !S_ISCHR(opened.st_mode) ||
        opened.st_rdev != before.st_rdev || opened.st_ino != before.st_ino ||
        opened.st_dev != before.st_dev) {
        logmsg("static-binder: %s changed while opening", node);
        goto out;
    }
    attr = open(attribute, O_RDONLY | O_CLOEXEC);
    if (attr < 0) goto out;
    ssize_t n;
    do { n = read(attr, text, sizeof text - 1); } while (n < 0 && errno == EINTR);
    if (n <= 0 || n == (ssize_t)sizeof text - 1) goto out;
    text[n] = '\0';
    if (sscanf(text, "%u:%u %c", &maj, &min, &trailing) != 2 ||
        makedev(maj, min) != opened.st_rdev) {
        logmsg("static-binder: %s does not match misc registration", node);
        goto out;
    }
    if (ioctl(fd, BINDER_VERSION, &version) < 0 ||
        version.protocol_version != BINDER_CURRENT_PROTOCOL_VERSION) {
        logmsg("static-binder: %s lacks expected binder protocol %d", node,
               BINDER_CURRENT_PROTOCOL_VERSION);
        goto out;
    }
    *device = opened.st_rdev;
    rc = 0;
out:
    if (rc < 0) logmsg("static-binder: validation failed for %s", node);
    if (attr >= 0) close(attr);
    if (fd >= 0) close(fd);
    return rc;
}

static int meizu_static_binder_prepare(void)
{
    static const char *const names[] = {
        "ohos-binder", "android-binder", "hwbinder", "vndbinder"
    };
    dev_t devices[4];
    struct stat alias;
    for (unsigned int i = 0; i < 4; ++i) {
        if (meizu_binder_node(names[i], &devices[i]) < 0) return -1;
        for (unsigned int j = 0; j < i; ++j) {
            if (devices[i] == devices[j]) {
                logmsg("static-binder: %s aliases %s; contexts must differ",
                       names[i], names[j]);
                return -1;
            }
        }
    }
    /* Bionic callers outside the child namespace also require Android's
     * framework context. OHOS IPC is separately patched to /dev/ohos-binder. */
    if (stat("/dev/binder", &alias) < 0 || !S_ISCHR(alias.st_mode) ||
        alias.st_rdev != devices[1]) {
        logmsg("static-binder: host /dev/binder must resolve to android-binder");
        return -1;
    }
    logmsg("static-binder: four registered contexts validated; OHOS and Android differ");
    return 0;
}
#endif
