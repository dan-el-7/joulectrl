/*
 * fixed_compute.c - Deterministic compute kernel for joulectrl
 *
 * Requirements:
 * - Fixed total chunk count.
 * - Fixed work per chunk.
 * - Chunks partitioned across workers.
 * - Deterministic checksum independent of worker count.
 * - No time-based stopping condition.
 * - Compiler cannot eliminate work (anti-DCE barrier).
 * - Changing worker count partitions the fixed total work; it does NOT change total computation.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>

#if defined(_WIN32) && !defined(__CYGWIN__) && !defined(__MSYS__)
#include <windows.h>
#define USE_WIN32_THREADS 1
#else
#include <pthread.h>
#define USE_PTHREADS 1
#endif

/* Default parameters */
#define DEFAULT_WORKERS 4
#define DEFAULT_CHUNKS 4096
#define DEFAULT_ITERS 100000
#define DEFAULT_SEED UINT64_C(0x517cc1b727220a95)
#define REDUCTION_SEED UINT64_C(0x243f6a8885a308d3)

typedef struct {
    uint64_t start_chunk;
    uint64_t end_chunk;
    uint64_t iters_per_chunk;
    uint64_t seed;
    uint64_t *results;
} WorkerTask;

/* High-resolution monotonic timer */
static double get_time_sec(void) {
#if defined(USE_WIN32_THREADS)
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    return (double)count.QuadPart / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

/* Worker loop: computes a fixed slice of the total chunks */
static void run_chunk_slice(WorkerTask *task) {
    const uint64_t iters = task->iters_per_chunk;
    const uint64_t base_seed = task->seed;
    uint64_t *results = task->results;

    for (uint64_t c = task->start_chunk; c < task->end_chunk; c++) {
        /* Deterministic initial state per chunk */
        uint64_t state = (c + 1) ^ base_seed;

        /* Anti-elimination loop: SplitMix64 non-linear transformation */
        for (uint64_t i = 0; i < iters; i++) {
            state ^= state >> 30;
            state *= UINT64_C(0xbf58476d1ce4e5b9);
            state ^= state >> 27;
            state *= UINT64_C(0x94d049bb133111eb);
            state ^= state >> 31;
            state += (i ^ UINT64_C(0x9e3779b97f4a7c15));

#if defined(__GNUC__) || defined(__clang__)
            /* Assembly memory/register barrier: compiler cannot eliminate or hoist this loop */
            __asm__ __volatile__("" : "+r"(state));
#endif
        }

        results[c] = state;
    }
}

#if defined(USE_WIN32_THREADS)
static DWORD WINAPI win32_thread_entry(LPVOID arg) {
    WorkerTask *task = (WorkerTask *)arg;
    run_chunk_slice(task);
    return 0;
}
#elif defined(USE_PTHREADS)
static void *pthread_entry(void *arg) {
    WorkerTask *task = (WorkerTask *)arg;
    run_chunk_slice(task);
    return NULL;
}
#endif

/* Deterministic reduction: order-dependent on chunk index 0..chunks-1 only */
static uint64_t reduce_results(const uint64_t *results, uint64_t chunks) {
    uint64_t checksum = REDUCTION_SEED;
    for (uint64_t c = 0; c < chunks; c++) {
        checksum ^= results[c];
        /* Rotate left by 31 bits */
        checksum = (checksum << 31) | (checksum >> 33);
        checksum *= UINT64_C(0xff51afd7ed558ccd);
        checksum += UINT64_C(0x9e3779b97f4a7c15);
    }
    return checksum;
}

static void print_usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s [options]\n"
            "Options:\n"
            "  -w, --workers <N>   Number of worker threads (default: %d)\n"
            "  -c, --chunks  <N>   Total number of chunks to divide (default: %d)\n"
            "  -i, --iters   <N>   Iterations per chunk (default: %d)\n"
            "  -s, --seed    <HEX> 64-bit base seed in hex (default: 0x%" PRIx64 ")\n"
            "  -q, --quiet         Quiet mode: print only the checksum hex\n"
            "  -j, --json          Output results as JSON\n"
            "  -h, --help          Show this help message\n",
            prog, DEFAULT_WORKERS, DEFAULT_CHUNKS, DEFAULT_ITERS, DEFAULT_SEED);
}

