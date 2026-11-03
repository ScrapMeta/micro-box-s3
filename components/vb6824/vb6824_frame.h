#ifndef VB6824_FRAME_H
#define VB6824_FRAME_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(VB6824_FRAME_HOST_TEST)
#define VB6824_FRAME_API __declspec(dllexport)
#else
#define VB6824_FRAME_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define VB6824_FRAME_MAX_PAYLOAD 512u
#define VB6824_FRAME_MAX_SIZE (VB6824_FRAME_MAX_PAYLOAD + 7u)

typedef struct {
    uint8_t bytes[VB6824_FRAME_MAX_SIZE];
    size_t used;
} vb6824_parser_t;

/* The complete wire frame is writable until the callback returns. Do not
 * recursively feed this parser or retain the supplied frame pointer. */
typedef void (*vb6824_frame_callback_t)(uint8_t *frame, size_t size, void *arg);

VB6824_FRAME_API void vb6824_parser_init(vb6824_parser_t *parser);
/* NULL parser/data is a no-op; a NULL callback discards validated frames. */
VB6824_FRAME_API void vb6824_parser_feed(vb6824_parser_t *parser,
                                        const uint8_t *data, size_t size,
                                        vb6824_frame_callback_t callback,
                                        void *arg);

#ifdef __cplusplus
}
#endif

#endif
