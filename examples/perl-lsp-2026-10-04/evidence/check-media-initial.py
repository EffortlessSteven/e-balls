import hashlib,json,pathlib,subprocess
root=pathlib.Path('examples/perl-lsp-2026-10-04')
data=json.loads((root/'data.json').read_text())
receipt=json.loads((root/'count-verification.json').read_text())
manifest=json.loads((root/'manifest.json').read_text())
assert receipt['verified'] is True
assert hashlib.sha256((root/'data.json').read_bytes()).hexdigest()==receipt['data_sha256']
assert data['source']['commit']=='31b87ee79b8fb55b6433bed7c1f1e4478443d61e'
assert data['source']['start_inclusive']=='2026-10-04T00:00:00Z'
assert data['source']['end_exclusive']=='2026-10-11T00:00:00Z'
assert manifest['rows']==[[r['label'],r['count']] for r in data['rows']]
assert manifest['duration_seconds']==16
streams={}
for suffix,width,frames in [('mp4',1080,960),('gif',480,240)]:
 meta=json.loads((root/(suffix+'-probe.json')).read_text())
 s=meta['streams'][0]
 assert len(meta['streams'])==1
 assert s['width']==s['height']==width
 assert int(s['nb_read_frames'])==frames
 assert abs(float(meta['format']['duration'])-16)<=0.02
 assert s['codec_name']==('h264' if suffix=='mp4' else 'gif')
 if suffix=='mp4': assert s['avg_frame_rate']=='60/1'
 streams[suffix]={'width':width,'height':width,'frames':frames,'duration_seconds':float(meta['format']['duration']),'average_frame_rate':s['avg_frame_rate'],'nominal_frame_rate':s['r_frame_rate'],'codec':s['codec_name']}
# Compare decoded RGB pixels: the renderer deliberately writes a normalized PNG.
def pixels(path):
 return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
a=pixels(root/'evidence/supplied-avatar.png'); b=pixels(root/'avatar.png')
assert a==b
report={'verified':True,'data_sha256':receipt['data_sha256'],'supplied_portrait_rgb_matches_rendered_avatar':True,'portrait_rgb_sha256':hashlib.sha256(a).hexdigest(),'streams':streams}
(root/'media-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
