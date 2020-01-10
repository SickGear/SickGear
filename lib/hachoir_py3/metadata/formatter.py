NB_CHANNEL_NAME = {1: "mono", 2: "stereo"}


def humanAudioChannel(value):
    return NB_CHANNEL_NAME.get(value, str(value))


def humanFrameRate(value):
    if isinstance(value, (int, float)):
        return "%.1f fps" % value
    else:
        return value


def humanComprRate(rate):
    return "%.1fx" % rate


def humanAltitude(value):
    return "%.1f meters" % value


def humanPixelSize(value):
    return "%s pixels" % value


def humanDPI(value):
    return "%s DPI" % value
