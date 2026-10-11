from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET
base='c1425299af74ba21afd58832d85b2d0b67dc1c28'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==base
readme=Path('README.md').read_text()
old_readme=subprocess.check_output(['git','show',base+':README.md'],text=True)
assert readme.split('\n\n')[:3]==old_readme.split('\n\n')[:3]
assert '*Top 7 perl-lsp days in the past week, rendered with `since: 7d`.*' in readme
old_files=subprocess.check_output(['git','ls-tree','-r','--name-only',base,'examples/perl-lsp-2026-10-04'],text=True).splitlines()
for p in old_files:
 assert Path(p).read_bytes()==subprocess.check_output(['git','show',f'{base}:{p}']),p
manifest=json.loads(Path('assets/plex-manifest.json').read_text())
for f in manifest['files']:
 assert hashlib.sha256((Path('assets')/f['path']).read_bytes()).hexdigest()==f['sha256']
svg=ET.parse('assets/logo.svg').getroot(); ns={'s':'http://www.w3.org/2000/svg'}
assert svg.find('s:title',ns).text=='e-balls'
assert not svg.findall('.//s:text',ns)
assert [(c.attrib['cx'],c.attrib['r'],c.attrib.get('opacity','1')) for c in svg.findall('s:circle',ns)]==[('96','74','.1'),('122','74','.2'),('150','74','1')]
assert svg.find('s:path',ns).attrib['fill']=='#f5f1e8'
source=Path('/tmp/e-balls-perl-history.git')
assert subprocess.check_output(['git','-C',str(source),'rev-parse','--is-shallow-repository'],text=True).strip()=='false'
print(json.dumps({'verified':True,'renderer_base':base,'old_example_files_preserved':len(old_files),'readme_opening_caption_and_logo_placement_preserved':True,'official_font_hashes_match':True,'logo_original_circle_geometry_and_outlined_e':True,'source_history_shallow':False,'source_repository':'https://github.com/EffortlessMetrics/perl-lsp-swarm.git','source_pin':subprocess.check_output(['git','-C',str(source),'rev-parse','31b87ee79b8fb55b6433bed7c1f1e4478443d61e^{commit}'],text=True).strip()},indent=2))
