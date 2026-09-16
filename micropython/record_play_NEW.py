# -*- coding: utf-8 -*-
"""
record_play_NEW.py — 录音 5 秒 → 休息 3 秒 → 播放
按最新驱动改写：
  - xl9535: audio_power_up(xl) / audio_power_down(xl)（AudioBoard 类已删除）
  - es7210: Record 的属性是 mclk_pwm，收尾用 stop()（彻底关 ES7210 + 释放 I2S/MCLK）
  - es8311: ES8311，播放前用 xl.output(AMP_EN, 1) 开功放
"""
import time
from machine import Pin, I2C
from xl9535 import (XL9535, I2C1_SCL, I2C1_SDA,
                    audio_power_up, audio_power_down, AMP_EN,
                    ES7210_ADDR, ES8311_ADDR)
from es7210 import Record
from es8311 import ES8311

RECORD_SEC = 5
REST_SEC = 3          # 休息 3 秒后播放
VOLUME = 100           # 播放音量 0~100
FILE = "rec_test.wav"


def play_stereo(codec, filename):
    """播放立体声 WAV：seek(44) 跳过文件头，PCM 数据透传给 ES8311 I2S(TX, STEREO)。"""
    f = open(filename, "rb")
    f.seek(44)
    buf = bytearray(8192)
    mv = memoryview(buf)
    while True:
        n = f.readinto(buf)
        if n == 0:
            break
        codec.audio_out.write(mv[:n])
    f.close()


def main():
    i2c = I2C(1, scl=Pin(I2C1_SCL), sda=Pin(I2C1_SDA), freq=400000)
    xl = XL9535(i2c)
    rec = None
    codec = None
    try:
        print("=" * 48)
        print("[1] 音频电源域上电")
        audio_power_up(xl)
        devs = i2c.scan()
        print("    I2C 设备: %s" % [hex(d) for d in devs])
        if ES7210_ADDR not in devs:
            raise OSError("未找到 ES7210(0x%02X)" % ES7210_ADDR)
        if ES8311_ADDR not in devs:
            raise OSError("未找到 ES8311(0x%02X)" % ES8311_ADDR)

        print("\n[2] 录音 %d 秒（单麦 MIC1，请说话/拍手）..." % RECORD_SEC)
        rec = Record(i2c, sck=16, ws=17, sd=18, mck=15, addr=ES7210_ADDR)
        rec.record(FILE, duration_sec=RECORD_SEC)
        print("    录音完成 -> %s" % FILE)

        print("\n[3] 停止录音（彻底关 ES7210 + 释放 I2S/MCLK）")
        rec.stop()

        print("\n[4] 休息 %d 秒..." % REST_SEC)
        time.sleep(REST_SEC)

        print("\n[5] 初始化 ES8311 并播放")
        codec = ES8311(i2c, sck=16, ws=17, sd=13, mck=15, addr=ES8311_ADDR)
        codec.set_volume(VOLUME)
        xl.output(AMP_EN, 1)          # 开功放
        print("    开始播放 (音量 %d%%)..." % VOLUME)
        play_stereo(codec, FILE)
        xl.output(AMP_EN, 0)          # 关功放
        print("    播放完成")

        print("\n结果: 录音+播放测试完成")
        print("应听到刚才录下的 %d 秒声音" % RECORD_SEC)

    except Exception as e:
        print("\n[失败] %s: %s" % (type(e).__name__, e))
    finally:
        # 清理：释放录音/播放的 I2S 与 MCLK PWM（不写 I2C，避免异常时二次失败）
        for obj, attrs in ((rec, ("audioInI2S", "mclk_pwm")),
                           (codec, ("audio_out", "mclk_pwm"))):
            if obj is None:
                continue
            for a in attrs:
                try:
                    getattr(obj, a).deinit()
                except Exception:
                    pass
        audio_power_down(xl)
        print("=" * 48)


if __name__ == "__main__":
    main()
