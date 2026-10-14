/* SPDX-License-Identifier: MIT */
#include <errno.h>
#include <fcntl.h>
#include <sound/asound.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    struct snd_ctl_elem_info info = {0};
    struct snd_ctl_elem_value value = {0};
    int fd = open("/dev/snd/controlC0", O_RDWR);
    if (fd < 0) { perror("open control"); return 1; }
    info.id.iface = SNDRV_CTL_ELEM_IFACE_MIXER;
    strcpy((char *)info.id.name, "M1S Media Volume");
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_INFO, &info) < 0) {
        perror("volume control info"); close(fd); return 1;
    }
    if (!(info.access & SNDRV_CTL_ELEM_ACCESS_USER)
        || info.type != SNDRV_CTL_ELEM_TYPE_INTEGER || info.count != 1
        || info.value.integer.min != 0 || info.value.integer.max != 1023) {
        fputs("Unexpected M1S control; refusing to change it\n", stderr);
        close(fd); return 2;
    }
    value.id = info.id;
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_READ, &value) < 0) {
        perror("read volume"); close(fd); return 1;
    }
    if (argc == 3 && !strcmp(argv[1], "set")) {
        char *end;
        long target = strtol(argv[2], &end, 10);
        if (*end || !argv[2][0] || target < 0 || target > 1023) {
            close(fd); return 2;
        }
        long initial = value.value.integer.value[0];
        /* A short local ramp never inserts, drops or resamples PCM frames. */
        const struct timespec pause = {0, 5000000};
        int steps = target == 0 || target == initial ? 1 : 8;
        for (int step = 1; step <= steps; ++step) {
            value.value.integer.value[0] = initial + (target - initial) * step / steps;
            if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_WRITE, &value) < 0) {
                perror("write volume"); close(fd); return 1;
            }
            if (step < steps) nanosleep(&pause, NULL);
        }
    } else if (argc != 2 || strcmp(argv[1], "get")) {
        close(fd); return 2;
    }
    if (ioctl(fd, SNDRV_CTL_IOCTL_ELEM_READ, &value) < 0) {
        perror("read volume"); close(fd); return 1;
    }
    printf("M1S_GAIN=%ld\n", value.value.integer.value[0]);
    close(fd);
    return 0;
}
