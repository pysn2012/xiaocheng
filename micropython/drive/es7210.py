import os,gc,time
from machine import PWM,Pin,I2C,I2S

# ES7210寄存器地址定义
ES7210_RESET_REG00 = 0x00    # 复位控制寄存器
ES7210_CLOCK_OFF_REG01 = 0x01 # 时钟关闭控制寄存器
ES7210_MAINCLK_REG02 = 0x02  # 主时钟分频配置
ES7210_MASTER_CLK_REG03 = 0x03
ES7210_LRCK_DIVH_REG04 = 0x04
ES7210_LRCK_DIVL_REG05 = 0x05
ES7210_POWER_DOWN_REG06 = 0x06
ES7210_OSR_REG07 = 0x07
ES7210_MODE_CONFIG_REG08 = 0x08
ES7210_TIME_CONTROL0_REG09 = 0x09
ES7210_TIME_CONTROL1_REG0A = 0x0A
ES7210_SDP_INTERFACE1_REG11 = 0x11
ES7210_SDP_INTERFACE2_REG12 = 0x12
ES7210_ADC_AUTOMUTE_REG13 = 0x13
ES7210_ADC34_MUTERANGE_REG14 = 0x14
ES7210_ADC12_MUTERANGE_REG15 = 0x15
ES7210_ADC34_HPF2_REG20 = 0x20
ES7210_ADC34_HPF1_REG21 = 0x21
ES7210_ADC12_HPF1_REG22 = 0x22
ES7210_ADC12_HPF2_REG23 = 0x23
ES7210_ANALOG_REG40 = 0x40
ES7210_MIC12_BIAS_REG41 = 0x41
ES7210_MIC34_BIAS_REG42 = 0x42
ES7210_MIC1_GAIN_REG43 = 0x43
ES7210_MIC2_GAIN_REG44 = 0x44
ES7210_MIC3_GAIN_REG45 = 0x45
ES7210_MIC4_GAIN_REG46 = 0x46
ES7210_MIC1_POWER_REG47 = 0x47
ES7210_MIC2_POWER_REG48 = 0x48
ES7210_MIC3_POWER_REG49 = 0x49
ES7210_MIC4_POWER_REG4A = 0x4A
ES7210_MIC12_POWER_REG4B = 0x4B
ES7210_MIC34_POWER_REG4C = 0x4C


# ES7210输入选择，麦克风输入通道选择（二进制掩码控制）
class ES7210InputMics:
    MIC1 = 0x01
    MIC2 = 0x02
    MIC3 = 0x04
    MIC4 = 0x08

# ES7210增益值，麦克风增益等级（0~14对应0dB~37.5dB）
class ES7210GainValue:
    GAIN_0DB = 0
    GAIN_3DB = 1
    GAIN_6DB = 2
    GAIN_9DB = 3
    GAIN_12DB = 4
    GAIN_15DB = 5
    GAIN_18DB = 6
    GAIN_21DB = 7
    GAIN_24DB = 8
    GAIN_27DB = 9
    GAIN_30DB = 10
    GAIN_33DB = 11
    GAIN_34_5DB = 12
    GAIN_36DB = 13
    GAIN_37_5DB = 14

