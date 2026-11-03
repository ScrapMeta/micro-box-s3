"""Exercise the SDK-independent UART parser through a real host C library."""

import ctypes
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components" / "vb6824"
MAX_PAYLOAD = 512
MAX_FRAME = MAX_PAYLOAD + 7


class Parser(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_uint8 * MAX_FRAME), ("used", ctypes.c_size_t)]


CALLBACK = ctypes.CFUNCTYPE(
    None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_void_p
)
COMMAND_CALLBACK = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint16, ctypes.c_void_p
)


def frame(payload=b"", command=0x2080):
    raw = b"\x55\xaa" + len(payload).to_bytes(2, "big")
    raw += command.to_bytes(2, "big") + payload
    return raw + bytes([sum(raw) & 0xFF])


def msvc_environment(build):
    """Read a temporary vcvars environment without printing its contents."""
    if shutil.which("cl.exe"):
        return dict(os.environ)
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    vswhere /= "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.is_file():
        raise unittest.SkipTest("no host C compiler available")
    result = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"],
        capture_output=True, text=True, check=True,
    )
    installation = result.stdout.strip()
    if not installation:
        raise unittest.SkipTest("no host C compiler available")
    vcvars = Path(installation) / "VC/Auxiliary/Build/vcvars64.bat"
    script = build / "compiler_env.cmd"
    script.write_text(
        '@echo off\ncall "' + str(vcvars) + '" >nul\n'
        'if errorlevel 1 exit /b %errorlevel%\nset\n', encoding="utf-8"
    )
    result = subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("vcvars64.bat failed to initialize the host compiler")
    environment = dict(os.environ)
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            environment[key.upper()] = value
    return environment


def compile_library(build, sources, name):
    if os.name == "nt":
        environment = msvc_environment(build)
        compiler = shutil.which("cl.exe", path=environment.get("PATH"))
        if not compiler:
            raise RuntimeError("MSVC environment has no cl.exe")
        library = build / (name + ".dll")
        command = [compiler, "/nologo", "/LD", "/W4", "/WX", "/std:c11",
                   "/DVB6824_FRAME_HOST_TEST", "/I" + str(COMPONENT)]
        command += [str(source) for source in sources]
        command += ["/Fe:" + str(library)]
        includes = environment.get("INCLUDE", "").split(os.pathsep)
        if not any((Path(path) / "stddef.h").is_file() for path in includes):
            # Some installations have MSVC but no Windows SDK. Use installed
            # Win64 C headers and the real system CRT, never a simulated parser.
            candidates = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            candidates = candidates.glob("MATLAB/*/sys/lcc64/lcc64/include64")
            headers = next((path for path in candidates
                            if all((path / name).is_file() for name in
                                   ("stddef.h", "stdint.h", "string.h"))), None)
            if headers is None:
                raise RuntimeError("MSVC is installed but standard C headers are missing")
            definition = build / "host_crt.def"
            definition.write_text(
                "LIBRARY msvcrt.dll\nEXPORTS\nmemmove\nmemcpy\nmemset\nstrncpy\n",
                encoding="ascii",
            )
            imports = build / "host_crt.lib"
            result = subprocess.run(
                [str(Path(compiler).with_name("lib.exe")), "/nologo", "/machine:x64",
                 "/def:" + str(definition), "/out:" + str(imports)],
                cwd=build, env=environment, capture_output=True, text=True,
            )
            if result.returncode:
                raise AssertionError("host CRT import creation failed:\n" + result.stdout + result.stderr)
            command += ["/I" + str(headers), "/GS-", "/Zl", "/link",
                        "/NODEFAULTLIB", "/NOENTRY", str(imports)]
    else:
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("no host C compiler available")
        environment = dict(os.environ)
        library = build / ("lib" + name + (".dylib" if os.sys.platform == "darwin" else ".so"))
        command = [compiler, "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra",
                   "-Werror", "-DVB6824_FRAME_HOST_TEST", "-I", str(COMPONENT)]
        command += [str(source) for source in sources] + ["-o", str(library)]
    result = subprocess.run(command, cwd=build, env=environment,
                            capture_output=True, text=True)
    if result.returncode:
        raise AssertionError("host C compilation failed:\n" + result.stdout + result.stderr)
    print("Host C compiler: " + compiler, flush=True)
    return ctypes.CDLL(str(library))


