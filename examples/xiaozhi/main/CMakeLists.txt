set(BOARD_TYPE "micro-box-s3")
set(SOURCES
    "main.cc"
    "application.cc"
    "background_task.cc"
    "system_info.cc"
    "settings.cc"
    "ota.cc"
    "mcp_server.cc"
    "audio_codecs/audio_codec.cc"
    "audio_codecs/vb6824_audio_codec.cc"
    "audio_processing/audio_debugger.cc"
    "audio_processing/no_audio_processor.cc"
    "audio_processing/no_wake_word.cc"
    "display/display.cc"
    "display/lcd_display.cc"
    "protocols/protocol.cc"
    "protocols/mqtt_protocol.cc"
    "protocols/websocket_protocol.cc"
    "iot/thing.cc"
    "iot/thing_manager.cc"
    "iot/things/speaker.cc"
    "iot/things/screen.cc"
    "boards/common/board.cc"
    "boards/common/wifi_board.cc"
    "boards/common/backlight.cc"
    "boards/common/esp32_camera.cc"
    "boards/common/touch_button.cc"
    "boards/micro-box-s3/micro-box-s3.cc"
)
file(GLOB LANG_SOUNDS "${CMAKE_CURRENT_SOURCE_DIR}/assets/zh-CN/*.p3")
file(GLOB COMMON_SOUNDS "${CMAKE_CURRENT_SOURCE_DIR}/assets/common/*.p3")
idf_component_register(SRCS ${SOURCES}
    INCLUDE_DIRS "." "display" "audio_codecs" "protocols" "audio_processing" "boards/common"
    EMBED_FILES ${LANG_SOUNDS} ${COMMON_SOUNDS}
    REQUIRES micro_box_s3 micro_box_s3_controls vb6824 opus_codec
             esp_lcd driver touch_element esp_timer nvs_flash app_update
             esp_wifi esp_event esp_netif esp_pm esp_psram esp_system esp_hw_support
             esp_partition esp_app_format spi_flash efuse json mbedtls lwip pthread
             78__esp-ml307 78__esp-wifi-connect 78__xiaozhi-fonts
             espressif__esp32-camera lvgl__lvgl
    WHOLE_ARCHIVE
)
# ESP-IDF's early requirement scan returns from idf_component_register().
# Check Kconfig only during the real component configuration.
if(NOT CONFIG_BOARD_TYPE_MICRO_BOX_S3 OR NOT CONFIG_LCD_GC9A01_160X160)
    message(FATAL_ERROR "Select micro-box-s3 with its fixed 160x160 displays")
endif()
if(CONFIG_VB6824_OTA_SUPPORT)
    message(FATAL_ERROR "VB6824 network upgrades are not included")
endif()
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    BOARD_TYPE="${BOARD_TYPE}" BOARD_NAME="${BOARD_TYPE}")