class ES7210:
    def __init__(self, i2c, address=0x41):
        """
        初始化ES7210录音编解码器
        :param i2c: I2C总线对象（需与config.h中的AUDIO_CODEC_I2C_SCL/SDA_PIN对应）
        :param address: ES7210的I2C地址（默认0x41，需与AUDIO_CODEC_ES7210_ADDR一致）
        """
        self.i2c = i2c
        self.address = address

    def write_reg(self, reg, value):
        """向ES7210寄存器写入数据（I2C通信）"""
        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    def read_reg(self, reg):
        """从ES7210寄存器读取数据（I2C通信）"""
        self.i2c.writeto(self.address, bytes([reg]))
        return self.i2c.readfrom(self.address, 1)[0]

    def init(self):
        """初始化ES7210寄存器配置（时钟、HPF、偏置电压等）"""
        self.write_reg(ES7210_RESET_REG00, 0xff)
        self.write_reg(ES7210_RESET_REG00, 0x41)
        self.write_reg(ES7210_CLOCK_OFF_REG01, 0x1f)
        self.write_reg(ES7210_TIME_CONTROL0_REG09, 0x30)  # 设置芯片状态周期
        self.write_reg(ES7210_TIME_CONTROL1_REG0A, 0x30)  # 设置上电状态周期
        self.write_reg(ES7210_ADC12_HPF2_REG23, 0x2a)     # 快速设置
        self.write_reg(ES7210_ADC12_HPF1_REG22, 0x0a)
        self.write_reg(ES7210_ADC34_HPF2_REG20, 0x0a)
        self.write_reg(ES7210_ADC34_HPF1_REG21, 0x2a)
        self.write_reg(ES7210_ANALOG_REG40, 0xC3)        # 模拟电源 + VMID（ESP-IDF 官方驱动用 0xC3：VDDA=3.3V、VMID 选 5KΩ 启动）
        self.write_reg(ES7210_MIC12_BIAS_REG41, 0x70)     # 选择2.87V
        self.write_reg(ES7210_MIC34_BIAS_REG42, 0x70)     # 选择2.87V
        self.write_reg(ES7210_OSR_REG07, 0x20)
        self.write_reg(ES7210_MAINCLK_REG02, 0xc1)       # 设置分频系数并启用DLL（除了时钟倍频器），需要设置为0xc1以清除状态
        self.write_reg(ES7210_SDP_INTERFACE1_REG11, 0x60)  # SDP接口：16bit + I2S标准格式（SP_WL[7:5]=011=16bit, SP_PROTOCOL[1:0]=00=I2S）
        # 位宽匹配：ES7210 复位默认 24bit，ESP32 I2S 配 16bit，显式配成 16bit 避免精度损失。
        
    def set_gain(self, mic, gain):
        """设置指定麦克风的增益（需选择MIC1~4通道）。bit4=0x10 是 PGA 使能，必须带上。"""
        if mic == ES7210InputMics.MIC1:
            self.write_reg(ES7210_MIC1_GAIN_REG43, 0x10 | gain)
        elif mic == ES7210InputMics.MIC2:
            self.write_reg(ES7210_MIC2_GAIN_REG44, 0x10 | gain)
        elif mic == ES7210InputMics.MIC3:
            self.write_reg(ES7210_MIC3_GAIN_REG45, 0x10 | gain)
        elif mic == ES7210InputMics.MIC4:
            self.write_reg(ES7210_MIC4_GAIN_REG46, 0x10 | gain)

    def power_down(self):
        """彻底关闭 ES7210（对齐 ESP-IDF 官方 es7210_stop）：
        关 MIC 电源 → 关时钟 → power down。否则 ES7210 半运行会干扰共享 I2C 总线，
        导致后续播放（ES8311 初始化）失败，只能硬断电恢复。"""
        self.write_reg(ES7210_MIC1_POWER_REG47, 0xFF)
        self.write_reg(ES7210_MIC2_POWER_REG48, 0xFF)
        self.write_reg(ES7210_MIC3_POWER_REG49, 0xFF)
        self.write_reg(ES7210_MIC4_POWER_REG4A, 0xFF)
        self.write_reg(ES7210_MIC12_POWER_REG4B, 0xFF)
        self.write_reg(ES7210_MIC34_POWER_REG4C, 0xFF)
        self.write_reg(ES7210_CLOCK_OFF_REG01, 0x7F)
        self.write_reg(ES7210_POWER_DOWN_REG06, 0x07)

    def power_on(self):
        # 唤醒ES7210
        self.write_reg(ES7210_POWER_DOWN_REG06, 0x00)
    
    def start(self, clock_reg_value):
        # 启动ES7210编解码器
        self.write_reg(ES7210_CLOCK_OFF_REG01, clock_reg_value)
        self.write_reg(ES7210_POWER_DOWN_REG06, 0x00)
        self.write_reg(ES7210_ANALOG_REG40, 0xC3)
        self.write_reg(ES7210_MIC1_POWER_REG47, 0x00)
        self.write_reg(ES7210_MIC2_POWER_REG48, 0x00)
        self.write_reg(ES7210_MIC3_POWER_REG49, 0x00)
        self.write_reg(ES7210_MIC4_POWER_REG4A, 0x00)
        self.mic_select(0x01)  #|0x02
    
    def update_reg_bit(self, reg, mask, value):
        # 读取寄存器值
        reg_value = self.read_reg(reg)
        # 根据mask更新寄存器值
        if value:
            reg_value |= mask
        else:
            reg_value &= ~mask
        # 写回寄存器
        self.write_reg(reg, reg_value)

    def mic_select(self, mic_select):
        # 选择麦克风
        self.mic_select = mic_select
        if mic_select & (ES7210InputMics.MIC1 | ES7210InputMics.MIC2 | ES7210InputMics.MIC3 | ES7210InputMics.MIC4):
            for i in range(4):
                self.update_reg_bit(ES7210_MIC1_GAIN_REG43 + i, 0x10, 0x00)
            self.write_reg(ES7210_MIC12_POWER_REG4B, 0xff)
            self.write_reg(ES7210_MIC34_POWER_REG4C, 0xff)
            
            if mic_select & ES7210InputMics.MIC1:
                print("Enable ES7210_INPUT_MIC1")
                self.update_reg_bit(ES7210_CLOCK_OFF_REG01, 0x0b, 0x00)
                self.write_reg(ES7210_MIC12_POWER_REG4B, 0x00)
                self.update_reg_bit(ES7210_MIC1_GAIN_REG43, 0x10, 0x10)
                self.update_reg_bit(ES7210_MIC1_GAIN_REG43, 0x0f, 0)
                
            if mic_select & ES7210InputMics.MIC2:
                print("Enable ES7210_INPUT_MIC2")
                self.update_reg_bit(ES7210_CLOCK_OFF_REG01, 0x0b, 0x00)
                self.write_reg(ES7210_MIC12_POWER_REG4B, 0x00)
                self.update_reg_bit(ES7210_MIC2_GAIN_REG44, 0x10, 0x10)
                self.update_reg_bit(ES7210_MIC2_GAIN_REG44, 0x0f, 0)
                
            if mic_select & ES7210InputMics.MIC3:
                print("Enable ES7210_INPUT_MIC3")
                self.update_reg_bit(ES7210_CLOCK_OFF_REG01, 0x15, 0x00)
                self.write_reg(ES7210_MIC34_POWER_REG4C, 0x00)
                self.update_reg_bit(ES7210_MIC3_GAIN_REG45, 0x10, 0x10)
                self.update_reg_bit(ES7210_MIC3_GAIN_REG45, 0x0f, 0)
                
            if mic_select & ES7210InputMics.MIC4:
                print("Enable ES7210_INPUT_MIC4")
                self.update_reg_bit(ES7210_CLOCK_OFF_REG01, 0x15, 0x00)
                self.write_reg(ES7210_MIC34_POWER_REG4C, 0x00)
                self.update_reg_bit(ES7210_MIC4_GAIN_REG46, 0x10, 0x10)
                self.update_reg_bit(ES7210_MIC4_GAIN_REG46, 0x0f, 0)
                
            mic_num = sum(1 for i in [ES7210InputMics.MIC1, ES7210InputMics.MIC2, ES7210InputMics.MIC3, ES7210InputMics.MIC4] if mic_select & i)
            if mic_num >= 2:  # 假设ENABLE_TDM_MAX_NUM为2
                self.write_reg(ES7210_SDP_INTERFACE2_REG12, 0x02)
                print(f"Enable TDM mode. ES7210_SDP_INTERFACE2_REG12: {self.read_reg(ES7210_SDP_INTERFACE2_REG12):X}")
            else:
                self.write_reg(ES7210_SDP_INTERFACE2_REG12, 0x00)
                print(f"Disable TDM mode. ES7210_SDP_INTERFACE2_REG12: {self.read_reg(ES7210_SDP_INTERFACE2_REG12):X}")
        else:
            print("Microphone selection error")
            raise ValueError("Microphone selection error")
    def read_all(self):
        for i in range(0x4E + 1):
            reg = self.read_reg(i)
            print("REG:%02x, VAL:%02x"%(i, reg))

