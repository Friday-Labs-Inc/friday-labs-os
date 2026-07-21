import base64, io, numpy as np
from sensor_msgs.msg import Image
from PIL import Image as PImage
from friday_telemetry.telemetry_agent_node import build_keyframe_payload

# synthetic rgb8 camera frame 160x120 with structure (gradient + a block)
h,w=120,160
arr=np.zeros((h,w,3),dtype=np.uint8)
arr[:,:,1]=np.linspace(0,255,w,dtype=np.uint8)[None,:]   # green gradient (grassy)
arr[80:110,40:100]=[120,90,60]                            # a brown patch
msg=Image(); msg.height=h; msg.width=w; msg.encoding='rgb8'; msg.data=arr.tobytes()

payload,digest=build_keyframe_payload(msg,'')
assert payload is not None, "no payload"
jpeg=base64.b64decode(payload['data'])
im=PImage.open(io.BytesIO(jpeg))
print(f"class={payload['class']} enc={payload['enc']} dims={payload['w']}x{payload['h']} jpeg={len(jpeg)} B decoded={im.size} fmt={im.format}")
assert payload['class']=='keyframe' and payload['enc']=='jpeg-b64'
assert max(payload['w'],payload['h'])<=160, "not thumbnailed"
assert im.format=='JPEG' and im.size==(payload['w'],payload['h'])
assert len(jpeg)<12000, f"too big: {len(jpeg)}"
# digest gate: same frame -> no resend
p2,d2=build_keyframe_payload(msg,digest); assert p2 is None and d2==digest
# non-color encoding -> skip gracefully
msg2=Image(); msg2.height=4; msg2.width=4; msg2.encoding='32FC1'; msg2.data=bytes(64)
p3,_=build_keyframe_payload(msg2,''); assert p3 is None
print("\nALL KEYFRAME TESTS PASSED ✅  (JPEG postcard, thumbnailed, digest-gated, non-RGB skipped)")
