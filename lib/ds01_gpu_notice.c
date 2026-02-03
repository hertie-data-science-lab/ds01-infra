/*
 * DS01 GPU Notice — LD_PRELOAD library
 *
 * Shows a helpful message when CUDA initialization fails while
 * CUDA_VISIBLE_DEVICES="" is set (host GPU access blocked by ds01).
 *
 * Strategy: Hook cuInit() (Driver API) and show notice only when it FAILS.
 * This ensures we don't fire during successful availability probes.
 *
 * Why Driver API not Runtime API:
 * - cudaMalloc (Runtime API, libcudart.so) often loaded via dlopen by frameworks
 * - cuInit (Driver API, libcuda.so.1) is system library, LD_PRELOAD works reliably
 *
 * Build:
 *   gcc -shared -fPIC -o libds01_gpu_notice.so ds01_gpu_notice.c -ldl
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef int (*cuInit_fn)(unsigned int);

static int notice_shown = 0;

static void show_gpu_notice(void) {
    if (notice_shown)
        return;

    const char *cvd = getenv("CUDA_VISIBLE_DEVICES");
    if (cvd && *cvd == '\0') {
        notice_shown = 1;
        fprintf(stderr,
            "\n"
            "\033[33m┌──────────────────────────────────────────────────────────┐\033[0m\n"
            "\033[33m│\033[0m  \033[1;33m⚠  GPU ACCESS BLOCKED\033[0m                                   \033[33m│\033[0m\n"
            "\033[33m│\033[0m                                                          \033[33m│\033[0m\n"
            "\033[33m│\033[0m  Host GPU compute is disabled on this server.             \033[33m│\033[0m\n"
            "\033[33m│\033[0m  GPU workloads must run inside containers.                \033[33m│\033[0m\n"
            "\033[33m│\033[0m                                                          \033[33m│\033[0m\n"
            "\033[33m│\033[0m  Launch a GPU container:                                  \033[33m│\033[0m\n"
            "\033[33m│\033[0m    $ \033[1mcontainer deploy <project-name>\033[0m                      \033[33m│\033[0m\n"
            "\033[33m│\033[0m                                                          \033[33m│\033[0m\n"
            "\033[33m│\033[0m  Check available GPUs:                                    \033[33m│\033[0m\n"
            "\033[33m│\033[0m    $ \033[1mdashboard gpu\033[0m                                         \033[33m│\033[0m\n"
            "\033[33m└──────────────────────────────────────────────────────────┘\033[0m\n"
            "\n");
    }
}

/* Use dlvsym to get the real dlsym — avoids recursion */
typedef void *(*dlsym_fn)(void *, const char *);

static dlsym_fn get_real_dlsym(void) {
    static dlsym_fn real = NULL;
    if (!real)
        *(void **)(&real) = dlvsym(RTLD_NEXT, "dlsym", "GLIBC_2.2.5");
    return real;
}

/* Hook cuInit — show notice only when it FAILS (not during successful probes) */
int cuInit(unsigned int flags) {
    cuInit_fn real_cuInit = (cuInit_fn)get_real_dlsym()(RTLD_NEXT, "cuInit");

    int result = 100; /* CUDA_ERROR_NO_DEVICE */
    if (real_cuInit)
        result = real_cuInit(flags);

    /* Only show notice if cuInit failed AND CUDA is blocked */
    if (result != 0)
        show_gpu_notice();

    return result;
}

/* dlsym override — return our cuInit wrapper for dlopen+dlsym pattern */
void *dlsym(void *handle, const char *symbol) {
    dlsym_fn real_dlsym = get_real_dlsym();
    if (!real_dlsym)
        return NULL;

    if (symbol && strcmp(symbol, "cuInit") == 0)
        return (void *)cuInit;

    return real_dlsym(handle, symbol);
}