class Record:
    def __init__(self,i2c,sck=16,ws=17,sd=18,mck=15,addr=0x43):
        """
        录音模块初始化（引脚与 record_wav_NEW.py 调用一致）
        :param sck: I2S BCLK (GPIO16)
        :param ws:  I2S WS   (GPIO17)
        :param sd:  I2S DIN  (GPIO18)
        :param mck: MCLK     (GPIO15)
        :param addr: ES7210 I2C 地址（默认 0x43，与 xl9535.ES7210_ADDR 一致；如与实际不符请 i2c.scan() 确认）
        """
        self.i2c = i2c
        self.sampleRate = 24000
        self.bitsPerSample = 16
        self.bufSize = 80000    # 加大 I2S DMA 缓冲（内部 RAM 有限，80KB 足够容忍写 flash 抖动），防溢出丢数据
        self.datasize = self.bufSize * 4

        # 1) 先启动 MCLK（6.144MHz = 256×fs）。
        #    ES7210 的寄存器配置（0x02=0xc1）是 256×fs 分频：fs = MCLK/256。
        #    必须用 6.144MHz；否则 ES7210 内部按 MCLK/256=48kHz 采样、ESP32 按 24kHz
        self.mclk_pwm = PWM(Pin(mck), freq=6144000, duty_u16=32768)
        time.sleep_ms(20)

        # 2) 再配置 ES7210 寄存器
        self.es7210 = ES7210(self.i2c, addr)
        self.es7210.init()
        regv = self.es7210.read_reg(ES7210_CLOCK_OFF_REG01)
        print("ES7210_CLOCK_OFF_REG01寄存器的值（停止前）：%x" % regv)
        self.es7210.start(regv)     # 含 mic_select，选择 MIC1（此时增益会被清 0）
        self.es7210.power_on()
        # 3) start() 之后再设增益（否则 mic_select 会把增益清 0，导致信号只剩噪声底）
        self.es7210.set_gain(0x01, 0x0A)   # MIC1 增益 30dB（参考代码值）
        self.es7210.set_gain(0x02, 0x0A)   # MIC2 增益 30dB

        # 4) 最后初始化 I2S RX
        self.audioInI2S = I2S(0,
           sck=Pin(sck), ws=Pin(ws), sd=Pin(sd),
           mode=I2S.RX, bits=self.bitsPerSample,
           format=I2S.STEREO, rate=self.sampleRate,
           ibuf=self.bufSize)
    #定义一个函数用于创建wav文件的头
    def createWavHeader(self, sampleRate, bitsPerSample, num_channels, datasize):
        o = bytes("RIFF", 'ascii')                                                   # (4字节) 标记文件为RIFF格式
        o += (datasize + 36).to_bytes(4, 'little')                                   # (4字节) 文件大小（不包括RIFF标记和此字段）
        o += bytes("WAVE", 'ascii')                                                  # (4字节) 文件类型
        o += bytes("fmt ", 'ascii')                                                  # (4字节) 格式块标记
        o += (16).to_bytes(4, 'little')                                              # (4字节) 格式块长度
        o += (1).to_bytes(2, 'little')                                               # (2字节) 格式类型（1 - PCM）
        o += (num_channels).to_bytes(2, 'little')                                    # (2字节) 通道数
        o += (sampleRate).to_bytes(4, 'little')                                      # (4字节) 采样率
        o += (sampleRate * num_channels * bitsPerSample // 8).to_bytes(4, 'little')  # (4字节) 每秒字节数
        o += (num_channels * bitsPerSample // 8).to_bytes(2, 'little')               # (2字节) 每个采样的字节数
        o += (bitsPerSample).to_bytes(2, 'little')                                   # (2字节) 每个采样的比特数
        o += bytes("data", 'ascii')                                                  # (4字节) 数据块标记
        o += (datasize).to_bytes(4, 'little')                                        # (4字节) 数据块大小
        return o
    def record(self, file, duration_sec=5):
        """录音到 RAM，录完一次性写文件。
        避免录音过程边读边写 flash 导致 I2S DMA 溢出丢数据（断续）。"""
        bytes_per_second = self.sampleRate * 2 * 2  # 96000字节/秒
        total_bytes = bytes_per_second * duration_sec

        print("开始录音 %d 秒..." % duration_sec)
        data = bytearray(total_bytes)   # 录音缓冲（PSRAM）
        mv = memoryview(data)
        byteCount = 0
        start = time.ticks_ms()

        # 读满 total_bytes：readinto 直接把数据拷进 RAM，速度远快于音频流，不会溢出
        while byteCount < total_bytes:
            n = self.audioInI2S.readinto(mv[byteCount:])
            byteCount += n
            # 超时防御：ES7210 无数据时退出，避免死循环
            if n == 0 and time.ticks_diff(time.ticks_ms(), start) > (duration_sec + 3) * 1000:
                print("录音超时：ES7210 无数据输出")
                break

        # 录完一次性写文件（含 wav 头，2 声道与 I2S STEREO 一致）
        headData = self.createWavHeader(self.sampleRate, self.bitsPerSample, 2, byteCount)
        with open(file, "wb") as fOut:
            fOut.write(headData)
            fOut.write(mv[:byteCount])
        print("录音完成，共 %d 字节" % byteCount)

    def stop(self):
        """停止录音：先关 ES7210 数据源，再释放 I2S 和 MCLK。"""
        self.es7210.power_down()
        self.audioInI2S.deinit()
        self.mclk_pwm.deinit()

