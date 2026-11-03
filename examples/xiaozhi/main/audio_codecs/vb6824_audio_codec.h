#ifndef _VB6824_AUDIO_CODEC_H
#define _VB6824_AUDIO_CODEC_H

#include "audio_codec.h"
#include <driver/gpio.h>
#include <esp_timer.h>
#include "vb6824.h"
#include <functional>

#include "freertos/timers.h"

class VbAduioCodec : public AudioCodec {
private:
    void WakeUp(std::string command);
    virtual int Read(int16_t* dest, int samples) override;
    virtual int Read(uint8_t* dest, int samples) override;
    virtual int Write(const int16_t* data, int samples) override;
    std::function<void(std::string)> on_wake_up_;
    bool frist_volume_is_set = false;

public:
    VbAduioCodec(gpio_num_t tx, gpio_num_t rx);
    void OnWakeUp(std::function<void(std::string)> callback);
    void SetOutputVolume(int volume) override;
    virtual void Start() override;
    virtual bool InputData(std::vector<uint8_t>& opus) override;
    virtual void EnableInput(bool enable) override; 
    virtual void EnableOutput(bool enable) override; 
};

#endif