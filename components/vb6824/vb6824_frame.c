#include "vb6824_frame.h"

#include <string.h>

static void discard_prefix(vb6824_parser_t *parser, size_t size)
{
    parser->used -= size;
    memmove(parser->bytes, parser->bytes + size, parser->used);
}

void vb6824_parser_init(vb6824_parser_t *parser)
{
    if (parser != NULL) {
        parser->used = 0;
    }
}

void vb6824_parser_feed(vb6824_parser_t *parser, const uint8_t *data,
                        size_t size, vb6824_frame_callback_t callback, void *arg)
{
    if (parser == NULL || data == NULL) {
        return;
    }

    for (size_t i = 0; i < size; ++i) {
        /* A valid pending frame always completes within this buffer. */
        if (parser->used >= sizeof(parser->bytes)) {
            parser->used = 0;
        }
        parser->bytes[parser->used++] = data[i];

        while (parser->used != 0) {
            if (parser->bytes[0] != 0x55) {
                discard_prefix(parser, 1);
                continue;
            }
            if (parser->used < 2) {
                break;
            }
            if (parser->bytes[1] != 0xaa) {
                discard_prefix(parser, 1);
                continue;
            }
            if (parser->used < 4) {
                break;
            }

            /* Validate the wire length before computing any payload offset. */
            const size_t payload_size = ((size_t)parser->bytes[2] << 8)
                                      | parser->bytes[3];
            if (payload_size > VB6824_FRAME_MAX_PAYLOAD) {
                discard_prefix(parser, 1);
                continue;
            }
            const size_t frame_size = payload_size + 7u;
            if (parser->used < frame_size) {
                break;
            }

            uint8_t checksum = 0;
            for (size_t j = 0; j < frame_size - 1; ++j) {
                checksum = (uint8_t)(checksum + parser->bytes[j]);
            }
            if (checksum != parser->bytes[frame_size - 1]) {
                /* Keep every suffix: a valid header may be inside bad data. */
                discard_prefix(parser, 1);
                continue;
            }
            if (callback != NULL) {
                callback(parser->bytes, frame_size, arg);
            }
            /* The consumer may rewrite length/command/checksum in place. */
            discard_prefix(parser, frame_size);
        }
    }
}