@lru_cache(maxsize=1)
def load_parser():
    for name in ("vb6824_frame.c", "vb6824_frame.h"):
        if not (COMPONENT / name).is_file():
            raise AssertionError("missing bounded UART parser implementation: " + name)
    build_root = ROOT / ".build" / "host"
    build_root.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="vb6824_parser_", dir=build_root))
    library = compile_library(build, [COMPONENT / "vb6824_frame.c"], "vb6824_parser")
    library.vb6824_parser_init.argtypes = [ctypes.POINTER(Parser)]
    library.vb6824_parser_init.restype = None
    library.vb6824_parser_feed.argtypes = [
        ctypes.POINTER(Parser), ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        CALLBACK, ctypes.c_void_p,
    ]
    library.vb6824_parser_feed.restype = None
    return library


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.library = load_parser()
        self.parser = Parser()
        self.library.vb6824_parser_init(ctypes.byref(self.parser))
        self.frames = []
        self.callback = CALLBACK(
            lambda data, size, context: self.frames.append(ctypes.string_at(data, size))
        )

    def feed(self, data):
        buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        self.library.vb6824_parser_feed(
            ctypes.byref(self.parser), buffer, len(data), self.callback, None
        )
        self.assertLessEqual(self.parser.used, MAX_FRAME)

    def test_fragmented_short_frame_and_coalesced_frames(self):
        first = frame(b"opus")
        second = frame(b"pcm", 0x0180)
        self.feed(first[:1])
        self.feed(first[1:5])
        self.assertEqual(self.frames, [])
        self.feed(first[5:] + second + frame())
        self.assertEqual(self.frames, [first, second, frame()])
        self.assertEqual(self.parser.used, 0)


    def test_each_possible_split_preserves_payload_bytes(self):
        packet = frame(bytes(range(64)) + b"\x55\xaa", 0x0180)
        for split in range(len(packet) + 1):
            with self.subTest(split=split):
                self.library.vb6824_parser_init(ctypes.byref(self.parser))
                self.frames.clear()
                self.feed(packet[:split])
                self.feed(packet[split:])
                self.assertEqual(self.frames, [packet])

    def test_noise_and_overlapping_header_recover(self):
        packet = frame(b"voice")
        self.feed(b"\x00\xaa\x13" + b"\x55" * 19)
        self.assertEqual(self.frames, [])
        self.assertEqual(self.parser.used, 1)
        self.feed(packet[1:])
        self.assertEqual(self.frames, [packet])

    def test_oversized_lengths_recover_without_waiting_for_payload(self):
        packet = frame(b"next")
        for size in (513, 514, 1024, 0x7FFF, 0xFFF9, 0xFFFF):
            with self.subTest(size=size):
                self.library.vb6824_parser_init(ctypes.byref(self.parser))
                self.frames.clear()
                self.feed(b"\x55\xaa" + size.to_bytes(2, "big") + packet)
                self.assertEqual(self.frames, [packet])
                self.assertEqual(self.parser.used, 0)

    def test_bad_checksum_recovers_at_next_frame(self):
        broken = bytearray(frame(b"broken"))
        broken[-1] ^= 1
        packet = frame(b"next", 0x0180)
        self.feed(bytes(broken) + packet)
        self.assertEqual(self.frames, [packet])

    def test_bad_checksum_rescans_embedded_valid_header(self):
        inside = frame(b"inside", 0x0180)
        broken = bytearray(frame(b"x" + inside + b"y"))
        broken[-1] ^= 1
        following = frame(b"next")
        self.feed(bytes(broken) + following)
        self.assertEqual(self.frames, [inside, following])

    def test_damaged_max_length_frame_rescans_retained_suffix(self):
        packet = frame(b"retained", 0x0180)
        prefix = b"\x55\xaa\x02\x00\x20\x80" + packet
        before_checksum = prefix + b"\0" * (MAX_FRAME - 1 - len(prefix))
        broken = before_checksum + bytes([(sum(before_checksum) + 1) & 0xFF])
        self.feed(broken + packet)
        self.assertEqual(self.frames, [packet, packet])

    def test_supported_payload_boundaries_and_checksum_wrap(self):
        for size in (0, 1, 31, 32, 40, 320, 511, 512):
            with self.subTest(size=size):
                packet = frame(bytes((i * 97) & 0xFF for i in range(size)), 0xFFFF)
                self.feed(packet)
                self.assertEqual(self.frames[-1], packet)
                self.assertEqual(self.parser.used, 0)

    def test_callback_can_rewrite_complete_frame_before_consumption(self):
        seen_contexts = []

        def consume(data, size, context):
            self.frames.append(ctypes.string_at(data, size))
            seen_contexts.append(context)
            # The production consumer swaps these fields and NULs the checksum.
            data[2], data[3] = data[3], data[2]
            data[4], data[5] = data[5], data[4]
            data[size - 1] = 0

        callback = CALLBACK(consume)
        packets = [frame(b"x" * MAX_PAYLOAD, 0x0280), frame(), frame(b"tail")]
        stream = b"".join(packets)
        data = (ctypes.c_uint8 * len(stream)).from_buffer_copy(stream)
        self.library.vb6824_parser_feed(ctypes.byref(self.parser), data, len(stream),
                                         callback, ctypes.c_void_p(0x6824))
        self.assertEqual(self.frames, packets)
        self.assertEqual(seen_contexts, [0x6824] * len(packets))
        self.assertEqual(bytes(data), stream)
        self.assertEqual(self.parser.used, 0)

    def test_large_input_keeps_parser_and_input_guards_intact(self):
        class GuardedParser(ctypes.Structure):
            _fields_ = [("before", ctypes.c_uint8 * 16), ("parser", Parser),
                        ("after", ctypes.c_uint8 * 16)]

        guarded = GuardedParser()
        ctypes.memset(ctypes.byref(guarded), 0xA5, ctypes.sizeof(guarded))
        self.parser = guarded.parser
        self.library.vb6824_parser_init(ctypes.byref(self.parser))
        packet = frame(bytes(range(256)) * 2)
        stream = b"\0" * 65536 + b"\x55\xaa\xff\xff" * 1024 + packet * 8
        input_buffer = (ctypes.c_uint8 * (len(stream) + 32))()
        ctypes.memset(input_buffer, 0xA5, ctypes.sizeof(input_buffer))
        ctypes.memmove(ctypes.addressof(input_buffer) + 16, stream, len(stream))
        pointer = ctypes.cast(ctypes.addressof(input_buffer) + 16,
                              ctypes.POINTER(ctypes.c_uint8))
        self.library.vb6824_parser_feed(ctypes.byref(self.parser), pointer,
                                         len(stream), self.callback, None)
        self.assertEqual(self.frames, [packet] * 8)
        self.assertEqual(bytes(guarded.before), b"\xa5" * 16)
        self.assertEqual(bytes(guarded.after), b"\xa5" * 16)
        self.assertEqual(bytes(input_buffer[:16]), b"\xa5" * 16)
        self.assertEqual(bytes(input_buffer[-16:]), b"\xa5" * 16)
        self.assertEqual(bytes(input_buffer[16:-16]), stream)
        padding = Parser.used.offset - MAX_FRAME
        self.assertEqual(ctypes.string_at(ctypes.addressof(self.parser) + MAX_FRAME,
                                          padding), b"\xa5" * padding)
        self.assertEqual(self.parser.used, 0)

    def test_null_inputs_are_no_ops(self):
        packet = frame(b"null-safe")
        self.feed(packet[:3])
        snapshot = ctypes.string_at(ctypes.byref(self.parser), ctypes.sizeof(Parser))
        self.library.vb6824_parser_init(None)
        self.library.vb6824_parser_feed(None, None, 4096, self.callback, None)
        self.library.vb6824_parser_feed(ctypes.byref(self.parser), None,
                                         4096, self.callback, None)
        data = (ctypes.c_uint8 * 1)(0xFF)
        self.library.vb6824_parser_feed(ctypes.byref(self.parser), data,
                                         0, self.callback, None)
        self.assertEqual(ctypes.string_at(ctypes.byref(self.parser),
                                          ctypes.sizeof(Parser)), snapshot)
        self.feed(packet[3:])
        self.assertEqual(self.frames, [packet])

    def test_null_callback_discards_complete_frames(self):
        packet = frame(b"discard")
        data = (ctypes.c_uint8 * len(packet)).from_buffer_copy(packet)
        self.library.vb6824_parser_feed(ctypes.byref(self.parser), data, len(packet),
                                         CALLBACK(), None)
        self.assertEqual(self.parser.used, 0)
        self.feed(frame(b"kept"))
        self.assertEqual(self.frames, [frame(b"kept")])

    def test_reset_discards_partial_frame(self):
        packet = frame(b"abandoned")
        self.feed(packet[:5])
        self.library.vb6824_parser_init(ctypes.byref(self.parser))
        self.feed(frame(b"fresh"))
        self.assertEqual(self.frames, [frame(b"fresh")])

    def test_parser_instances_keep_independent_stream_state(self):
        first = frame(b"first")
        second = frame(b"second")
        other = Parser()
        self.library.vb6824_parser_init(ctypes.byref(other))
        self.feed(first[:5])
        data = (ctypes.c_uint8 * len(second)).from_buffer_copy(second)
        self.library.vb6824_parser_feed(ctypes.byref(other), data, len(second),
                                         self.callback, None)
        self.feed(first[5:])
        self.assertEqual(self.frames, [second, first])

    def test_deterministic_mixed_stream_with_random_chunk_boundaries(self):
        import random

        generator = random.Random(0x6824)
        packets = []
        pieces = []
        for _ in range(256):
            pieces.append(bytes(generator.choice((0, 1, 0xAA, 0xFF))
                                for _ in range(generator.randrange(32))))
            pieces.append(b"\x55\xaa\xff\xff")
            size = generator.randrange(MAX_PAYLOAD + 1)
            packet = frame(generator.randbytes(size), generator.randrange(65536))
            packets.append(packet)
            pieces.append(packet)
        stream = b"".join(pieces)
        offset = 0
        while offset < len(stream):
            size = generator.randrange(1, 1025)
            self.feed(stream[offset:offset + size])
            offset += size
        self.assertEqual(self.frames, packets)
        self.assertEqual(self.parser.used, 0)


