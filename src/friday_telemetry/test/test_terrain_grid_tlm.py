import base64, zlib, numpy as np
from nav_msgs.msg import OccupancyGrid
from friday_telemetry.telemetry_agent_node import build_map_payload

# a realistic sparse terrain ribbon: 240x240, mostly unsensed (-1), a path of classes
w=240; g=np.full((w,w),-1,dtype=np.int16)
g[100:140,100:160]=0      # drive (free)
g[105:110,150:160]=40     # gentle
g[120:125,130:140]=60     # rough
g[130:135,155:160]=100    # lethal/block
grid=OccupancyGrid(); grid.info.width=w; grid.info.height=w; grid.info.resolution=0.2
grid.info.origin.position.x=-19.0; grid.info.origin.position.y=-21.0
grid.data=g.flatten().astype(np.int8).tolist()

payload,digest=build_map_payload(grid,'',cls='terrain_grid')
assert payload is not None
raw=zlib.decompress(base64.b64decode(payload['data']))
cells=np.frombuffer(raw,dtype=np.int8).reshape(payload['h'],payload['w']).astype(np.int16)
# int8 wraps 128-255 -> negative; the encoder does b&0xFF so 100 stays 100, -1 -> 255
cells=np.where(cells<0, cells+256, cells)          # undo the b&0xFF for -1(255) etc.
cells=np.where(cells==255,-1,cells)
sensed_in=int((g!=-1).sum()); sensed_out=int((cells!=-1).sum())
print(f"class={payload['class']}  enc={payload['enc']}  res={payload['res']}  origin=({payload['ox']},{payload['oy']})")
print(f"payload data bytes (b64): {len(payload['data'])}  compressed grid of {w*w} cells")
print(f"sensed cells in={sensed_in} out={sensed_out}  free={int((cells==0).sum())} lethal={int((cells==100).sum())}")
assert payload['class']=='terrain_grid'
assert sensed_out==sensed_in, "cell count mismatch after round-trip"
assert int((cells==0).sum())==2400 and int((cells==100).sum())==25
assert len(payload['data'])<3000, f"payload too big for 4G: {len(payload['data'])}"
# digest gate: unchanged grid -> no re-send
p2,d2=build_map_payload(grid,digest,cls='terrain_grid')
assert p2 is None and d2==digest, "digest gate failed"
print(f"\ndigest-gate OK (unchanged grid -> None); payload {len(payload['data'])} B for a 44 m ribbon")
print("ALL ASSERTIONS PASSED ✅")
