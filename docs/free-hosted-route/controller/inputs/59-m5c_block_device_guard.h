/* SPDX-License-Identifier: MIT
 * BOOT-UNBLOCK: keep the legacy Android child's fstab from writing eMMC.
 * This is an accidental physical-write guard, not a hostile-root sandbox.
 */
#ifndef M5C_BLOCK_DEVICE_GUARD_H
#define M5C_BLOCK_DEVICE_GUARD_H
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

#define M5C_GUARD_ROOT "/dev/meizu-block-guard"
#define M5C_GUARD_GROUP M5C_GUARD_ROOT "/android"

static int m5c_guard_write(const char *path, const char *text)
{
    size_t length = strlen(text), done = 0;
    int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    while (done < length) {
        ssize_t n = write(fd, text + done, length - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { int saved = n < 0 ? errno : EIO; close(fd); errno = saved; return -1; }
        done += (size_t)n;
    }
    return close(fd);
}

static int m5c_guard_read_policy(void)
{
    char line[80];
    int chars = 0, loops = 0, count = 0;
    FILE *f = fopen(M5C_GUARD_GROUP "/devices.list", "re");
    if (!f) return -1;
    while (fgets(line, sizeof(line), f)) {
        ++count;
        if (!strcmp(line, "c *:* rwm\n")) ++chars;
        else if (!strcmp(line, "b 7:* rwm\n")) ++loops;
        else { fclose(f); errno = EPERM; return -1; }
    }
    if (ferror(f)) { fclose(f); errno = EIO; return -1; }
    if (fclose(f)) return -1;
    if (count != 2 || chars != 1 || loops != 1) { errno = EPERM; return -1; }
    return 0;
}

static int m5c_guard_physical_block_devices(void)
{
    struct statfs fs;
    char pid[40];
    int n;
    /* Called only after androidd created the child's private tmpfs /dev and
     * completed its pivot. Never share or edit the native parent's /dev.
     * Missing controller or parent restrictions fail child startup explicitly.
     */
    if (geteuid() != 0) { errno = EPERM; return -1; }
    if (mkdir(M5C_GUARD_ROOT, 0700) < 0) return -1;
    if (mount("none", M5C_GUARD_ROOT, "cgroup",
              MS_NOSUID | MS_NODEV | MS_NOEXEC, "devices") < 0) return -1;
    if (statfs(M5C_GUARD_ROOT, &fs) < 0) return -1;
    if ((unsigned long)fs.f_type != 0x27e0ebUL) { errno = ENODEV; return -1; }
    if (mkdir(M5C_GUARD_GROUP, 0700) < 0) return -1;
    /* Begin with deny-all so the actual devices.list can prove the complete
     * allowlist. Character nodes cover existing HALs; block major7 is Linux
     * loop only. eMMC/UFS/SD/device-mapper/raw host partitions are excluded.
     */
    if (m5c_guard_write(M5C_GUARD_GROUP "/devices.deny", "a\n") < 0 ||
        m5c_guard_write(M5C_GUARD_GROUP "/devices.allow", "c *:* rwm\n") < 0 ||
        m5c_guard_write(M5C_GUARD_GROUP "/devices.allow", "b 7:* rwm\n") < 0 ||
        m5c_guard_read_policy() < 0) return -1;
    n = snprintf(pid, sizeof(pid), "%ld\n", (long)getpid());
    if (n < 1 || (size_t)n >= sizeof(pid)) { errno = EOVERFLOW; return -1; }
    if (m5c_guard_write(M5C_GUARD_GROUP "/cgroup.procs", pid) < 0) return -1;
    /* Do not leave writable control files at the launcher's own mountpoint.
     * All future init/ueventd/HAL children inherit the real kernel restriction.
     */
    if (mount(NULL, M5C_GUARD_ROOT, NULL,
              MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, "devices") < 0)
        return -1;
    return m5c_guard_read_policy();
}
#endif