@lru_cache(maxsize=1)
def load_driver_callback():
    """Compile the real adapter/callback bodies, not a Python reimplementation.

    Only unexercised SDK queue/log services are replaced; UART framing and the
    wakeup copy are compiled verbatim from production C on every test run.
    """
    driver = (COMPONENT / "vb6824.c").read_text(encoding="utf-8")
    callback = re.search(
        r"void __vb6824_frame_cb\(uint8_t \*data, uint16_t len\)\{.*?^\}",
        driver, re.MULTILINE | re.DOTALL,
    )
    commands = re.search(r"typedef enum\s*\{[^}]*\}vb6824_cmd_t;", driver)
    if callback is None or commands is None:
        raise AssertionError("cannot locate production frame callback/commands")
    start = driver.index("static void __frame_dispatch(")
    adapter = driver[start:driver.index("\nvoid __frame_send(", start)]
    prefix = r"""
#include "vb6824_frame.h"
#include <string.h>
#ifdef _MSC_VER
#pragma warning(disable: 4100 4200)
#else
#pragma GCC diagnostic ignored "-Wunused-parameter"
#endif
#define SWAP_16(x) ((((x) & 0xff) << 8) | (((x) >> 8) & 0xff))
#define CONFIG_VB6824_TYPE_OPUS_16K_20MS_PCM_16K 1
#define ESP_LOGI(...) ((void)0)
#define xSemaphoreTake(...) ((void)0)
#define xSemaphoreGive(...) ((void)0)
#define xRingbufferGetCurFreeSize(...) ((size_t)512)
#define xRingbufferReceive(ring, size, wait) ((void)(size), (uint8_t *)NULL)
#define vRingbufferReturnItem(...) ((void)0)
#define xRingbufferSend(...) ((void)0)
#pragma pack(push, 1)
typedef struct {
    uint16_t head;
    uint16_t len;
    uint16_t cmd;
    uint8_t data[];
} vb6824_frame_t;
#pragma pack(pop)
static struct {
    uint8_t before[16];
    char word[32];
    uint8_t after[512];
} guarded_word;
#define s_wakeup_word guarded_word.word
static uint8_t s_wait_fresh_wakeup_word;
static uint8_t s_wait_vb_hello;
static int g_input_enabled;
static void (*g_voice_command_cb)(char *, uint16_t, void *);
static void *g_voice_command_cb_arg;
static vb6824_parser_t s_frame_parser;
"""
    suffix = r"""
VB6824_FRAME_API void host_reset(void)
{
    memset(&guarded_word, 0xa5, sizeof(guarded_word));
    memset(s_wakeup_word, 0, sizeof(s_wakeup_word));
    s_wait_fresh_wakeup_word = 1;
    g_voice_command_cb = NULL;
    g_voice_command_cb_arg = NULL;
    vb6824_parser_init(&s_frame_parser);
}
VB6824_FRAME_API void host_set_command_callback(
    void (*callback)(char *, uint16_t, void *), void *arg)
{
    g_voice_command_cb = callback;
    g_voice_command_cb_arg = arg;
}
VB6824_FRAME_API void host_feed(uint8_t *data, uint16_t size)
{
    __frame_parse_data(data, size);
}
VB6824_FRAME_API uint8_t *host_storage(void)
{
    return (uint8_t *)&guarded_word;
}
VB6824_FRAME_API uint8_t host_waiting_for_wakeup(void)
{
    return s_wait_fresh_wakeup_word;
}
"""
    build_root = ROOT / ".build" / "host"
    build_root.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="vb6824_callback_", dir=build_root))
    source = build / "callback_host.c"
    source.write_text(prefix + commands.group() + "\n" + callback.group()
                      + "\n" + adapter + suffix, encoding="utf-8")
    library = compile_library(build, [COMPONENT / "vb6824_frame.c", source],
                              "vb6824_callback")
    library.host_reset.argtypes = []
    library.host_reset.restype = None
    library.host_set_command_callback.argtypes = [COMMAND_CALLBACK, ctypes.c_void_p]
    library.host_set_command_callback.restype = None
    library.host_feed.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
    library.host_feed.restype = None
    library.host_storage.argtypes = []
    library.host_storage.restype = ctypes.POINTER(ctypes.c_uint8)
    library.host_waiting_for_wakeup.argtypes = []
    library.host_waiting_for_wakeup.restype = ctypes.c_uint8
    return library


