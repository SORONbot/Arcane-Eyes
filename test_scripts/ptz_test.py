import time
import socket
from onvif import ONVIFCamera


def force_audio_binding(ip, port, user, pwd):
    try:
        mycam = ONVIFCamera(ip, port, user, pwd)
        media = mycam.create_media_service()

        # 1. Find the hidden audio encoder configuration
        audio_configs = media.GetAudioEncoderConfigurations()
        if not audio_configs:
            print("No audio encoders found. The camera might be blocking this via ONVIF.")
            return

        target_cfg_token = audio_configs[0].token
        print(f"Found Audio Encoder: {target_cfg_token}")

        # 2. Link it to BOTH profiles (Main and Sub)
        profiles = media.GetProfiles()
        for p in profiles:
            try:
                media.AddAudioEncoderConfiguration({
                    'ProfileToken': p.token,
                    'ConfigurationToken': target_cfg_token
                })
                print(f"Successfully linked audio to {p.Name} ({p.token})")
            except Exception as e:
                print(f"Could not link to {p.token}: {e}")

    except Exception as e:
        print(f"Connection failed: {e}")

# force_audio_binding('192.168.100.25', 80, 'admin', '')

def test_audio_handshake(ip, port=8001):
    # This hex string is a standard "Start Audio Stream" command
    # for the XMeye/NETSDK protocol
    handshake = bytes.fromhex("ff01000000000000000000000800000000000000")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        print(f"Connecting to {ip}:{port}...")
        s.connect((ip, port))

        print("Sending handshake...")
        s.send(handshake)

        # Buffer the response
        data = s.recv(1024)
        if data:
            print(f"SUCCESS! Received {len(data)} bytes.")
            print(f"First 20 bytes (Hex): {data[:20].hex()}")
            return True
        else:
            print("Connected, but camera sent no data.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        s.close()
    return False


test_audio_handshake('192.168.100.25')

def test_ptz(ip, port, user, pwd):
    try:
        # 1. Initialize Connection
        # Based on your previous probe, Port 80 worked
        mycam = ONVIFCamera(ip, port, user, pwd)
        print(f"Connected to {ip}")

        # 2. Setup Services
        media = mycam.create_media_service()
        ptz = mycam.create_ptz_service()

        # 3. Get Media Profile
        # Cameras usually have 'mainStream' and 'subStream'
        profile = media.GetProfiles()[0]
        token = profile.token
        print(f"Using Profile: {profile.Name} (Token: {token})")

        # 4. Prepare Movement Request
        # ContinuousMove requires a ProfileToken and a Velocity vector
        request = ptz.create_type('ContinuousMove')
        request.ProfileToken = token

        # Velocity values range from -1.0 to 1.0
        # x: Pan (Negative = Left, Positive = Right)
        # y: Tilt (Negative = Down, Positive = Up)
        request.Velocity = {
            'PanTilt': {'x': -0.5, 'y': 0},
            'Zoom': {'x': 0}
        }

        # 5. Execute Movement
        print("Moving Left...")
        ptz.ContinuousMove(request)

        # Move for 2 seconds
        time.sleep(2)

        # 6. Stop Movement
        print("Stopping...")
        ptz.Stop({'ProfileToken': token})
        print("Test Complete.")

    except Exception as e:
        print(f"PTZ Test Failed: {e}")

# test_ptz('192.168.100.25', 80, 'admin', '')