import os, gc, time
from machine import PWM, Pin, I2C, I2S

ES8311_ADDR = 0x18

# =====================================================================
# ES8311 初始化寄存器表
# =====================================================================
register_values = [
(0x00, 0x80), (0x01, 0x3F), (0x02, 0x00), (0x03, 0x10), (0x04, 0x10),
(0x05, 0x00), (0x06, 0x03), (0x07, 0x00), (0x08, 0xFF), (0x09, 0x0C),
(0x0A, 0x4C), (0x0B, 0x00), (0x0C, 0x00), (0x0D, 0x01), (0x0E, 0x02),
(0x0F, 0x00), (0x10, 0x1F), (0x11, 0x7F), (0x12, 0x00), (0x13, 0x10),
(0x14, 0x1A), (0x15, 0x40), (0x16, 0x24), (0x17, 0xBF), (0x18, 0x00),
(0x19, 0x00), (0x1A, 0x00), (0x1B, 0x0A), (0x1C, 0x6A), (0x1D, 0x00),
(0x1E, 0x00), (0x1F, 0x00), (0x20, 0x00), (0x21, 0x00), (0x22, 0x00),
(0x23, 0x00), (0x24, 0x00), (0x25, 0x00), (0x26, 0x00), (0x27, 0x00),
(0x28, 0x00), (0x29, 0x00), (0x2A, 0x00), (0x2B, 0x00), (0x2C, 0x00),
(0x2D, 0x00), (0x2E, 0x00), (0x2F, 0x00), (0x30, 0x00), (0x31, 0x00),
(0x32, 0xFF), (0x33, 0x00), (0x34, 0x00), (0x35, 0x00), (0x36, 0x00),
(0x37, 0x08), (0x38, 0x00), (0x39, 0x00), (0x3A, 0x00), (0x3B, 0x00),
(0x3C, 0x00), (0x3D, 0x00), (0x3E, 0x00), (0x3F, 0x00), (0x40, 0x00),
(0x41, 0x00), (0x42, 0x00), (0x43, 0x00), (0x44, 0x50), (0x45, 0x00),
(0x46, 0x00), (0x47, 0x00), (0x48, 0x00), (0x49, 0x00)
]


class ES8311:
    def __init__(self, i2c, sck=16, ws=17, sd=13, mck=15, addr=ES8311_ADDR):
        self.i2c = i2c
        self.addr = addr

        # ---- I2S 硬件参数 ----
        self.SCK_PIN = sck
        self.WS_PIN = ws
        self.SD_PIN = sd
        self.MCK_PIN = mck
        self.I2S_ID = 0
        self.BUFFER_LENGTH_IN_BYTES = 40000
        self.WAV_SAMPLE_SIZE_IN_BITS = 16
        self.FORMAT = I2S.STEREO
        self.SAMPLE_RATE_IN_HZ = 24000  # 与参考代码及录音端一致

        # 1) 先输出 MCLK（= 采样率 x 256 = 6.144MHz）。
        #    ES8311 的复位和内部状态机都依赖 MCLK，必须在写寄存器前让时钟稳定，
        #    否则芯片可能处于未正确初始化的状态（表现为噪声）。
        self.mclk_pwm = PWM(Pin(self.MCK_PIN), freq=self.SAMPLE_RATE_IN_HZ * 256,
                            duty_u16=32768)
        time.sleep_ms(20)

        # 2) 复位：先保持复位 + 掉电，再释放复位 + 上电（从模式 MSC=0）
        self.write(self.i2c, 0x00, 0x1F)   # 复位位=1 保持复位，CSM_ON=0 掉电
        time.sleep_ms(20)

        # 3) 写配置寄存器（跳过 0x00，复位单独处理）
        for reg, value in register_values:
            if reg == 0x00:
                continue
            self.write(self.i2c, reg, value)
            time.sleep_ms(5)

        # 4) 上电 + 释放复位 + 从模式：0x80 = CSM_ON=1, MSC=0(从), 复位位=0
        self.write(self.i2c, 0x00, 0x80)
        time.sleep_ms(30)

        # 5) 编解码器就绪后，最后再初始化 I2S 输出
        self.audio_out = I2S(
            self.I2S_ID,
            sck=Pin(self.SCK_PIN),
            ws=Pin(self.WS_PIN),
            sd=Pin(self.SD_PIN),
            mode=I2S.TX,
            bits=self.WAV_SAMPLE_SIZE_IN_BITS,
            format=self.FORMAT,
            rate=self.SAMPLE_RATE_IN_HZ,
            ibuf=self.BUFFER_LENGTH_IN_BYTES,
        )

    def write(self, i2c, reg, byte):
        try:
            if isinstance(byte, bytes):
                i2c.writeto_mem(self.addr, reg, byte)
            elif isinstance(byte, int):
                i2c.writeto_mem(self.addr, reg, byte.to_bytes(1, 'little'))
            else:
                raise TypeError("invalid byte input")
        except Exception as ex:
            print("ES8311 write 0x%02X 失败: %s" % (reg, ex))

    def read_reg(self, reg):
        self.i2c.writeto(self.addr, bytes([reg]))
        return self.i2c.readfrom(self.addr, 1)[0]

    def play(self, file):
        f = open("/{}".format(file), "rb")
        f.seek(44)
        f_samples = bytearray(40000)
        f_samples_mv = memoryview(f_samples)
        while True:
            num_read = f.readinto(f_samples_mv)
            _ = self.audio_out.write(f_samples_mv[:num_read])
            if num_read == 0:
                break
        f.close()

    def set_volume(self, volume):
        """
        0~100 映射到 DAC 音量寄存器 0x32。
        0x32 是 0.5dB/step：0x00=-95.5dB(静音)，0xBF=0dB，0xFF=+32dB(会削波)。
        这里把 0~100% 线性映射到 -95.5dB ~ 0dB（0x00 ~ 0xBF），避免 +32dB 削波。
        """
        volume = max(0, min(100, volume))
        if volume == 0:
            self.write(self.i2c, 0x32, 0x00)
            return
        frac = volume / 100.0
        v = int(0xBF * (frac ** 0.35))   # 指数曲线抬高中高音量
        v = max(0x01, min(0xBF, v))       # 上限锁 0dB，绝不削波
        self.write(self.i2c, 0x32, v)