class WakeupTests(unittest.TestCase):
    def test_long_wakeup_word_is_terminated_without_overwrite(self):
        library = load_driver_callback()
        library.host_reset()
        packet = frame(b"W" * MAX_PAYLOAD, 0x0280)
        data = (ctypes.c_uint8 * len(packet)).from_buffer_copy(packet)
        library.host_feed(data, len(packet))
        storage = ctypes.string_at(library.host_storage(), 16 + 32 + 512)
        self.assertEqual(storage[16:48], b"W" * 31 + b"\0")
        self.assertEqual(storage[:16], b"\xa5" * 16)
        self.assertEqual(storage[48:], b"\xa5" * 512)
        self.assertEqual(library.host_waiting_for_wakeup(), 0)


    def test_wakeup_lengths_and_embedded_nul_preserve_guards(self):
        library = load_driver_callback()
        for payload in (b"", b"short", b"W" * 31, b"W" * 32,
                        b"W" * 33, b"W" * 511, b"W" * 512,
                        b"short\0ignored" + b"W" * 128):
            with self.subTest(size=len(payload)):
                library.host_reset()
                packet = frame(payload, 0x0280)
                data = (ctypes.c_uint8 * len(packet)).from_buffer_copy(packet)
                library.host_feed(data, len(packet))
                storage = ctypes.string_at(library.host_storage(), 16 + 32 + 512)
                expected = payload.split(b"\0", 1)[0][:31].ljust(32, b"\0")
                self.assertEqual(storage[16:48], expected)
                self.assertEqual(storage[:16], b"\xa5" * 16)
                self.assertEqual(storage[48:], b"\xa5" * 512)
                self.assertEqual(library.host_waiting_for_wakeup(), 0)
                self.assertEqual(bytes(data), packet)

    def test_invalid_wakeup_frame_does_not_change_wakeup_state(self):
        library = load_driver_callback()
        library.host_reset()
        packet = bytearray(frame(b"not-accepted", 0x0280))
        packet[-1] ^= 1
        data = (ctypes.c_uint8 * len(packet)).from_buffer_copy(packet)
        library.host_feed(data, len(packet))
        storage = ctypes.string_at(library.host_storage(), 16 + 32 + 512)
        self.assertEqual(storage[16:48], b"\0" * 32)
        self.assertEqual(storage[:16] + storage[48:], b"\xa5" * (16 + 512))
        self.assertEqual(library.host_waiting_for_wakeup(), 1)

    def test_adapter_preserves_commands_after_writable_wakeup_frames(self):
        library = load_driver_callback()
        library.host_reset()
        commands = []
        callback = COMMAND_CALLBACK(
            lambda data, size, arg: commands.append((ctypes.string_at(data, size), arg))
        )
        library.host_set_command_callback(callback, ctypes.c_void_p(0x6824))
        command = b"command\0binary\x55\xaa"
        stream = (frame(b"W" * MAX_PAYLOAD, 0x0280) + frame(command, 0x0180)
                  + frame(b"new", 0x0280) + frame(b"", 0x0180))
        for part in (stream[:1], stream[1:3], stream[3:518], stream[518:]):
            data = (ctypes.c_uint8 * len(part)).from_buffer_copy(part)
            library.host_feed(data, len(part))
            self.assertEqual(bytes(data), part)
        self.assertEqual(commands, [(command, 0x6824), (b"", 0x6824)])
        storage = ctypes.string_at(library.host_storage(), 16 + 32 + 512)
        self.assertEqual(storage[16:48], b"new" + b"\0" * 29)
        self.assertEqual(storage[:16] + storage[48:], b"\xa5" * (16 + 512))
        self.assertEqual(library.host_waiting_for_wakeup(), 0)


if __name__ == "__main__":
    unittest.main()
