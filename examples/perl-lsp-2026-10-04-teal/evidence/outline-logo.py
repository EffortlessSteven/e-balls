from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
import hashlib,json
root=Path('assets'); sha='763c36ef9117782905ae010056dfbe8fd2653a25'
files=[]
for family in ['Sans','Mono']:
 for suffix,source in [('Regular.ttf',f'fonts/complete/ttf/IBMPlex{family}-Regular.ttf'),('LICENSE.txt','LICENSE.txt')]:
  name=f'IBMPlex{family}-{suffix}'
  files.append({'path':name,'source':f'https://raw.githubusercontent.com/IBM/plex/{sha}/packages/plex-{family.lower()}/{source}','sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()})
(root/'plex-manifest.json').write_text(json.dumps({'repository':'https://github.com/IBM/plex','revision':sha,'license':'OFL-1.1','files':files},indent=2)+'\n')
f=TTFont(root/'IBMPlexSans-Regular.ttf'); glyphs=f.getGlyphSet(); glyph=glyphs[f.getBestCmap()[ord('e')]]
b=BoundsPen(glyphs); glyph.draw(b); x0,y0,x1,y1=b.bounds
scale=76/(y1-y0); pen=SVGPathPen(glyphs)
glyph.draw(TransformPen(pen,(scale,0,0,-scale,150-scale*(x0+x1)/2,128+scale*(y0+y1)/2)))
(root/'logo.svg').write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <title>e-balls</title>
  <rect x="2" y="2" width="252" height="252" rx="58" fill="#f5f1e8" stroke="#156b76" stroke-width="4"/>
  <circle cx="96" cy="128" r="74" fill="#156b76" opacity=".1"/>
  <circle cx="122" cy="128" r="74" fill="#156b76" opacity=".2"/>
  <circle cx="150" cy="128" r="74" fill="#156b76"/>
  <!-- IBM Plex Sans Regular lowercase e; original outline centered by ink bounds. -->
  <path fill="#f5f1e8" d="{pen.getCommands()}"/>
</svg>
''')
