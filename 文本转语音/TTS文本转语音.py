import asyncio
from edge_tts import Communicate

def get_voice_option(key):
    voice_options = {
        '1': 'zh-CN-XiaoxiaoNeural',  # 晓晓，女性
        '2': 'zh-CN-YunxiNeural',  # 云希，男性
        '3': 'zh-CN-YunyangNeural',  # 云扬，男性
        '4': 'zh-CN-YunjianNeural',  # 云健，男性
        '5': 'zh-CN-XiaoyiNeural',  # 晓忆，女性
        '19': 'zh-CN-YunxiaNeural',  # 云霞，女性
        '29': 'zh-CN-XiaobeiNeural',  # 晓北，女性
        '30': 'zh-CN-guangxi-YunqiNeural1.3',  # 广西，云奇，男性
        '31': 'zh-CN-henan-YundengNeural3',  # 河南，云登，男性
        '32': 'zh-CN-liaoning-XiaobeiNeural1.3',  # 辽宁，晓北，女性
        '34': 'zh-CN-shaanxi-XiaoniNeural1.3',  # 陕西，晓妮，女性
        '37': 'zh-HK-HiuMaanNeural',  # 香港，晓曼，女性
        '38': 'zh-HK-WanLungNeural',  # 香港，云龙，男性
        '39': 'zh-HK-HiuGaaiNeural',  # 香港，晓佳，女性
        '40': 'zh-TW-HsiaoChenNeural',  # 台湾，晓晨，女性
        '41': 'zh-TW-YunJheNeural',  # 台湾，云哲，男性
        '42': 'zh-TW-HsiaoYuNeural'  # 台湾，晓宇，女性
    }
    # 6~18  20~28  30 31  33  35  36 模型似乎是收费模型 无法使用
    return voice_options.get(key, 'zh-CN-YunjianNeural')  # 默认为云健

async def main():
    # 文本内容
    text = '''秋风轻拂过窗棂，带来了几丝凉意，宣告着季节更迭的消息。落叶如同一封封信件，从枝头飘落，静静地躺在大地之上，述说着过往的故事。天空变得格外高远，云朵也似乎变得轻盈起来，仿佛整个世界都在这一刻放慢了脚步。

人们穿上了长袖，围巾和帽子开始出现在街头巷尾，每个人的脸上都洋溢着一种温暖而淡然的笑容。夜晚降临得早了一些，但家中的灯光却更加温馨。煮上一壶热茶，翻阅着手中的书卷，感受着时光在指缝间缓缓流淌。

这是一个收获的季节，不仅是大自然的果实累累，更是心灵深处的一份宁静与满足。在这样的季节里，我们学会了感恩，珍惜身边的一切美好。'''

    # 语音设置
    voice = get_voice_option('5')  # 你可以选择不同的语音
    # voice = "en-US-AriaNeural"  # 英文
    rate = "+10%"  # 减慢语音速度
    volume = "+10%"  # 音量调整为0%，即保持原样

    # 保存到的文件名
    filename = "C:/Users/15457/Desktop/output_customized.mp3"

    # 使用 Communicate 类进行 TTS
    communicate = Communicate(text, voice, rate=rate, volume=volume)
    # 将生成的语音保存到文件
    await communicate.save(filename)

# 运行异步函数
asyncio.run(main())