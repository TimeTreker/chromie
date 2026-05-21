import sounddevice as sd

print("\n========== AUDIO DEVICES ==========")
for i, dev in enumerate(sd.query_devices()):
    print(f"\n[{i}] {dev['name']}")
    print(f"    Input Channels : {dev['max_input_channels']}")
    print(f"    Output Channels: {dev['max_output_channels']}")
    print(f"    Default SR     : {dev['default_samplerate']}")

print("\n========== DEFAULT DEVICES ==========")
print(f"Default Input : {sd.default.device[0]}")
print(f"Default Output: {sd.default.device[1]}")
