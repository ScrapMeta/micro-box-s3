idf_component_register(
    SRCS "inputs.c" "micro_box_s3_motor.c" "micro_box_s3_motor_policy.c"
    INCLUDE_DIRS "include" PRIV_INCLUDE_DIRS "."
    REQUIRES micro_box_s3 driver esp_timer esp_driver_gpio esp_driver_ledc freertos)
