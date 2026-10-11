import hashlib,json,math,pathlib,subprocess
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
# The supplied URL returns JPEG. Independent JPEG decoders may differ in
# chroma upsampling and rounding, so compare visual fidelity, not byte identity.
def pixels(path):
 return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
a=pixels(root/'evidence/supplied-avatar.png'); b=pixels(root/'avatar.png')
assert len(a)==len(b)==460*460*3
differences=[abs(x-y) for x,y in zip(a,b)]
mae=sum(differences)/len(differences)
mse=sum(d*d for d in differences)/len(differences)
psnr=10*math.log10(255**2/mse) if mse else 100.0
assert mae < 2 and psnr > 40
timing=json.loads((root/'gif-frame-timing.json').read_text())['frames']
assert len(timing)==240
assert {f['pkt_duration_time'] for f in timing}=={'0.060000','0.070000'}
assert abs(sum(float(f['pkt_duration_time']) for f in timing)-16)<0.000001
report={'verified':True,'data_sha256':receipt['data_sha256'],'portrait_comparison':{'source_format':'JPEG','source_dimensions':[460,460],'rendered_format':'PNG','mean_absolute_rgb_difference':mae,'psnr_db':psnr,'acceptance':'MAE < 2 and PSNR > 40 dB; independent JPEG decoders'},'gif_frame_delays_seconds':[0.06,0.07],'gif_frame_delay_total_seconds':16.0,'streams':streams}
(root/'media-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