int main(int argc, char **argv) {
    uint64_t workers = DEFAULT_WORKERS;
    uint64_t chunks = DEFAULT_CHUNKS;
    uint64_t iters = DEFAULT_ITERS;
    uint64_t seed = DEFAULT_SEED;
    int quiet = 0;
    int json_mode = 0;

    for (int i = 1; i < argc; i++) {
        if ((strcmp(argv[i], "-w") == 0 || strcmp(argv[i], "--workers") == 0) && i + 1 < argc) {
            workers = strtoull(argv[++i], NULL, 10);
            if (workers == 0) workers = 1;
        } else if ((strcmp(argv[i], "-c") == 0 || strcmp(argv[i], "--chunks") == 0) && i + 1 < argc) {
            chunks = strtoull(argv[++i], NULL, 10);
            if (chunks == 0) chunks = 1;
        } else if ((strcmp(argv[i], "-i") == 0 || strcmp(argv[i], "--iters") == 0) && i + 1 < argc) {
            iters = strtoull(argv[++i], NULL, 10);
        } else if ((strcmp(argv[i], "-s") == 0 || strcmp(argv[i], "--seed") == 0) && i + 1 < argc) {
            seed = strtoull(argv[++i], NULL, 16);
        } else if (strcmp(argv[i], "-q") == 0 || strcmp(argv[i], "--quiet") == 0) {
            quiet = 1;
        } else if (strcmp(argv[i], "-j") == 0 || strcmp(argv[i], "--json") == 0) {
            json_mode = 1;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            print_usage(argv[0]);
            return 0;
        } else {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            print_usage(argv[0]);
            return 1;
        }
    }

    /* Allocate chunk output array */
    uint64_t *results = (uint64_t *)calloc(chunks, sizeof(uint64_t));
    if (!results) {
        fprintf(stderr, "Failed to allocate memory for %" PRIu64 " chunks\n", chunks);
        return 2;
    }

    WorkerTask *tasks = (WorkerTask *)calloc(workers, sizeof(WorkerTask));
    if (!tasks) {
        fprintf(stderr, "Failed to allocate memory for worker tasks\n");
        free(results);
        return 2;
    }

    /* Partition chunks statically across workers: contiguous disjoint blocks */
    for (uint64_t t = 0; t < workers; t++) {
        tasks[t].start_chunk = (t * chunks) / workers;
        tasks[t].end_chunk = ((t + 1) * chunks) / workers;
        tasks[t].iters_per_chunk = iters;
        tasks[t].seed = seed;
        tasks[t].results = results;
    }

    double t_start = get_time_sec();

    if (workers == 1) {
        /* Single worker: execute directly without thread overhead */
        run_chunk_slice(&tasks[0]);
    } else {
#if defined(USE_WIN32_THREADS)
        HANDLE *threads = (HANDLE *)malloc(workers * sizeof(HANDLE));
        for (uint64_t t = 0; t < workers; t++) {
            threads[t] = CreateThread(NULL, 0, win32_thread_entry, &tasks[t], 0, NULL);
            if (!threads[t]) {
                fprintf(stderr, "Failed to create thread %" PRIu64 "\n", t);
                return 3;
            }
        }
        WaitForMultipleObjects((DWORD)workers, threads, TRUE, INFINITE);
        for (uint64_t t = 0; t < workers; t++) {
            CloseHandle(threads[t]);
        }
        free(threads);
#elif defined(USE_PTHREADS)
        pthread_t *threads = (pthread_t *)malloc(workers * sizeof(pthread_t));
        for (uint64_t t = 0; t < workers; t++) {
            int rc = pthread_create(&threads[t], NULL, pthread_entry, &tasks[t]);
            if (rc != 0) {
                fprintf(stderr, "Failed to create pthread %" PRIu64 "\n", t);
                return 3;
            }
        }
        for (uint64_t t = 0; t < workers; t++) {
            pthread_join(threads[t], NULL);
        }
        free(threads);
#endif
    }

    double t_end = get_time_sec();
    double runtime_sec = t_end - t_start;

    /* Deterministic checksum computation over chunk results in ascending order */
    uint64_t checksum = reduce_results(results, chunks);

    double total_work_units = (double)chunks * (double)iters;
    double chunks_per_sec = runtime_sec > 0.0 ? (double)chunks / runtime_sec : 0.0;

    if (quiet) {
        printf("0x%016" PRIx64 "\n", checksum);
    } else if (json_mode) {
        printf("{\n");
        printf("  \"workload\": \"fixed_compute\",\n");
        printf("  \"workers\": %" PRIu64 ",\n", workers);
        printf("  \"chunks\": %" PRIu64 ",\n", chunks);
        printf("  \"iters_per_chunk\": %" PRIu64 ",\n", iters);
        printf("  \"total_work_units\": %.0f,\n", total_work_units);
        printf("  \"checksum\": \"0x%016" PRIx64 "\",\n", checksum);
        printf("  \"runtime_sec\": %.6f,\n", runtime_sec);
        printf("  \"chunks_per_sec\": %.2f\n", chunks_per_sec);
        printf("}\n");
    } else {
        printf("joulectrl-fixed-compute: workers=%" PRIu64 " chunks=%" PRIu64 " iters=%" PRIu64 "\n",
               workers, chunks, iters);
        printf("checksum: 0x%016" PRIx64 "\n", checksum);
        printf("runtime: %.4f s (%.1f chunks/s)\n", runtime_sec, chunks_per_sec);
    }

    free(tasks);
    free(results);
    return 0;
}
