/* SPDX-License-Identifier: MIT
 * Source-selected child nodes for byte-verified, readonly composite partitions.
 * Parent measures dev_t and mount identity; no assumption about loop.max_part.
 * Not a security sandbox and not runtime accepted before device evidence.
 */
#ifndef M5C_CHILD_LOOP_NODES_H
#define M5C_CHILD_LOOP_NODES_H
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>

static dev_t m5c_child_loop_dev[2];

static int m5c_csv_readonly(char *options)
{
    char *save = NULL;
    char *token = strtok_r(options, ",", &save);
    while (token) {
        if (strcmp(token, "ro") == 0) return 1;
        token = strtok_r(NULL, ",", &save);
    }
    return 0;
}

static int m5c_prepare_child_loop_nodes(void)
{
    const char *mounts[2] = {"/android", "/android/vendor"};
    for (unsigned int i = 0; i < 2; ++i) {
        char node[64], rofile[96], line[4096];
        struct stat st;
        snprintf(node, sizeof(node), "/dev/loop%u", i + 5);
        snprintf(rofile, sizeof(rofile), "/sys/class/block/loop%u/ro", i + 5);
        if (stat(node, &st) < 0) return -1;
        if (!S_ISBLK(st.st_mode) || major(st.st_rdev) != 7) { errno = ENODEV; return -1; }
        FILE *ro = fopen(rofile, "r");
        if (!ro) return -1;
        int flag = fgetc(ro), end = fgetc(ro), trailing = fgetc(ro);
        fclose(ro);
        if (flag != '1' || end != '\n' || trailing != EOF) { errno = EROFS; return -1; }
        FILE *info = fopen("/proc/self/mountinfo", "r");
        if (!info) return -1;
        unsigned int matches = 0;
        while (fgets(line, sizeof(line), info)) {
            unsigned int id, parent, maj, min;
            char root[256], target[256], options[256];
            if (!strchr(line, '\n')) { fclose(info); errno = EOVERFLOW; return -1; }
            if (sscanf(line, "%u %u %u:%u %255s %255s %255s", &id, &parent,
                       &maj, &min, root, target, options) != 7) {
                fclose(info); errno = EINVAL; return -1;
            }
            if (strcmp(target, mounts[i]) != 0) continue;
            const char *separator = strstr(line, " - ");
            if (!separator || strncmp(separator + 3, "ext4 ", 5) != 0 ||
                    maj != major(st.st_rdev) || min != minor(st.st_rdev) ||
                    !m5c_csv_readonly(options)) {
                fclose(info); errno = EINVAL; return -1;
            }
            ++matches;
        }
        int read_error = ferror(info);
        fclose(info);
        if (read_error || matches != 1) { errno = EINVAL; return -1; }
        m5c_child_loop_dev[i] = st.st_rdev;
    }
    return 0;
}

static int m5c_install_child_loop_nodes(void)
{
    const char *paths[2] = {"/dev/block/m5c-child-system", "/dev/block/m5c-child-vendor"};
    struct stat st;
    if (mkdir("/dev/block", 0755) < 0 && errno != EEXIST) return -1;
    if (lstat("/dev/block", &st) < 0 || !S_ISDIR(st.st_mode)) { errno = ENOTDIR; return -1; }
    for (unsigned int i = 0; i < 2; ++i) {
        if (major(m5c_child_loop_dev[i]) != 7) { errno = ENODEV; return -1; }
        if (mknod(paths[i], S_IFBLK | 0600, m5c_child_loop_dev[i]) < 0 && errno != EEXIST) return -1;
        if (lstat(paths[i], &st) < 0 || !S_ISBLK(st.st_mode) || st.st_rdev != m5c_child_loop_dev[i]) {
            errno = EINVAL; return -1;
        }
    }
    return 0;
}
#endif
