from pathlib import Path
from PIL import Image, ImageDraw
import subprocess,json,hashlib,io
root=Path('examples/perl-lsp-2026-10-04-teal')
old=Path('examples/perl-lsp-2026-10-04')
counts=[5773,5691,3809,3292,109,4,734]
data=json.loads((root/'data.json').read_text())
assert [r['count'] for r in data['rows']]==counts
assert data['source']['total_commits']==129
assert data['source']['commit']=='31b87ee79b8fb55b6433bed7c1f1e4478443d61e'
assert (root/'data.json').read_bytes()==(old/'data.json').read_bytes()
assert Image.open(root/'avatar.png').convert('RGB').tobytes()==Image.open(old/'avatar.png').convert('RGB').tobytes()
results={'counts':counts,'commits':129,'data_identical_to_old_example':True,'portrait_pixels_identical':True,'media':{}}
samples=[0,0.5,1,3.5,8,15.9]
for ext,width,fps,nframes in [('mp4',1080,'60/1',960),('gif',480,None,240)]:
 media=root/f'e-balls.{ext}'
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(media)]))
 (root/f'{ext}-probe.json').write_text(json.dumps(probe,indent=2)+'\n')
 stream=probe['streams'][0]
 assert stream['width']==stream['height']==width
 assert int(stream['nb_read_frames'])==nframes
 assert abs(float(probe['format']['duration'])-16)<0.015
 if fps: assert stream['r_frame_rate']==fps
 if ext=='gif':
  im=Image.open(media); durations=[]
  for frame in range(im.n_frames):
   im.seek(frame); durations.append(im.info['duration'])
  assert sum(durations)==16000
  assert set(durations)<={60,70}
  (root/'gif-timing.json').write_text(json.dumps({'frames':len(durations),'duration_ms':sum(durations),'frame_delays_ms':durations},indent=2)+'\n')
 sheet=Image.new('RGB',(1080,768),(245,241,232)); draw=ImageDraw.Draw(sheet)
 sample_info=[]
 for i,t in enumerate(samples):
  raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(media),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
  im=Image.open(io.BytesIO(raw)).convert('RGB')
  for a,b in zip(im.getpixel((0,0)),(245,241,232)):assert abs(a-b)<=4
  if ext=='mp4' and t==0.5: im.save(root/'preview.png')
  sample_info.append({'seconds':t,'rgb_sha256':hashlib.sha256(im.tobytes()).hexdigest(),'corner':im.getpixel((0,0))})
  im.thumbnail((360,360)); x=i%3*360; y=i//3*384
  sheet.paste(im,(x,y+24));draw.text((x+12,y+5),f'{ext.upper()} {t:g}s',fill=(21,107,118))
 sheet.save(root/f'{ext}-contact-sheet.png')
 results['media'][ext]={'frames':nframes,'width':width,'duration_seconds':float(probe['format']['duration']),'samples':sample_info}
(root/'media-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
